"""Bounded foreground Blender / experimental Core GTK E2E, never a bpy mock.

BlenderSession's default Linux route remains disabled. This consumer uses only
WebView's named experimental API and the separately installed public scheduler.
"""

import argparse
import hashlib
import importlib.machinery
import json
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
from pathlib import Path

HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<title>AuroraView live host E2E</title>
<style>body{background:#101827;color:#e5edf8;font:18px sans-serif;margin:32px}
h1{font-size:26px}pre{white-space:pre-wrap;color:#8be2bc}small{color:#aab9cc}</style>
</head><body><h1>AuroraView + Blender</h1>
<p>Real WebKit document · generation __GENERATION__</p>
<small id="nonce">__NONCE__</small><pre id="status">Waiting for native bridge…</pre>
<script>
(async () => {
  const nonce = '__NONCE__';
  const status = document.getElementById('status');
  try {
    const deadline = performance.now() + 8000;
    while (!window.auroraview) {
      if (performance.now() > deadline) throw new Error('Bridge missing');
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    const api = await window.auroraview.whenReady();
    const hostEvent = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Host event timeout')), 8000);
      api.on('e2e.host_event', data => {
        if (data.nonce === nonce) { clearTimeout(timer); resolve(data); }
      });
    });
    const reply = await api.call('e2e.sum', {a: 20, b: 22, nonce}, {timeout: 8000});
    if (reply.value !== 42 || reply.nonce !== nonce || reply.host !== 'blender') {
      throw new Error('Native call result mismatch');
    }
    let rejected = false;
    try { await api.call('e2e.reject', {nonce}, {timeout: 8000}); }
    catch (error) {
      rejected = error.name === 'ValueError' && error.message === 'E2E_REJECTED';
    }
    if (!rejected) throw new Error('Error contract mismatch');
    api.send_event('e2e.js_event', {nonce, value: 7});
    const event = await hostEvent;
    if (event.value !== 8 || event.host !== 'blender') throw new Error('Event mismatch');
    status.textContent = 'JS → Blender → JS: 42\n'
      + 'JS event → Blender → JS event: 7 → 8\n'
      + 'ValueError rejection: E2E_REJECTED\n'
      + 'Real host: Blender ' + reply.version;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await api.call('e2e.report', {result: {
      nonce, value: reply.value, rejected, event_value: event.value,
      visibility: document.visibilityState, width: innerWidth, height: innerHeight,
      text: status.textContent, user_agent: navigator.userAgent
    }}, {timeout: 8000});
  } catch (error) {
    status.textContent = 'FAILED: ' + String(error);
    if (window.auroraview) window.auroraview.send_event('e2e.failure', {
      nonce, message: String(error)
    });
  }
})();
</script></body></html>"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*arguments):
    return subprocess.check_output(arguments, text=True, timeout=5).strip()


def windows():
    result = []
    for line in command('wmctrl', '-l').splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            result.append((parts[0], parts[3]))
    return result


def window_id(title):
    matches = [ident for ident, text in windows() if text == title]
    if len(matches) != 1:
        raise RuntimeError('Expected one mapped native window: ' + title)
    info = command('xwininfo', '-id', matches[0])
    if 'Map State: IsViewable' not in info:
        raise RuntimeError('Native window is not viewable')
    return matches[0]


def verify_install(site, wheel):
    import auroraview
    from auroraview import _core

    if site not in Path(auroraview.__file__).resolve().parents:
        raise RuntimeError('Core imported outside the isolated wheel site')
    if site not in Path(_core.__file__).resolve().parents:
        raise RuntimeError('Native Core imported outside the isolated wheel site')
    if not isinstance(_core.__loader__, importlib.machinery.ExtensionFileLoader):
        raise RuntimeError('A real native extension is required')
    matched = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith('auroraview/') and not name.endswith('/'):
                relative = Path(name)
                if '..' in relative.parts:
                    raise RuntimeError('Invalid wheel member')
                if (site / relative).read_bytes() != archive.read(name):
                    raise RuntimeError('Installed wheel bytes differ: ' + name)
                matched += 1
    if matched < 2:
        raise RuntimeError('No packaged Core files verified')
    return {'wheel_sha256': digest(wheel), 'matching_installed_files': matched}


class Run:
    def __init__(self, args):
        import bpy
        from auroraview.hosted import HostRuntime
        from auroraview_blender.runtime import BlenderScheduler

        if bpy.app.background or not bpy.context.window_manager.windows:
            raise RuntimeError('A foreground Blender GUI process is required')
        self.bpy = bpy
        self.out = args.evidence
        self.deadline = time.monotonic() + 90
        self.runtime = HostRuntime(experimental=True)
        self.scheduler = BlenderScheduler(bpy, interval=0.02, batch_size=1)
        self.scheduler.start()
        self.view = None
        self.generation = 0
        self.phase = 'opening'
        self.capture_after = 0.0
        self.report = None
        self.calls = 0
        self.events = 0
        self.finished = False
        self.result = {
            'status': 'running', 'host': 'blender', 'background': bpy.app.background,
            'blender_version': bpy.app.version_string, 'python_version': sys.version.split()[0],
            'route': 'experimental Core HostRuntime + public BlenderScheduler',
            'default_linux_blender_session_enabled': False, 'rounds': [],
            'core': verify_install(args.site, args.wheel), 'errors': [],
        }
        self.save()
        self.open()
        self.scheduler.submit(self.tick)

    def save(self):
        (self.out / 'result.json').write_text(json.dumps(self.result, indent=2) + '\n')

    def check(self, nonce):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Blender callback ran off the main thread')
        if nonce != self.nonce or self.phase not in ('waiting', 'capture'):
            raise RuntimeError('Stale view callback')
        if self.bpy.context.scene is None:
            raise RuntimeError('Actual Blender context is unavailable')

    def open(self):
        from auroraview import WebView

        self.generation += 1
        self.nonce = uuid.uuid4().hex
        self.title = 'AuroraView Blender E2E g{} {}'.format(self.generation, self.nonce[:8])
        self.report = None
        self.calls = 0
        self.events = 0
        self.phase = 'waiting'
        html = HTML.replace('__NONCE__', self.nonce).replace('__GENERATION__', str(self.generation))
        self.view = WebView(
            title=self.title, html=html, width=620, height=440, dcc_mode=True,
            auto_show=True, debug=False, allow_downloads=False, allow_new_window=False,
            data_directory=str(self.out / ('web-data-' + str(self.generation))),
        )
        self.view.set_call_dispatcher(self.scheduler.submit)

        def add(a, b, nonce):
            self.check(nonce)
            self.calls += 1
            return {'value': a + b, 'nonce': nonce, 'host': 'blender',
                    'version': self.bpy.app.version_string}

        def reject(nonce):
            self.check(nonce)
            raise ValueError('E2E_REJECTED')

        def js_event(data):
            self.check(data['nonce'])
            if data.get('value') != 7:
                raise RuntimeError('JS event payload mismatch')
            self.events += 1
            self.view.emit('e2e.host_event', {'nonce': self.nonce, 'value': 8, 'host': 'blender'})

        def report(result):
            self.check(result['nonce'])
            if self.report is not None:
                raise RuntimeError('Duplicate page report')
            self.report = result
            return {'received': True}

        def failure(data):
            self.result['errors'].append('Page: ' + str(data.get('message')))

        self.view.bind_call('e2e.sum', add)
        self.view.bind_call('e2e.reject', reject)
        self.view.bind_call('e2e.report', report)
        self.view.on('e2e.js_event', js_event)
        self.view.on('e2e.failure', failure)
        self.view.show_hosted(self.runtime)

    def tick(self):
        if self.finished:
            return
        try:
            if time.monotonic() > self.deadline:
                raise TimeoutError('Foreground Blender WebView E2E deadline exceeded')
            report = self.runtime.poll(max_iterations=32, max_messages=32, budget_ms=2.0)
            if self.scheduler.last_error or self.result['errors']:
                raise RuntimeError(self.scheduler.last_error or self.result['errors'][-1])
            if self.phase == 'waiting' and self.report is not None:
                page = self.report
                if not (page['value'] == 42 and page['rejected'] is True
                        and page['event_value'] == 8 and page['visibility'] == 'visible'
                        and page['width'] > 0 and page['height'] > 0
                        and self.calls == 1 and self.events == 1):
                    raise RuntimeError('Page/host assertions did not all execute')
                ident = window_id(self.title)
                command('wmctrl', '-ir', ident, '-e', '0,930,140,620,440')
                self.capture_after = time.monotonic() + 0.4
                self.phase = 'capture'
            elif self.phase == 'capture' and time.monotonic() >= self.capture_after:
                ident = window_id(self.title)
                if not any(title == 'Blender' for _, title in windows()):
                    raise RuntimeError('Foreground Blender window missing')
                screenshot = self.out / ('generation-{}.png'.format(self.generation))
                command('scrot', '--overwrite', str(screenshot))
                self.result['rounds'].append({
                    'generation': self.generation, 'nonce': self.nonce,
                    'native_window': ident, 'window_viewable': True,
                    'host_main_thread': True, 'call_count': self.calls,
                    'js_event_count': self.events, 'page': self.report,
                    'screenshot': screenshot.name, 'screenshot_sha256': digest(screenshot),
                    'closed': False,
                })
                self.save()
                self.view.request_close()
                self.phase = 'closing'
            elif self.phase == 'closing' and report['live_views'] == 0:
                if self.view.is_alive() or any(title == self.title for _, title in windows()):
                    raise RuntimeError('Closed WebView still has a live native window')
                self.result['rounds'][-1]['closed'] = True
                self.save()
                if self.generation == 1:
                    self.open()
                elif self.runtime.shutdown():
                    self.finish(True)
                    return
            self.scheduler.submit(self.tick)
        except BaseException:
            self.result['errors'].append(traceback.format_exc())
            self.finish(False)

    def finish(self, passed):
        self.finished = True
        try:
            if not self.runtime.shutdown():
                raise RuntimeError('Native shutdown is still pending')
            self.scheduler.stop()
            if self.scheduler.running or self.scheduler.pending:
                raise RuntimeError('Blender scheduler did not release its work')
        except BaseException:
            passed = False
            self.result['errors'].append(traceback.format_exc())
        self.result['status'] = 'passed' if passed else 'failed'
        self.result['shutdown_complete'] = passed
        self.save()

        def quit_blender():
            self.bpy.ops.wm.quit_blender()
            return None

        self.bpy.app.timers.register(quit_blender, first_interval=0.2)


def verify(args):
    data = json.loads((args.evidence / 'result.json').read_text())
    if args.blender_exit != 0 or data['status'] != 'passed' or data['errors']:
        raise RuntimeError('Native Blender E2E failed: ' + json.dumps(data))
    if data['background'] is not False or data['shutdown_complete'] is not True:
        raise RuntimeError('Missing foreground host / completed cleanup')
    if [item['generation'] for item in data['rounds']] != [1, 2]:
        raise RuntimeError('Both native generations must execute')
    if len({item['nonce'] for item in data['rounds']}) != 2:
        raise RuntimeError('Reopen did not use a fresh document nonce')
    for item in data['rounds']:
        if item['closed'] is not True or item['window_viewable'] is not True:
            raise RuntimeError('Native window lifecycle did not complete')
        name = item['screenshot']
        if not re.fullmatch(r'generation-[12]\.png', name):
            raise RuntimeError('Unexpected screenshot path')
        image = args.evidence / name
        if image.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n' or digest(image) != item['screenshot_sha256']:
            raise RuntimeError('Missing or mismatched native screenshot')
    print(json.dumps(data, indent=2))
    print('Foreground Blender / experimental GTK E2E passed; default Linux route unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--blender-exit', type=int)
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    args.evidence = args.evidence.resolve()
    args.evidence.mkdir(parents=True, exist_ok=True)
    if args.verify:
        verify(args)
        return
    args.site = args.site.resolve(strict=True)
    args.wheel = args.wheel.resolve(strict=True)
    sys.path.insert(0, str(args.site))
    try:
        Run(args)
    except BaseException:
        (args.evidence / 'startup-error.txt').write_text(traceback.format_exc())
        raise


if __name__ == '__main__':
    main()
