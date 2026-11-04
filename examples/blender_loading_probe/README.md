# Blender loading probe

The follow-up investigation, stage timings, OA redirect evidence and measured
optimization prototypes are recorded in
[the loading diagnosis](../../notes/auroraview-loading-diagnosis.md).

A small diagnostic add-on: one Blender operator opens a floating AuroraView
window containing static HTML. The default page needs no scene data, Qt,
JavaScript framework, external font, authentication, or Vibely service. Optional
URL measurements compare the same window lifecycle with actual online pages.

For the retained-window acceptance path, use `--retained --runs 3 --quit`. The
Blender timer prepares a hidden native window, then shows the local test page
after its DOM, bridge and first contentful paint are ready. This is test-page
readiness; `RetainedWindow` still reports native `hidden` without waiting for
page readiness.
The next two runs hide and reopen the same HWND and check a marker left in the
DOM; the final run closes it. The JSONL output records `prepared`,
`hide_requested`, `dom_retained`, and `closed`. A user can omit `--quit`, click
the native X to hide, and use the sidebar operator to reopen the same window.
After an explicit close, the next operator click creates a fresh manager. The
manager owns a persistent Blender `exit_pre` handler and waits up to two seconds
for native cleanup during normal host exit.

For each retained display, `desktop_pixel_visible.since_show_ms` measures from
the show request to a known page color in an actual desktop pixel.
`desktop_screenshot` saves a BMP of the screen's window client rectangle. The
first opening's import, native creation, page load and hidden FCP are reported
separately. Later openings preserve DOM, input, scroll and binding. An occluded
window or page that never reaches hidden FCP is an invalid or timed-out sample.

```powershell
vx just blender-loading-probe 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --retained --runs 3 --quit --output target/loading-probe/retained.jsonl
```

Use `--runs 20` for the full DOM, input, scroll and binding reuse check. The
`--exit-at preparing|hidden|visible|callback` option requests Blender exit at
one lifecycle point. The JSONL `exit_requested` and `exit_pre_observed` rows
include lifecycle state, native/owner/host completion flags and active callback
count; callback mode deliberately holds a business callback beyond the shared
two-second cleanup budget.

For unload and file-switch acceptance, run separate fresh-profile probes with
`--unload-at-hidden` and `--file-switch-at-hidden`. Their JSONL rows record
the manager completion/handler state and the file-switch result.

The resource runner launches Blender and its sampler together. It flushes
process-tree samples to JSONL, then writes a summary JSON. The final memory
sample is the last live hidden sample, even if Blender exits before summary.
Use fresh, different prefixes for retained and idle control runs. By default
it performs 20 openings and holds hidden for 302 seconds, leaving at least
300 seconds of one-second observations. `psutil` is validation-only and comes
from `vx uv run --with psutil`.

```powershell
vx uv run --with psutil python examples/blender_loading_probe/resource_sampler.py --launch 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' target/loading-probe/retained-resource
vx uv run --with psutil python examples/blender_loading_probe/resource_sampler.py --launch 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' target/loading-probe/idle-resource --idle
```

`--runs 2 --hold-seconds 4` checks the sampler quickly; the short run reports
`valid: false` because it is shorter than five minutes.

Build the current Core, then run a **visible** Blender process on Windows:

```powershell
vx just build-release
vx just blender-loading-probe 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --runs 3 --quit --output target/loading-probe/inline-1.jsonl
```

The first run opens a new WebView2 profile by default when the output name has
not been used before. Subsequent runs close and construct a fresh view in the
same Blender process and profile. Reusing the output path appends observations
and reuses that profile; use a different filename for a fresh-profile comparison.
`--profile` explicitly selects a persistent profile directory. `--site` selects
the directory containing an alternate `auroraview` package; it defaults to this
checkout's `python/` directory. Record the binary/build used when comparing runs.

To compare inline HTML with a real URL served exclusively over loopback:

```powershell
vx just blender-loading-probe 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --source http --runs 3 --quit --output target/loading-probe/http-1.jsonl
```

Omit `--quit` to leave the last window open for inspection. Closing it manually
allows **3D View > Sidebar > Loading Probe > Open Loading Probe** to reopen it.
The add-on registers only for this session; it does not install itself or change
Blender preferences. A background/headless Blender run is not rendering evidence.

Each JSONL record includes its run number and event:

| Event | Meaning |
| --- | --- |
| `open_requested` | Operator begins, before the first AuroraView import |
| `imported` | Python import completes; records package version and path |
| `constructed` | Python/Core constructor returns |
| `show_returned` | Non-blocking `show(wait=False)` returns |
| `window_visible` | Blender timer first observes `IsWindowVisible(hwnd)` |
| `script_started`, `dom_ready`, `load` | Actual document progress |
| `first-paint`, `first-contentful-paint` | Chromium Paint Timing entries |
| `bridge_ready` | The page observes the injected bridge's `isReady()` |
| `complete`, `page_timeout`, `close_timeout` | Probe outcome |

For browser events, use `since_open_ms` to compare with `window_visible.elapsed_ms`.
`page_ms` starts at the document time origin. Other `elapsed_ms` values describe
Python observation/report receipt, including HTTP delivery latency. Browser
timings use `performance.timeOrigin` and Python uses the system wall clock;
do not adjust the system clock during a run. Visibility is sampled by Blender's
10 ms timer and can be observed late if its main thread is busy. FCP is a browser
paint metric, not an independent measurement of pixels reaching the monitor.

The static page reports over a temporary loopback HTTP endpoint independently
of the AuroraView bridge, so slow bridge startup cannot conceal paint timing.
Logs/profiles live under ignored `target/loading-probe/` by default.

```powershell
vx just lint-blender-loading-probe
```

## Local files and online pages

The measurement runner uses the repository's Python Playwright dependency to
connect to the **actual Blender WebView2 instance**, without launching a separate
browser or altering the remote page. It reads buffered Paint Timing entries,
navigation response/DOM/load timings, final URL/title/status and a short content
sample. It captures each non-authentication page to PNG, then closes the native
window and opens the next one. CDP is reconnected for each new WebView2 target.

```powershell
vx just measure-blender-loading-probe 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --source file --runs 3 --output target/loading-probe/file-cdp.jsonl
vx just measure-blender-loading-probe 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --source url --url https://vibely.woa.com/photoshop-colorist-doc/ --runs 3 --profile target/loading-probe/vibely-auth-profile --output target/loading-probe/vibely-cdp.jsonl
```

`file` writes the minimal page to disk and passes its `file://` URL to Core.
On Windows, Core translates it to `https://auroraview.localhost/type:file/...`;
the measured page is still loaded from disk. This differs from both inline HTML
and the loopback HTTP server.

An unauthenticated Vibely profile redirects to OA. To prepare a session, run a
single opening with `--auth-wait 600`, complete login manually in that WebView,
and wait for the target document to open. This setup opening is marked
`manual_auth` and must be excluded from performance results. Then restart the
measurement using the same `--profile` and a new output filename. The runner
does not enter credentials or copy browser cookies. Authentication pages are
reported as such and do not count as successful target-page measurements.

In CDP runs, use `snapshot.fcp_since_open_ms` for FCP, and subtract
`window_visible.elapsed_ms` for the visibility-to-FCP interval. The screenshot
is taken after the document is complete and has had two seconds to settle;
that later screenshot/report time is **not** the FCP. This does not establish
application-specific readiness. The controller does not reload or navigate the
page, so first navigation remains initiated by AuroraView itself.

For targeted diagnosis, `--trace-rust` enables native stage logs;
`--prewarm hidden` retains a hidden view before opening measured business views;
`--prewarm library` waits for the existing warmup API; and `--reopen-delay 5`
waits after native close before constructing the next window. These change only
the diagnostic experiment. Warmup/preparation time is recorded separately and
must not be presented as eliminated startup work.

`--reload-pairs 3` additionally compares live reloads with an authenticated,
in-memory copy of the Colorist document via CDP Fetch. These are separately
labelled navigation samples, not new-window FCP. Cookie diagnostics retain only
metadata and blocked reasons, never cookie values or authentication headers.
For a control with no CDP port, use `blender-loading-probe --source url --url ...
--ipc-probe`; it reports Paint Timing through the bridge on a host queue.

Additional measured groups (same release binary, three openings per group):

| Page / profile | First opening to FCP | Same-process reopening to FCP | First visibility to FCP |
| --- | ---: | ---: | ---: |
| Inline HTML, fresh profile | 2327 ms | 214–269 ms | 433 ms |
| Local HTML file, fresh profile | 2353 ms | 196–270 ms | 473 ms |
| Local HTML file, existing profile in a new Blender process | 1102 ms | 252–284 ms | 429 ms |
| `https://example.com/`, fresh profile | 3579 ms | 202–276 ms | 110 ms |
| Vibely Colorist docs, authenticated existing profile (two groups) | 2504–2556 ms | 572–628 ms | 600–636 ms |

These **18** additional openings all produced screenshots, document status 200,
completion records and native-close observations. Raw evidence is in
`expanded-inline-1.jsonl`, `expanded-file-2.jsonl`,
`expanded-file-existing-1.jsonl`, `expanded-example-1.jsonl`,
`expanded-vibely-1.jsonl`, and `expanded-vibely-2.jsonl` under
`target/loading-probe/`. The interrupted observer experiment
`expanded-file-1.jsonl` is excluded. The inline run's original URL display was
`nullblank`; the observer now renders this opaque-origin location correctly as
`about:blank`, without changing its timing calculation.

The requested `https://vibely.woa.com/photoshop-colorist-doc/` initially reached
the OA sign-in page in a fresh profile. After manual login, it opened the real
document: title `Colorist 使用指南`, H1 `Photoshop Colorist`, HTTP status 200.
`expanded-vibely-auth-setup.jsonl` is marked `manual_auth` and excluded from
performance statistics. The two subsequent Blender processes reused that profile;
all six measured openings reached the real document without manual login.

For the four same-process Vibely reopenings, native visibility was observed at
121–158 ms after opening, while FCP occurred at 572–628 ms. This leaves a
**432–506 ms visibility-to-FCP interval**, compared with 56–102 ms for local
HTML-file reopenings in these groups. Navigation start to response first byte
was 331–372 ms for the Vibely reopenings. This suggests investigating the remote
navigation/response phase in addition to initial WebView startup; it does not
separate transport time, authentication checks and server processing. The local
and public-page fresh profiles differ from the authenticated Vibely profile, so
their first-opening values are scenario observations, not a controlled estimate
of the server's standalone overhead.

## Local validation: 2026-11-03

Windows 11, Blender **5.2.3 LTS**, Blender Python **3.13.13**, AuroraView
**0.5.13**, source revision `c29c75b5`, built with `vx just build-release`.
Loaded binary: this checkout's `python/auroraview/_core.pyd`, SHA-256
`879431F7EDB43337674C21B77BD3D395C68CFF132B01F17D736788EF938106EB`.

Four separate visible Blender processes each opened three windows sequentially:
two inline-HTML groups and two HTTP groups, each with a fresh profile. All **12**
windows reported visibility, FCP and bridge readiness, then closed successfully.
An additional new Blender process reused the first group's profile and completed
one opening; its window was left open for inspection.

| Scenario | Samples | Open request to FCP | Observed window visibility to FCP |
| --- | ---: | ---: | ---: |
| Fresh profile, first opening, inline HTML | 2 | 2316–2890 ms | 384–435 ms |
| Fresh profile, first opening, loopback URL | 2 | 2312–2550 ms | 404–528 ms |
| Same-process reopening, inline HTML | 4 | 228–260 ms | 54–98 ms |
| Same-process reopening, loopback URL | 4 | 186–336 ms | 48–149 ms |
| New process, existing profile, inline HTML | 1 | 631 ms | 77 ms |

Evidence is stored locally under `target/loading-probe/`:
`release-inline-1.jsonl`, `release-inline-2.jsonl`, `release-http-1.jsonl`,
`release-http-2.jsonl`, and `release-existing-profile.jsonl`.
The earlier `debug-inline-1.jsonl` is an exploratory run with an interrupted
sampler and is **excluded** from these results.

The minimal page reproduces a measurable interval between a visible window and
its first contentful paint. Startup is substantially slower with a fresh profile
than reopening in the same process. These observations establish a Core baseline;
they do not identify a root cause or measure Vibely's network/auth/app startup.
No Core loading behavior was changed. The release measurements come from actual
browser Paint Timing and native-window visibility observations, subject to the
measurement limitations described above.
