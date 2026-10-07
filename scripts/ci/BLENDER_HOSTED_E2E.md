# Minimal foreground Blender / GTK E2E

The opt-in CI job starts one official Blender 3.6.21 process without
`--background`, under Xvfb and a real window manager. It installs this same
workflow run's exact experimental Core wheel and the fixed Blender adapter
candidate. The consumer calls `WebView.show_hosted(HostRuntime(experimental=True))`
and the public `BlenderScheduler`; it never opens or bypasses the disabled
default Linux `BlenderSession` route.

Each of two fresh WebView documents must render, call real main-thread Blender
Python, receive the value 42, reject an intentional ValueError with its original
name/message, and exchange a JS event / host event with measured values 7 / 8.
Each document uses a fresh nonce. The native window must be viewable in X11,
captured in a real PNG, then absent after close; Core must report zero live views.
Finally the scheduler and runtime shut down and Blender exits normally.

The driver writes result.json and two generation screenshots. The outer verifier
requires both rounds, their close results, matching PNG hashes and Blender exit 0.
Any missing window, backend failure, timeout, or skipped stage fails the job.
Retain failures and inspect actual screenshot pixels before claiming visible
acceptance. A source check or a PNG file's existence alone is not visual proof.

The 150-second process deadline and 10-minute job limit are deliberate. No
WebKit sandbox, kernel/user-namespace policy, or host security setting is changed.
WebKit bootstrap restrictions are failures to diagnose, not instructions to add
`--no-sandbox` or equivalent variables. No network page, user project, native dock,
asset drag/drop, production Linux support, or performance claim is tested here.

The job is opted in on the experiment/hosted-gtk-source-v4 PR branch, or by the
workflow_dispatch blender_e2e input. Other branches do not run the GUI job by
default. It reuses same-run artifacts with contents:read; no extra token scopes.
