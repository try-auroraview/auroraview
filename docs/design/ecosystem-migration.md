# AuroraView organization and host repository migration

The canonical repository is [try-auroraview/auroraview](https://github.com/try-auroraview/auroraview).
Moving repository ownership and extracting host integration sources are separate
changes. This ownership change updates live repository metadata, installers,
self-update targets, and documentation links. It keeps the `auroraview` Python
package, `auroraview._core` extension, `@auroraview/sdk`, Cargo package names,
versions, and public APIs unchanged.

## Repository continuity and external services

A GitHub repository transfer preserves repository history and redirects old
repository links. Historical changelogs, design records, and source attribution
retain their original references. The former repository location must remain
available for redirects. GitHub Pages URLs do not follow the repository redirect;
the documentation address becomes `https://try-auroraview.github.io/auroraview/`
and requires a successful Pages deployment. See GitHub's
[repository transfer documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository).

External integrations require their own verification after the owner change.
Trusted publishing identifies a repository owner, repository, workflow, and an
optional environment; those external authorization records must match the
transferred repository before a future package release. See the official
[PyPI](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) and
[npm](https://docs.npmjs.com/trusted-publishers/) configuration documentation.
The ownership change does not modify
publisher permissions, credentials, environments, or publication steps. Codecov's
existing association also requires verification before replacing its service
links. No package release or new host package publication is part of this change.

## Shared contracts and core ownership

The existing [adapter contract](adapter-contract.md) and
[RFC 0019](../rfcs/0019-pluggable-backend-and-host-adapter-contract.md) define
`HostAdapter`, `HostRegistry`, `RenderBackend`, and `BackendRegistry`. Host
repositories must use those contracts and the existing thread dispatcher
registry. They must not introduce another host registration or permission system.
Rust adapters must use the contract re-export through `auroraview_core::contract` so
core and adapters share one contract type.

The WebView engine, native bindings, Qt integration, shared thread dispatch
contracts, common bridge, SDK, and shared packaging infrastructure remain in the
main repository. Host packages depend on core. Source extraction alone does not
remove the current built-in host implementations or change discovery precedence.
Replacing core imports with compatibility facades is a later reviewed change.

## Host source boundaries

Shared host descriptors live in
[`python/auroraview/adapter/hosts.py`](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/adapter/hosts.py).
The table links the host-specific source available for extraction. It does not certify a
supported host version, an independently installed package, or a licensed host
acceptance test. An import against a fake host SDK verifies Python behavior only.

| Host | Source currently in core | Extraction and acceptance gates |
| --- | --- | --- |
| Maya | [Dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/maya.py) using function-local `maya.utils`, shared Qt host metadata, DCC documentation and examples | Opt-in development package in the [Maya repository](https://github.com/try-auroraview/auroraview-maya); independently installed wheel/import checks, real Maya owner-thread dispatch, parent embedding, and lifecycle verification before core cutover |
| Houdini | [Dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/houdini.py) using `hdefereval`, shared Qt host metadata, DCC documentation | Extract host-specific sources and history; verify Qt parent integration and dispatch in a licensed Houdini process |
| Nuke | [Dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/nuke.py) using `nuke`, shared Qt host metadata, IPC tests | Define package documentation and install boundaries; verify host-thread dispatch and UI ownership in Nuke |
| Blender | [Dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/blender.py) using `bpy.app.timers`, floating/out-of-process metadata, DCC documentation and tests | Verify timer dispatch and floating window lifecycle in Blender; do not infer Qt child embedding from another host |
| 3ds Max | [Dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/max.py) using `pymxs` and the shared Qt event loop, host metadata and DCC documentation | Preserve the existing `max` identifier; explicitly map any external `3dsmax` identifier and verify dispatch and parent ownership in 3ds Max |
| Unreal Engine | [Python dispatcher](https://github.com/try-auroraview/auroraview/blob/main/python/auroraview/utils/thread_dispatcher/backends/unreal.py) using Slate post-tick, GameThread/Slate metadata; [Rust integration](https://github.com/try-auroraview/auroraview/blob/main/crates/auroraview-ue/src/lib.rs) | Resolve inherited workspace metadata and sibling `auroraview-core`/`auroraview-signals` path dependencies; implement and verify the native surface path before declaring an engine plugin |
| Unity | No Unity C# or UPM implementation in the current source | Implement a Unity integration, package layout, editor lifecycle, and real editor tests before creating a supported adapter package |

The Unreal native `create_webview` path currently returns a null pointer with a
TODO. A Python dispatcher or metadata adapter does not establish a working Slate
WebView integration. Other host metadata or documentation, including PowerPoint
and Adobe applications, likewise needs an explicit source and acceptance review
before joining the independent package set.

Independent host repositories should preserve the history of extracted source
paths and retain upstream attribution. Each repository needs its own package
metadata, compatible core dependency, portable CI, version policy, and release
configuration. Repository creation and passing mock tests do not complete these
gates.

## Core cutover gates

Before replacing core implementations with facades, verify imports with core
alone, a missing optional host package, and independently installed core plus host
packages. Test both canonical-first and legacy-first imports, host discovery,
registration precedence, and repeated registration. Both import paths must expose
the same classes and dispatcher specifications without import cycles or duplicate
registry entries.

Host acceptance must cover event-loop and owner-thread behavior, embedded and
standalone use of the same API, multiple views, stop/restart, and late signals.
Timeout and cancellation guarantees depend on the released dependencies that
implement them; local patches and private wheels cannot establish a public
dependency guarantee. Report untested host versions and unavailable licenses as
remaining acceptance limits.

## Ownership validation

Run `vx just check-repository-links` for dependency-free checks of the actual
installer and self-update repositories, Python/npm/Cargo provenance, preserved
package identifiers, and active repository links. The check intentionally allows
historical design and changelog references, external projects, and the Codecov
association awaiting verification. Existing installer tests also check the
canonical release target. This scope does not require a native rebuild or a host
SDK.
