# Portable hosted close-admission source tests

These tests load actual Python lifecycle/API/events/signals/HostRuntime files
from this Core checkout using only the Python standard library. They do not
load the native extension, GTK, WebKit or Blender. Native state/proxy objects are
explicit fakes; this is not native acceptance.

Use stdlib unittest discovery on tests/hosted_gtk_source from the Core checkout
through the repository's vx/just CI wrapper. reentrant_close_probe.py accepts
--source-root pointing either to a Core checkout or an earlier complete candidate
root, and --case python_close or native_retirement. Exit 1 means a stale mutation
or a finalizer exception; v3 is the intentional negative control. No private
experiment path is hardcoded.

BlenderScheduler-specific tests belong to the adapter/harness, not this directory.
Rust tests and real native acceptance are separate required gates.

The collectable test_close_admission.py contains one isolation driver. It launches
_close_admission_cases.py with the same Python interpreter in a child process,
requires exactly 12 passing cases and zero skips, and enforces a 30-second
process deadline. Package shells exist only in that child, so collecting this
directory beside the ordinary Python suites cannot replace their auroraview
modules. The driver is not a thirteenth lifecycle case. The twelve cases overlap
with the existing standalone harness coverage; do not add both totals together.
