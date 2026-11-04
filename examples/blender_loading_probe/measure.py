"""Read actual document timing through CDP in a visible Blender process."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = """() => {
  const navigation = performance.getEntriesByType('navigation')[0];
  const paint = performance.getEntriesByName('first-contentful-paint')[0];
  const clean = value => {
    try { const u = new URL(value); return u.origin === 'null' ? u.protocol + u.pathname : u.origin + u.pathname; }
    catch { return ''; }
  };
  return {
    url: location.protocol === 'about:' ? location.href : location.origin + location.pathname,
    title: document.title,
    ready: document.readyState, time_origin_ms: performance.timeOrigin,
    fcp_page_ms: paint?.startTime ?? null,
    response_page_ms: navigation?.responseStart ?? null,
    dom_page_ms: navigation?.domContentLoadedEventEnd ?? null,
    load_page_ms: navigation?.loadEventEnd ?? null,
    status: navigation?.responseStatus ?? null,
    navigation: navigation ? {...navigation.toJSON(), name: clean(navigation.name)} : null,
    resources: performance.getEntriesByType('resource')
      .filter(entry => !entry.name.includes('/metrics')).slice(0, 100)
      .map(entry => ({...entry.toJSON(), name: clean(entry.name)})),
    font_status: document.fonts?.status ?? null,
    bridge_ready: window.auroraview?.isReady?.() ?? false,
    heading: document.querySelector('h1')?.textContent?.trim().slice(0, 160) ?? '',
    text: document.body?.innerText?.slice(0, 500) ?? ''
  };
}"""

SAFE_HEADERS = (
    "cache-control",
    "content-type",
    "content-encoding",
    "content-length",
    "server",
    "server-timing",
    "age",
    "etag",
    "last-modified",
    "vary",
)


def clean_url(value):
    parts = urlsplit(value)
    return parts.scheme + "://" + parts.netloc + parts.path


def wait_document(page):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        data = page.evaluate(DOCUMENT)
        if data["fcp_page_ms"] is not None and data["ready"] == "complete":
            page.wait_for_timeout(500)
            return page.evaluate(DOCUMENT)
        page.wait_for_timeout(50)
    raise RuntimeError("No completed document paint after reload")


def reload_pairs(page, opened, pairs):
    """Compare live navigation with an in-memory copy of the authenticated HTML."""
    response = page.request.get(page.url, timeout=30000)
    if response.status != 200 or clean_url(response.url) != clean_url(page.url):
        raise RuntimeError("Authenticated document copy could not be obtained")
    body = response.body()
    headers = {
        key: value
        for key, value in response.headers.items()
        if key not in ("content-encoding", "content-length", "transfer-encoding", "set-cookie")
    }
    document_url = clean_url(page.url)

    session = page.context.new_cdp_session(page)
    session.send("Network.enable")

    def replay(event):
        session.send(
            "Fetch.fulfillRequest",
            {
                "requestId": event["requestId"],
                "responseCode": 200,
                "responseHeaders": [
                    {"name": key, "value": value} for key, value in headers.items()
                ],
                "body": base64.b64encode(body).decode("ascii"),
            },
        )

    for pair in range(1, pairs + 1):
        for mode in ("live", "replay_html"):
            chain = []

            def on_request(event, chain=chain):
                if event.get("type") != "Document":
                    return
                previous = event.get("redirectResponse")
                chain.append(
                    {
                        "url": clean_url(event["request"]["url"]),
                        "redirect_status": previous.get("status") if previous else None,
                    }
                )

            session.on("Network.requestWillBeSent", on_request)
            if mode == "replay_html":
                # Fetch interception avoids Playwright page.route(), which also
                # disables HTTP caching and would change the asset control.
                session.on("Fetch.requestPaused", replay)
                session.send(
                    "Fetch.enable",
                    {"patterns": [{"urlPattern": document_url, "resourceType": "Document"}]},
                )
            started = time.monotonic()
            result = page.reload(wait_until="load", timeout=30000)
            data = wait_document(page)
            if mode == "replay_html":
                session.send("Fetch.disable")
                session.remove_listener("Fetch.requestPaused", replay)
            session.remove_listener("Network.requestWillBeSent", on_request)
            data["headers"] = (
                {key: value for key, value in result.headers.items() if key in SAFE_HEADERS}
                if result
                else {}
            )
            data["document_chain"] = chain
            data["observed_elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
            if data["status"] != 200 or data["heading"] != "Photoshop Colorist":
                raise RuntimeError("Reload did not reach the authenticated Colorist document")
            report(opened, "reload_sample", pair=pair, mode=mode, **data)
            print(
                json.dumps(
                    {
                        "pair": pair,
                        "mode": mode,
                        "fcp_page_ms": data["fcp_page_ms"],
                        "response_page_ms": data["response_page_ms"],
                    }
                ),
                flush=True,
            )
    session.detach()


def rows(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # Another process may still be writing the last record.
    return result


def report(opened, event, **data):
    payload = json.dumps({"run": opened["run"], "event": event, **data}).encode()
    request = urllib.request.Request(
        opened["endpoint"] + "/metrics", payload, {"Content-Type": "text/plain"}
    )
    with urllib.request.urlopen(request, timeout=5):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blender")
    parser.add_argument("--source", choices=("inline", "file", "http", "url"), default="file")
    parser.add_argument("--url")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--profile")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--auth-wait",
        type=float,
        default=0,
        help="Seconds to allow manual OA login; exclude this setup run from timing",
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--trace-rust", action="store_true")
    parser.add_argument(
        "--prewarm", choices=("none", "import", "library", "hidden"), default="none"
    )
    parser.add_argument("--reopen-delay", type=float, default=0)
    parser.add_argument(
        "--reload-pairs",
        type=int,
        default=0,
        help="Colorist only: alternate live reloads and local HTML replay",
    )
    args = parser.parse_args()
    if args.source == "url" and not args.url:
        parser.error("URL mode requires --url")
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("Choose a new output filename; existing measurement logs are preserved")
    output.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [
        shutil.which("vx"),
        "just",
        "blender-loading-probe",
        args.blender,
        "--source",
        args.source,
        "--runs",
        str(args.runs),
        "--quit",
        "--cdp-port",
        str(port),
        "--timeout",
        str(args.timeout + args.auth_wait + 15),
        "--output",
        str(output),
        "--prewarm",
        args.prewarm,
        "--reopen-delay",
        str(args.reopen_delay),
    ]
    if args.url:
        command += ["--url", args.url]
    if args.profile:
        command += ["--profile", str(Path(args.profile).resolve())]
    console_path = output.with_suffix(".console.txt")
    with console_path.open("w", encoding="utf-8") as console:
        environment = dict(os.environ)
        if args.trace_rust:
            environment["RUST_LOG"] = "_core::webview=info,auroraview_core::cleanup=info"
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=console,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=environment,
        )
        browser = None
        failed = False
        with sync_playwright() as playwright:
            for run in range(1, args.runs + 1):
                # Reopening creates a new WebView2 target/environment. An old
                # connection can stay alive while no longer discovering it.
                browser = None
                deadline = time.monotonic() + args.timeout + args.auth_wait
                opened = None
                auth_seen = False
                ready_since = None
                last_url = None
                network_session = None
                initial_chain = []
                cookie_requests = []
                resource_responses = []
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Blender exited early; inspect " + str(console_path))
                    if opened is None:
                        opened = next(
                            (
                                row
                                for row in rows(output)
                                if row["run"] == run and row["event"] == "open_requested"
                            ),
                            None,
                        )
                        if opened is None:
                            time.sleep(0.1)
                            continue
                    try:
                        if browser is None or not browser.is_connected():
                            with urllib.request.urlopen(
                                "http://127.0.0.1:%d/json/version" % port, timeout=1
                            ):
                                pass
                            browser = playwright.chromium.connect_over_cdp(
                                "http://127.0.0.1:%d" % port, timeout=2000
                            )
                        pages = [
                            page
                            for context in browser.contexts
                            for page in context.pages
                            if not page.is_closed() and page.title() != "Probe Warmup"
                        ]
                        if not pages:
                            time.sleep(0.1)
                            continue
                        page = pages[-1]
                        if network_session is None:
                            network_session = page.context.new_cdp_session(page)

                            def capture_request(event, chain=initial_chain):
                                if event.get("type") == "Document":
                                    previous = event.get("redirectResponse") or {}
                                    chain.append(
                                        {
                                            "id": event["requestId"],
                                            "url": clean_url(event["request"]["url"]),
                                            "from_url": clean_url(previous.get("url", "")),
                                            "redirect_status": previous.get("status"),
                                        }
                                    )

                            def capture_cookies(event, samples=cookie_requests):
                                samples.append(
                                    {
                                        "id": event["requestId"],
                                        "cookies": [
                                            {
                                                "name": item["cookie"]["name"],
                                                "domain": item["cookie"]["domain"],
                                                "sameSite": item["cookie"].get("sameSite"),
                                                "blocked": item.get("blockedReasons", []),
                                            }
                                            for item in event.get("associatedCookies", [])
                                        ],
                                    }
                                )

                            def capture_response(event, samples=resource_responses):
                                if event.get("type") in (
                                    "Document",
                                    "Stylesheet",
                                    "Script",
                                    "Font",
                                ):
                                    response = event["response"]
                                    samples.append(
                                        {
                                            "url": clean_url(response["url"]),
                                            "type": event["type"],
                                            "status": response["status"],
                                            "disk_cache": response.get("fromDiskCache", False),
                                            "headers": {
                                                key.lower(): value
                                                for key, value in response.get(
                                                    "headers", {}
                                                ).items()
                                                if key.lower() in SAFE_HEADERS
                                            },
                                        }
                                    )

                            network_session.on("Network.requestWillBeSent", capture_request)
                            network_session.on(
                                "Network.requestWillBeSentExtraInfo", capture_cookies
                            )
                            network_session.on("Network.responseReceived", capture_response)
                            network_session.send("Network.enable")
                        data = page.evaluate(DOCUMENT)
                    except (Error, OSError):
                        time.sleep(0.1)
                        continue
                    host = urlsplit(data["url"]).hostname or ""
                    is_auth = "passport.woa.com" in host or "OA登录" in data["title"]
                    if is_auth:
                        if not auth_seen:
                            report(opened, "auth_required", url=data["url"], title=data["title"])
                            print(
                                "AUTH_REQUIRED: Complete OA login manually in the Blender WebView.",
                                flush=True,
                            )
                            auth_seen = True
                        if args.auth_wait:
                            time.sleep(0.25)
                            continue
                    if args.source == "url" and not is_auth:
                        requested = urlsplit(args.url)
                        actual = urlsplit(data["url"])
                        if actual.hostname != requested.hostname or (
                            actual.path.rstrip("/") != requested.path.rstrip("/")
                        ):
                            time.sleep(0.1)
                            continue
                    if data["url"] != last_url:
                        ready_since = None
                        last_url = data["url"]
                    if (
                        data["fcp_page_ms"] is None
                        or data["ready"] != "complete"
                        or not data["text"]
                    ):
                        time.sleep(0.1)
                        continue
                    if ready_since is None:
                        ready_since = time.monotonic()
                    if time.monotonic() - ready_since < 2:
                        time.sleep(0.1)
                        continue
                    # Timing entries are buffered; connecting late does not reset their origin.
                    data["fcp_since_open_ms"] = round(
                        data["time_origin_ms"] + data["fcp_page_ms"] - opened["started_epoch_ms"], 2
                    )
                    data["manual_auth"] = bool(auth_seen and args.auth_wait)
                    data["auth_page"] = is_auth
                    data["initial_document_chain_partial"] = initial_chain
                    data["resource_responses_partial"] = resource_responses
                    browser_session = browser.new_browser_cdp_session()
                    try:
                        data["runtime_processes"] = browser_session.send(
                            "SystemInfo.getProcessInfo"
                        )["processInfo"]
                    except Error:
                        data["runtime_processes"] = []
                    browser_session.detach()
                    request_ids = {item["id"] for item in initial_chain}
                    data["document_cookie_metadata_partial"] = [
                        item for item in cookie_requests if item["id"] in request_ids
                    ]
                    if args.url:
                        data["cookie_metadata"] = [
                            {
                                key: cookie.get(key)
                                for key in (
                                    "name",
                                    "domain",
                                    "path",
                                    "expires",
                                    "sameSite",
                                    "secure",
                                    "httpOnly",
                                )
                            }
                            for cookie in page.context.cookies([args.url])
                        ]
                    if not is_auth:
                        screenshot = output.with_name(output.stem + "-%d.png" % run)
                        page.screenshot(path=str(screenshot), timeout=5000)
                        data["screenshot"] = str(screenshot)
                    if args.reload_pairs and not is_auth:
                        reload_pairs(page, opened, args.reload_pairs)
                    report(opened, "snapshot", **data)
                    print(
                        json.dumps(
                            {
                                "run": run,
                                **{
                                    key: data[key]
                                    for key in (
                                        "url",
                                        "title",
                                        "fcp_since_open_ms",
                                        "status",
                                        "auth_page",
                                        "manual_auth",
                                    )
                                },
                            }
                        ),
                        flush=True,
                    )
                    failed |= is_auth or (data["status"] is not None and data["status"] >= 400)
                    break
                else:
                    failed = True
                    if opened:
                        report(opened, "observer_timeout")
                    print("Observer timed out for run %d" % run, flush=True)
                    break
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Probe is still open; inspect " + str(console_path)) from None
    recorded = rows(output)
    completed = sum(row["event"] == "complete" for row in recorded)
    closed = sum(row["event"] == "closed" for row in recorded)
    if failed or process.returncode or completed != args.runs or closed != args.runs:
        raise SystemExit("Incomplete measurement: inspect " + str(output))
    print("Verified %d page snapshots and native closes: %s" % (args.runs, output))


if __name__ == "__main__":
    main()
