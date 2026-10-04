# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.12](https://github.com/try-auroraview/auroraview/compare/auroraview-v0.5.11...auroraview-v0.5.12) (2026-10-04)


### Bug Fixes

* **ci:** pin vx python patch and align the pinned vx version across CI ([#492](https://github.com/try-auroraview/auroraview/issues/492)) ([7da726c](https://github.com/try-auroraview/auroraview/commit/7da726ca3b593808e707072a306cf314eda0346a))

## [0.5.11](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.10...auroraview-v0.5.11) (2026-09-28)


### Features

* **contract:** add host-adapter and render-backend contracts ([a760fc8](https://github.com/loonghao/auroraview/commit/a760fc89aa853765fef202856ec4378a61d6d300))
* **dcc-mcp:** expose AuroraView as a DCC-MCP WebView adapter ([d378ea9](https://github.com/loonghao/auroraview/commit/d378ea9fd5851855ba6c81cde3fdb6e0b9ca4b24))
* host-agnostic parent/child IPC bridge and --parent-hwnd embedding ([#463](https://github.com/loonghao/auroraview/issues/463)) ([5d9e9a9](https://github.com/loonghao/auroraview/commit/5d9e9a97fd2182b31f0c83d2513c44940b8cdc66))
* **python:** add diagnostics() runtime report for host and thread triage ([14569c7](https://github.com/loonghao/auroraview/commit/14569c71031e19df39645d4c7b27bd0c27eab46c))


### Bug Fixes

* **ci:** link full llvm-tools set into vx toolchain for rust coverage ([200a382](https://github.com/loonghao/auroraview/commit/200a38240c120edecc7ca27e1a876b530d5d8b0f))
* **contract:** registry duplicate-name protection, no double probe, test-race fix ([#472](https://github.com/loonghao/auroraview/issues/472)) ([c511384](https://github.com/loonghao/auroraview/commit/c5113847fd50fedb99171bf0856c6ee72b4d0df6))
* **python:** isolate Qt binding probe failures in diagnostics() ([3582c9d](https://github.com/loonghao/auroraview/commit/3582c9da02fb16de373c2ee8d303923ee5ab32b5))
* **python:** isolate Qt binding probe failures in diagnostics() ([3582c9d](https://github.com/loonghao/auroraview/commit/3582c9da02fb16de373c2ee8d303923ee5ab32b5))
* **python:** isolate Qt binding probe failures in diagnostics() ([7f4ee98](https://github.com/loonghao/auroraview/commit/7f4ee9847e182e9d5fae2a894fdade776a0f6eca))
* release GIL during blocking event loop and close windows on drop ([#464](https://github.com/loonghao/auroraview/issues/464)) ([d70c7a6](https://github.com/loonghao/auroraview/commit/d70c7a6511d27e1bcf54ecf296ec029eef4d9ef3))
* route cross-thread close through the close channel and shorten CI ready timeout ([#466](https://github.com/loonghao/auroraview/issues/466)) ([f71aa85](https://github.com/loonghao/auroraview/commit/f71aa859c5499b0cb29a6e9899fbe690246f94b3))


### Documentation

* consolidate agent instructions into a single AGENTS.md ([3c06d8e](https://github.com/loonghao/auroraview/commit/3c06d8eee81d39f81b4129b7530ba8a961f699c0))
* **rfc:** add RFC 0019 pluggable backend and host adapter contract, aligned to auroraview-contract ([#462](https://github.com/loonghao/auroraview/issues/462)) ([9ab258d](https://github.com/loonghao/auroraview/commit/9ab258d6e1c41180e600dfbf017f3b3c48972a0f))

## [0.5.10](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.9...auroraview-v0.5.10) (2026-07-02)


### Bug Fixes

* bind loop variable in Maya demo event handler ([0b0e6ad](https://github.com/loonghao/auroraview/commit/0b0e6ada96148779a2b96c69924afe2e0a1c749d))
* export set_window_class_null_background to fix clippy error ([0b84224](https://github.com/loonghao/auroraview/commit/0b842242f5a8a78348879e85a6196eb7242b849a))
* install llvm-tools-preview in llvm-cov-install recipe ([9a5c97b](https://github.com/loonghao/auroraview/commit/9a5c97b03484843eca1dbeb7deb7714717f940f9))
* make event loop management idempotent and add cleanup path ([4c4fca0](https://github.com/loonghao/auroraview/commit/4c4fca0fb4cc686a2adc174dc8844d70cf601a94))
* resolve Windows E2E test failures from asyncio loop conflict ([b7a9b9c](https://github.com/loonghao/auroraview/commit/b7a9b9c878888ede9a795df52e7a7b91823a0cf7))
* use NULL brush for transparent WebView2 windows ([2b9c97c](https://github.com/loonghao/auroraview/commit/2b9c97c0d188b6657fa13f6672f97f72c2ab06dc))

## [0.5.9](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.8...auroraview-v0.5.9) (2026-06-16)


### Features

* add packed headless CLI mode (RFC 0018) ([d0061ff](https://github.com/loonghao/auroraview/commit/d0061ffde49e30880060557802703dbdc53b890c))
* add packed headless CLI mode (RFC 0018) ([#442](https://github.com/loonghao/auroraview/issues/442)) ([d0061ff](https://github.com/loonghao/auroraview/commit/d0061ffde49e30880060557802703dbdc53b890c))
* **cli:** add packed headless CLI mode foundations (RFC 0018 steps 1-4) ([10ff489](https://github.com/loonghao/auroraview/commit/10ff489d9a346a77f328aa13bdd707dee17b201c))
* **cli:** add packed headless CLI mode foundations (RFC 0018 steps 1-4) ([5b2fcbe](https://github.com/loonghao/auroraview/commit/5b2fcbe27c970b1bdca9c643f06cfcc684c4c2ad))
* **cli:** complete packed headless CLI mode (RFC 0018 steps 5-8) ([b5cfe93](https://github.com/loonghao/auroraview/commit/b5cfe934b90b44f9ff1c0e8ccb2a1dc4c9a057d5))
* **cli:** complete packed headless CLI mode (RFC 0018 steps 5-8) ([d11b5d9](https://github.com/loonghao/auroraview/commit/d11b5d916dc222f64d896fda87760da514235bdd))
* **examples:** add packed headless CLI demo (RFC 0018) ([dc6cb88](https://github.com/loonghao/auroraview/commit/dc6cb88fcdee902483070d3223cd954e76967d59))
* **examples:** add packed headless CLI demo (RFC 0018) ([90020b1](https://github.com/loonghao/auroraview/commit/90020b126e3b7a751a635d5245efd3519a490a84))
* write CLI .cmd shim for GUI-subsystem packed exe ([3d556a6](https://github.com/loonghao/auroraview/commit/3d556a6d81fde029e732c47b1f0b0c1c35d48142))
* write CLI .cmd shim for GUI-subsystem packed exe ([4f6ae3d](https://github.com/loonghao/auroraview/commit/4f6ae3d528eb1e05e9a0117e7afd23fe87aa897d))


### Bug Fixes

* **ci:** install llvm-tools-preview through vx for rust coverage ([17c5583](https://github.com/loonghao/auroraview/commit/17c558384a346e0b2cb09e7cf2551862ae6cd7ec))
* **ci:** symlink system llvm-profdata into vx toolchain for rust coverage ([#440](https://github.com/loonghao/auroraview/issues/440)) ([2ab27a4](https://github.com/loonghao/auroraview/commit/2ab27a4f010b6731a959d5a2cf15185a9775f159))
* **cli:** gate headless command lookup on CLI exposure ([eacf042](https://github.com/loonghao/auroraview/commit/eacf04206d175083cbc7cc12cc2ab44b27e735d2))
* **cli:** gate headless command lookup on CLI exposure ([03efd04](https://github.com/loonghao/auroraview/commit/03efd04969027da559afb8d23b407aa669229ded))
* **cli:** use real exe name in packed CLI help/error text ([50f33ee](https://github.com/loonghao/auroraview/commit/50f33ee64c79c7800ae9315f743b7196113cb725))
* **cli:** use real exe name in packed CLI help/error text ([a97ef55](https://github.com/loonghao/auroraview/commit/a97ef5509d8459a3cc941af8b152b13b7bb12410))
* guard fix_webview2_child_windows against NULL hwnd ([65e0b49](https://github.com/loonghao/auroraview/commit/65e0b498ed9cfee279f76e0a0e5fa3799b99221a))
* **qt:** declare ctypes argtypes to avoid 64-bit handle overflow ([60f92f5](https://github.com/loonghao/auroraview/commit/60f92f54d3b374a987a6b0043cf6fe953c7e05be))
* **qt:** declare ctypes argtypes to avoid 64-bit handle overflow ([55a28e7](https://github.com/loonghao/auroraview/commit/55a28e7124236ea383bc9ee27b87389460adbd2e))
* **qt:** declare ctypes argtypes to avoid 64-bit handle overflow ([#435](https://github.com/loonghao/auroraview/issues/435)) ([60f92f5](https://github.com/loonghao/auroraview/commit/60f92f54d3b374a987a6b0043cf6fe953c7e05be))
* remove white border on standalone frameless windows ([05f09c4](https://github.com/loonghao/auroraview/commit/05f09c4fcb853fe32db31c06893d380974f48323))
* restore WebView2 subclass on destroy and warn on missing hwnd ([1c3609a](https://github.com/loonghao/auroraview/commit/1c3609a08b7f638c83f7e9d078c4c4362798ac4c))
* suppress __command_registered__ emit in headless CLI mode ([0c7baab](https://github.com/loonghao/auroraview/commit/0c7baab302f5ceffbbc1af055f0fe1ca2cf63aa0))
* suppress __command_registered__ emit in headless CLI mode ([601205f](https://github.com/loonghao/auroraview/commit/601205fecf4f42d22f1e11038e8b3a2aca8ec09a))
* update unsafe allowlist counts for window_style.rs and native.rs ([3fb2688](https://github.com/loonghao/auroraview/commit/3fb26889f6ac34317d51f412854e3b1b491219f5))
* update unsafe allowlist counts for window_style.rs and native.rs ([0d107d8](https://github.com/loonghao/auroraview/commit/0d107d86a8194f85dafdba9b1ad1c1b8ab15f777))
* update unsafe allowlist counts for window_style.rs and native.rs ([#437](https://github.com/loonghao/auroraview/issues/437)) ([3fb2688](https://github.com/loonghao/auroraview/commit/3fb26889f6ac34317d51f412854e3b1b491219f5))


### Code Refactoring

* **examples:** simplify maya echo demo typing and event wiring ([bd0003c](https://github.com/loonghao/auroraview/commit/bd0003ce11007bb05f0162e90853795fcb3fa127))
* **examples:** simplify maya echo demo typing and event wiring ([ba08949](https://github.com/loonghao/auroraview/commit/ba08949fccc8267fd6debe1263b5d5d244edff16))
* lift fix_webview2_child_windows into auroraview-core ([0a0a0ad](https://github.com/loonghao/auroraview/commit/0a0a0ad16d60997e200d21c49318373c316c5de3))
* **qt:** simplify ctypes signatures and drop dead child-window recursion ([8641d83](https://github.com/loonghao/auroraview/commit/8641d831b03ee742a0efac17cf98833526639bb5))


### Documentation

* add RFC 0018 packed exe headless CLI mode ([acfeed6](https://github.com/loonghao/auroraview/commit/acfeed67f284e567671e9b66279a1b97d0e11938))
* document packed headless CLI mode and Windows .cmd shim ([60091e0](https://github.com/loonghao/auroraview/commit/60091e049464d9e623e5cca797737b02084c5308))
* document packed headless CLI mode and Windows .cmd shim ([3bc69d9](https://github.com/loonghao/auroraview/commit/3bc69d983079708206523a642b5c0adcda70a1fa))
* **examples:** translate packed_cli_demo strings to English ([9210ad7](https://github.com/loonghao/auroraview/commit/9210ad782f4365d941c5d57abd7adcaaf7d17b42))
* **examples:** translate packed_cli_demo strings to English ([7888cb4](https://github.com/loonghao/auroraview/commit/7888cb4b6038bce383421f332b5016200123c6cb))

## [0.5.8](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.7...auroraview-v0.5.8) (2026-05-28)


### Bug Fixes

* **auroraview-protect:** migrate test suite to rand 0.10 API ([4c3e382](https://github.com/loonghao/auroraview/commit/4c3e382b9e31ddd3cbb08de91e21f0c8816ec918))


### Code Refactoring

* **auroraview-pack:** reformat checksum method chains ([228dcae](https://github.com/loonghao/auroraview/commit/228dcaee1eb6c04c1b86b0095215c4a163c241bd))

## [0.5.7](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.6...auroraview-v0.5.7) (2026-05-25)


### Bug Fixes

* isolate Playwright sync startup for CDP tests ([222b784](https://github.com/loonghao/auroraview/commit/222b784092a85ad331e53318145aa2aacce1e766))
* isolate Playwright sync startup for CDP tests ([ee547fe](https://github.com/loonghao/auroraview/commit/ee547fe6f8ab96086e5be591e0653550e737423c))

## [0.5.6](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.5...auroraview-v0.5.6) (2026-05-25)


### Features

* add --no-capture-file-drop flag and harden flag pair resolver ([1aae05c](https://github.com/loonghao/auroraview/commit/1aae05c2d718aae11e9652bba7123c59dcd63cbb))
* **browser:** hard-disable capture_file_drop in multi-tab Browser mode ([410f2e6](https://github.com/loonghao/auroraview/commit/410f2e662cc9eb098354a56ab7369c28f2113944))
* **cli:** tri-state capture-file-drop on run ([1dc9d98](https://github.com/loonghao/auroraview/commit/1dc9d9883f5ec4a39b35aeb0904c3c74be292dd3))
* **core:** add noop drag-drop sink and attach helper ([27ddb52](https://github.com/loonghao/auroraview/commit/27ddb5230fb81bcea4af1f02804c00b1d69d8ef9))
* **python:** preserve capture_file_drop tri-state through to Rust binding ([e16634e](https://github.com/loonghao/auroraview/commit/e16634eea377213b56e103a09cf244248cb16e37))
* **python:** preserve capture-file-drop tristate ([39c29ce](https://github.com/loonghao/auroraview/commit/39c29ce13a2071a08ae47a523db8fcaa749a54c4))
* **python:** thread capture_file_drop through all WebView entry points ([6fed24e](https://github.com/loonghao/auroraview/commit/6fed24e7250a4c03a2d2be3acc5d766dc0e22de6))
* **rust:** expose capture_file_drop as Optional[bool] in PyO3 binding ([5639e95](https://github.com/loonghao/auroraview/commit/5639e955d0c74d990a8e8291d5c9b38a188e9f93))
* **webview:** unify drag-drop registration via attach_drag_drop_handler ([362e3eb](https://github.com/loonghao/auroraview/commit/362e3eb7d56ae523e9daa68adb99a9a3c51766fb))


### Bug Fixes

* **bindings:** pass capture_file_drop arg in PyDesktopConfig tests ([5691d3b](https://github.com/loonghao/auroraview/commit/5691d3b981ed5e492f1d6498ee8035fe624efd0d))
* **cli:** use cfg-gated panic instead of debug_assert in resolve_flag_pair ([8394f6b](https://github.com/loonghao/auroraview/commit/8394f6b270c85f2a928e4548067e5e8af9060520))
* **core:** prevent port collision in service_discovery CDP test ([670749e](https://github.com/loonghao/auroraview/commit/670749e91df0affb181422dc483d02c1af712d4e))
* **desktop:** warn-once on missing drag-drop sink ([4a6ac2d](https://github.com/loonghao/auroraview/commit/4a6ac2d76eb2c5e2e78e3807fbcd4455a54e3d45))
* **qt:** prevent DCC deadlock in WebView2 geometry sync ([1de8c75](https://github.com/loonghao/auroraview/commit/1de8c75a4f67d8babdcd12bc5ebbbc8650429a89))
* **qt:** replace assert with RuntimeError in lock release and add flag constants ([9bb6356](https://github.com/loonghao/auroraview/commit/9bb6356f6e1b7d1aa31bc6e9f690f59e59586d1a))
* **qt:** resolve CI failures on Python 3.7 Linux runners ([09b7b4c](https://github.com/loonghao/auroraview/commit/09b7b4c441ff1455bf5249d01432706b801004cc))


### Code Refactoring

* apply rustfmt and ruff formatting ([6a6ce68](https://github.com/loonghao/auroraview/commit/6a6ce68a013dc8f333a94f662365ec3425cafd91))
* clean up code style in qt integration modules ([9af754f](https://github.com/loonghao/auroraview/commit/9af754fbbfff1587da65ae5386a068061469bbbe))
* **cli:** extract resolve_flag_pair utility and inline drag-drop attachment ([294958d](https://github.com/loonghao/auroraview/commit/294958d35243abe567bf6cb225df42dfbef7120a))
* harden drag-drop pipeline and centralize shared utilities ([3cf255e](https://github.com/loonghao/auroraview/commit/3cf255e906a8c597062aedb52b6c4f76ec8b3624))
* introduce skip_drag_drop_capture helper and PackConfig::skeleton ([5f7c9f8](https://github.com/loonghao/auroraview/commit/5f7c9f86dd4cb8b14b4189ee040efd5581bd5c56))
* **ipc:** replace warn-once linear scan with exhaustive match ([24765ea](https://github.com/loonghao/auroraview/commit/24765ead06877e5fbc2b5f7c73532c4da1bc3a15))
* **ipc:** tighten PackedDragDropSink encapsulation and warn-once ([f5ff4b0](https://github.com/loonghao/auroraview/commit/f5ff4b0d042ce374d877dd8a3ec5d8e47932470d))
* **qt:** apply linter formatting and remove unused import ([5f5f999](https://github.com/loonghao/auroraview/commit/5f5f999acefd434a0b8fde3c988f9e2099adc91e))
* **qt:** guard Qt imports so pure-Python submodules stay importable ([adfe618](https://github.com/loonghao/auroraview/commit/adfe618b5ab8680c49392675057aff5e261c94fb))
* short-circuit DragDropEvent::Over in hot path ([583c0be](https://github.com/loonghao/auroraview/commit/583c0be83c8e20f2479a0dfb9aa07dece8f8096c))


### Documentation

* **rfc:** finalize 0013-0017 file-drop guide ([a8fe5a5](https://github.com/loonghao/auroraview/commit/a8fe5a551947f432a4ed14c2b6807992f2db30e3))
* standardize RFC filenames and update file-drop docs ([4c0e56d](https://github.com/loonghao/auroraview/commit/4c0e56d0a7f36b7444e48e858efe5abd7138f0ae))
* update llms.txt, CHANGELOG and add file-drop example ([b944fed](https://github.com/loonghao/auroraview/commit/b944fed193d394908725b72c77b29130d934b801))

## [0.5.5](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.4...auroraview-v0.5.5) (2026-05-24)


### Bug Fixes

* **ci:** increase CDP E2E timeouts and improve npm token guidance ([b67cda7](https://github.com/loonghao/auroraview/commit/b67cda7efc968ae48e769e4c6629d62cc9147148))
* **ci:** migrate npm publish from token-based to OIDC trusted publishing ([2070c87](https://github.com/loonghao/auroraview/commit/2070c877cec4e3ece9281750ecb621fd2ca5a46f))

## [0.5.4](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.3...auroraview-v0.5.4) (2026-05-23)


### Bug Fixes

* gate unsafe usage ([17774f6](https://github.com/loonghao/auroraview/commit/17774f6a6f436b3aea0d1e59b9adcb7a8e07a675))
* keep codecov checks informational ([11655fa](https://github.com/loonghao/auroraview/commit/11655faa12f25b163023e3c0e1c5a035affdd12f))
* repair ci wheel and release publishing ([9409eda](https://github.com/loonghao/auroraview/commit/9409edaa3af60ee414bf470e947eae42cfa59753))

## [0.5.3](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.2...auroraview-v0.5.3) (2026-05-22)


### Features

* **auroraview-extensions:** migrate RuntimeManager.message_handlers and uninstall_urls to DashMap ([6245c73](https://github.com/loonghao/auroraview/commit/6245c73d809f5726f2208a4a66c43bcf86b56c70))
* **auroraview-extensions:** migrate ScriptingManager.registered_scripts to DashMap ([6d7bfb6](https://github.com/loonghao/auroraview/commit/6d7bfb6134f520751e09a11c724448fcc64ed2b2))
* **core:** add deprecated decorator to event_emitter [auto-improve][done] ([9f82933](https://github.com/loonghao/auroraview/commit/9f8293364e2f8bf88ecb9d4debe73899182fb5ec))
* **extensions:** implement runtime API methods and fix clippy warnings ([3878b8d](https://github.com/loonghao/auroraview/commit/3878b8d25d1d8f3d2bbfe1791a363ec40d84bff0))
* **mcp-agui:** integrate AG-UI events for all MCP tools ([1ac09bb](https://github.com/loonghao/auroraview/commit/1ac09bbe07bec6291b46fd0e84b056455953fe9b))
* **mcp:** add Display impls for all public types ([c61d879](https://github.com/loonghao/auroraview/commit/c61d87924095b4d17eff233580e7afe4898f3d2e))
* **mcp:** add enable_oauth config field and simplified OAuth 2.0 implementation ([62f71ac](https://github.com/loonghao/auroraview/commit/62f71ac3616daec49cfc8d8b259322a6cae66343))
* **mcp:** add OAuth 2.0 endpoints to MCP server ([c8d445b](https://github.com/loonghao/auroraview/commit/c8d445b28c8c5e248934dc8faae72803aabca6c1))
* **mcp:** add rmcp auth + elicitation features (oauth2 5.0.0) ([321abb6](https://github.com/loonghao/auroraview/commit/321abb6bfe826bb4827d767229c71474e00a89f3))
* **mcp:** add update_cdp_endpoint() to WebViewRegistry ([3384acf](https://github.com/loonghao/auroraview/commit/3384acf88d00d7e3b3f18fd4570c53aacf687f45))
* **mcp:** expose update_cdp_endpoint to Python bindings ([95353ea](https://github.com/loonghao/auroraview/commit/95353eaf19344727a76b1692c2423db3ca3aeab9))
* **mcp:** implement real eval_js via CDP Runtime.evaluate ([7d5469c](https://github.com/loonghao/auroraview/commit/7d5469ca4e6b4e1ecb4d19112d3df00086bb1ee9))
* **mcp:** implement real screenshot via CDP ([4a27586](https://github.com/loonghao/auroraview/commit/4a275868636fdefcad1b18ed5b59ca7bc705bac6))
* **mcp:** re-enable MCP Server - add rmcp/axum/mdns-sd deps, export all modules, fix compilation ([b9a7284](https://github.com/loonghao/auroraview/commit/b9a72849092ca0fa2590c514b46bf61258277794))
* **mcp:** upgrade rmcp from 0.3.2 to 1.5.0 ([7cc3a39](https://github.com/loonghao/auroraview/commit/7cc3a393e5af05124760502bf948543933f28ba3))
* merge auto-improve to main ([#396](https://github.com/loonghao/auroraview/issues/396)) ([46a1708](https://github.com/loonghao/auroraview/commit/46a1708c1a3fc7962bb3a4629cc8cd5abe0f8d85))
* **ue:** add auroraview-ue crate with GameThread executor ([6c355b2](https://github.com/loonghao/auroraview/commit/6c355b28b9a611c9247cea912791239bf34308a6))
* **ue:** add Display impls for UeEmbedMode and UeWebViewConfig ([b136aab](https://github.com/loonghao/auroraview/commit/b136aaba7a74fd250a07056a95ecdcfd2419b5cb))


### Bug Fixes

* **browser:** isolate tests from persisted bookmarks on disk ([b138075](https://github.com/loonghao/auroraview/commit/b1380759a61bfa12910619b55924c89c1573e178))
* **build:** resolve compilation errors after merge with main ([6c0c6f5](https://github.com/loonghao/auroraview/commit/6c0c6f5fe8997346dbc7b1a1d2962394b77d9266))
* **ci:** handle PR comment 403 from fork PRs and missing issues permission ([1a38786](https://github.com/loonghao/auroraview/commit/1a387861d83d2fe0717399da487aaa6e099679e4))
* **ci:** resolve lint, encoding and test naming issues ([9dea400](https://github.com/loonghao/auroraview/commit/9dea400bc989512eb4ad75723ac58c8f51b22075))
* **ci:** restore desktop extension build ([0e0f993](https://github.com/loonghao/auroraview/commit/0e0f993499fd57de1c569ce94880bb4a75978763))
* **ci:** satisfy ruff and clippy ([2bbb712](https://github.com/loonghao/auroraview/commit/2bbb7124b317317f831256d8e3b64cd6c19df278))
* **cli-tests:** replace match-with-empty-arm with if let ([f433e38](https://github.com/loonghao/auroraview/commit/f433e38fca47f35dd6ba239f1b977be3830d8101))
* **clippy:** satisfy needless_borrows and deprecated lints ([b6a3984](https://github.com/loonghao/auroraview/commit/b6a39847aa1d5b0d4e477e4ae57396000698f7b4))
* **clippy:** suppress struct_excessive_bools in Cli struct ([db1b510](https://github.com/loonghao/auroraview/commit/db1b5107d20ce4b3c451f57f451973ac25fe567c))
* correct regressions from 2c39318 and 24e135b ([bc3643b](https://github.com/loonghao/auroraview/commit/bc3643b1115e5053635990dcbfdb7dc249c6b499))
* **doc:** fix Rustdoc warnings across multiple crates ([a33b38a](https://github.com/loonghao/auroraview/commit/a33b38ab8509aaa5feb4da3d9f580e47a25c8006))
* **doc:** suppress false-positive Rustdoc warning in ai-agent ([c23510f](https://github.com/loonghao/auroraview/commit/c23510f8fd798190f9fb47540d418f0cbe3bbc41))
* **doc:** suppress remaining Rustdoc warning in ai-agent ([77db3c5](https://github.com/loonghao/auroraview/commit/77db3c5588e12b595211de005ce4594434199ac1))
* **mcp-oauth:** add Default impl for OAuthStore, use strip_prefix ([0017e7c](https://github.com/loonghao/auroraview/commit/0017e7c5bc7b99e312020cdbb4d3ec513b7160ce))
* **mcp-oauth:** use aws_lc::DEFAULT_PROVIDER for CryptoProvider initialization ([32b555d](https://github.com/loonghao/auroraview/commit/32b555d36e11c7deb1918c95676906e78481dae8))
* **mcp-python:** add missing enable_oauth field to PyMcpConfigWrapper ([0d1e533](https://github.com/loonghao/auroraview/commit/0d1e5333e9e1cfd3dd0de4f4c30e9368887a6e82))
* **mcp:** fix clippy needless_continue in cdp.rs and doc_markdown in lib.rs ([bf0b7e5](https://github.com/loonghao/auroraview/commit/bf0b7e59c48d4942e0537a10138b45fc5db2ba98))
* **mcp:** fix compilation errors in auroraview-mcp crate ([b7bfcec](https://github.com/loonghao/auroraview/commit/b7bfcec4ed2b3bbe12db14b57b0e5ad38ef6760e))
* **mcp:** fix documentation warnings in lib.rs ([af5f905](https://github.com/loonghao/auroraview/commit/af5f90556d72bede2ee0e681977227bb6224082e))
* **mcp:** remove unused imports and fix clippy warnings ([9aa9529](https://github.com/loonghao/auroraview/commit/9aa9529206f9f45444977697f4a590fc58b8e130))
* **mcp:** suppress missing_errors_doc clippy warnings (crate-level) ([f44a7b8](https://github.com/loonghao/auroraview/commit/f44a7b85c241b28ae17b68916624e44c28cd1b71))
* prevent gallery backend crash ([cb7ce73](https://github.com/loonghao/auroraview/commit/cb7ce73b2983fa41c6be26160bcb487f855e5049))
* **py37:** import Literal from typing_extensions on Python 3.7 ([5280db0](https://github.com/loonghao/auroraview/commit/5280db05e64d57dd348ebf876a9b8e17f313890e))
* **python:** delegate EventTimer readiness checks to WebView.is_ready ([9b8569d](https://github.com/loonghao/auroraview/commit/9b8569d52af71f960749fbd0daaf2b53acadf038))
* **python:** guard process_events against missing core in packed mode ([abf14b4](https://github.com/loonghao/auroraview/commit/abf14b4d80a9256a8505a12e6cccde77e11f9d79))
* **qt:** keep EventTimer ticking when only the sync core is ready ([660d1ba](https://github.com/loonghao/auroraview/commit/660d1ba5ea867788bffb8680c513c87d65bbe8a9))
* skip docs preview comments for fork PRs ([68b11c1](https://github.com/loonghao/auroraview/commit/68b11c1a9eb2322482ddf5134c5efe5d71d3e5ff))
* **ue:** silence unused-import lint on linux clippy ([f54b702](https://github.com/loonghao/auroraview/commit/f54b70239425700e19432317097e173075edad79))
* **windows:** prevent host UI freeze and STA deadlock during WebView2 embedding ([7893beb](https://github.com/loonghao/auroraview/commit/7893bebf9452b20904780819b5b577fd532ebb5d))
* **windows:** unfreeze WebView2 cold-start STA pump ([8821255](https://github.com/loonghao/auroraview/commit/88212552488f991d6b729540e543fd3f49f71d42))


### Performance Improvements

* **bench:** add OAuthStore benchmarks to measure DashMap optimization ([c23e0f0](https://github.com/loonghao/auroraview/commit/c23e0f04d90c3b21a2a06dcb3634ff5d8740c5aa))
* **core:** replace RwLock&lt;HashMap&gt; with DashMap in WindowManager ([970a300](https://github.com/loonghao/auroraview/commit/970a300b6d71ec81de5ac78d3f52d1b0ba5e6d2b))
* **mcp-oauth:** replace RwLock&lt;HashMap&gt; with DashMap for better concurrency ([345717a](https://github.com/loonghao/auroraview/commit/345717a40d359b3cb23b454d1c11027d3f44532d))
* **mcp:** add WebViewRegistry benchmarks [auto-improve][done] ([f10327b](https://github.com/loonghao/auroraview/commit/f10327ba0a94250fa277ae49ecfbdee61e3fab72))
* **signals:** replace RwLock&lt;HashMap&gt; with DashMap in SignalRegistry ([8c1297f](https://github.com/loonghao/auroraview/commit/8c1297fdc3035e332c23b7d51afb20ec651cc571))


### Code Refactoring

* **mcp:** reuse dcc adapter contract ([b952f16](https://github.com/loonghao/auroraview/commit/b952f16fd43a1075afcdb8f932281b0eb25d78e3))


### Documentation

* add performance benchmark results [auto-improve][done] ([71577c3](https://github.com/loonghao/auroraview/commit/71577c301c2b3cac0114da6937d12f2e558a0029))
* **auto-improve:** update memory.md with iteration [#33](https://github.com/loonghao/auroraview/issues/33) progress [auto-improve][done] ([1ffcaae](https://github.com/loonghao/auroraview/commit/1ffcaae5d3fbcd9fb1d7d530eb488acbaad4da78))
* **auto-improve:** update memory.md with iteration [#7](https://github.com/loonghao/auroraview/issues/7) results ([d554574](https://github.com/loonghao/auroraview/commit/d55457419f21fd8861c33b4093d9b5226a526afd))
* **mcp:** add basic usage example [auto-improve][done] ([f014a8c](https://github.com/loonghao/auroraview/commit/f014a8cf7d5150cbeeb9db80db10cffb8f65f499))
* **mcp:** add comprehensive README for MCP Server ([459051b](https://github.com/loonghao/auroraview/commit/459051b940e940d702076d5eb877805d2329bf5b))
* **mcp:** add MCP Server documentation and README update [auto-improve][done] ([0d93519](https://github.com/loonghao/auroraview/commit/0d93519e34a55c25a0303b19d7d2f29ce1c94c36))
* record webview2 cold-start fixes in CHANGELOG and add PR draft ([1f20043](https://github.com/loonghao/auroraview/commit/1f20043905971ac58817d579e18f77a7ae92332c))
* sync PR draft and CHANGELOG with current branch scope ([dd15315](https://github.com/loonghao/auroraview/commit/dd153157a4f40be125ad77d7d1d09eb19019d14f))
* **ue:** add comprehensive README for UE integration ([51ee003](https://github.com/loonghao/auroraview/commit/51ee0032936171c7bf8ba313fb7d8ee8fbd28a01))

## [Unreleased]

### ⚠ BREAKING CHANGES

* **DCC: default `capture_file_drop` changed from `True` to `False`** (RFCs 0013 / 0015 / 0017).
  Previously, an `AuroraView` embedded in DCC hosts such as Maya / Houdini / Nuke / Blender
  would automatically take over OS drag-and-drop and forward it as `file_drop` IPC events.
  The default is now aligned with standalone / CLI / packed modes — no takeover, so the
  frontend can use HTML5 `dragover` / `drop` as usual.
  - **Impact**: DCC tools relying on `auroraview.on('file_drop', ...)` will stop receiving events.
  - **Migration**: explicitly pass `capture_file_drop=True` when constructing `AuroraView`:
    ```python
    super().__init__(parent=parent, capture_file_drop=True, ...)
    ```
  - **Example**: see [`examples/desktop_app_capture_file_drop.py`](./examples/desktop_app_capture_file_drop.py).
  - **Details**: see [`docs/zh/guide/file-drop.md`](./docs/zh/guide/file-drop.md).

### Features

* **drag-drop**: add `auroraview_core::builder::attach_drag_drop_handler` helper
  + `DragDropIpcSink` trait + `DispatchError`, unifying the 5 builder integration
  points (RFC 0015 §3.3). The `capture=false` path performs no `Arc::clone`; the
  `capture=true` path clones exactly once.
* **drag-drop**: add shared `auroraview_core::builder::NoopDragDropSink` and the
  `attach_drag_drop_handler` helper, eliminating duplicated definitions in
  `auroraview-browser` and `webview/tab_manager.rs`.
* **browser**: hard-disable `capture_file_drop` in multi-tab Browser mode (RFC 0016) —
  neither the controller nor any business tab ever attaches `with_drag_drop_handler`,
  avoiding the unrecoverable OS drag-and-drop state machine when multiple WebViews
  are stacked.
* **CLI**: `auroraview run` adds a one-way `--capture-file-drop` flag;
  `auroraview pack` adds the dual flags `--capture-file-drop` /
  `--no-capture-file-drop` (RFC 0015 §4.2).
* **packed runtime**: add `AURORAVIEW_CAPTURE_FILE_DROP` environment variable as
  an escape hatch, supporting case-insensitive `1/true/on/yes/enabled` ×
  `0/false/off/no/disabled` literals (RFC 0015 §4.3).
* **manifest**: add `[security].capture_file_drop: Optional[bool]`
  (RFC 0015 §4.1; `#[serde(default)]` keeps overlay binary compatibility,
  **no version bump required**).
* **Python**: `AuroraView(capture_file_drop=Optional[bool])` tri-state contract
  (RFC 0017). `None` / `True` / `False` are preserved all the way through to the
  PyO3 binding; `unwrap_or(false)` on the Rust side is the only allowed flatten point.

### Refactors

* **workspace**: pin `wry` (0.54.4) / `tao` (0.34.6) versions centrally in the
  root `[workspace.dependencies]` instead of in 5 different crate `Cargo.toml`
  files (RFC 0014), eliminating version-drift risk when upgrading wry.
* **ipc**: tighten encapsulation of `PackedDragDropSink` (pub fields → `new()`
  constructor); switch the `IpcRouter::dispatch` warn-once implementation from
  `DashSet<String>` to a fixed-size `(&'static str, AtomicBool)` array plus an
  exhaustive `match` over named statics — lock-free and allocation-free on the
  hot path.
* **desktop**: log warn-once when the drag-drop sink is missing, avoiding log
  spam.

### Documentation

* Add [`docs/zh/guide/file-drop.md`](./docs/zh/guide/file-drop.md) user guide
  (covers HTML5 ↔ IPC mutual exclusion, DCC migration, CLI / manifest / env-var
  merge precedence, and troubleshooting).
* Add RFC 0013 / 0014 / 0015 / 0016 / 0017 file-drop design document series.
* Add [`examples/desktop_app_capture_file_drop.py`](./examples/desktop_app_capture_file_drop.py)
  desktop IPC file-drop demo.

### Tests / CI

* `crates/auroraview-core/tests/builder_helpers_tests.rs`: 6 contract tests for
  `attach_drag_drop_handler` (smoke / clone-not-once /
  clone-exactly-once-dual / dispatch + Over filter / error swallowed /
  `Send + Sync` blanket).
* `crates/auroraview-pack/tests/manifest_tests.rs` + `config_tests.rs`:
  tri-state parsing of `[security].capture_file_drop` and the `from_manifest`
  mapping.
* `crates/auroraview-cli/tests/{pack_args_tests,pack_merge_rule_tests,packed_env_var_tests}.rs`:
  CLI flag parsing, merge-rule truth table, and the 4 env-var value classes
  (unset / truthy / falsy / invalid).
* `tests/python/unit/test_capture_file_drop_tristate.py` +
  `test_child_window_isolation.py` + the new
  `tests/python/integration/test_capture_file_drop_passthrough.py` plus a PyO3
  `_dump_capture_file_drop` test hook (RFC 0017 §4).
* `scripts/ci/check_capture_file_drop_defaults.py` +
  `check_browser_no_drag_drop_capture.py`: two static CI trip-wires wired into
  `vx just test` via `vx just ci-grep`.

### Added

* **windows**: `AURORAVIEW_WEBVIEW2_TIMEOUT_SECS` environment variable to
  override the WebView2 cold-start timeout. Value is interpreted as seconds
  (plain unsigned integer, no unit suffix). Defaults to 30s. Useful on slow
  hosts (CI containers, AV-heavy enterprise machines, first-run Edge install
  paths) where the default is not enough.

### Changed

* **windows**: `recv_with_pump` no longer busy-loops with `PeekMessageW` +
  `Sleep(1ms)`. It now uses `CoWaitForMultipleHandles` with
  `COWAIT_DISPATCH_CALLS | COWAIT_DISPATCH_WINDOW_MESSAGES`, letting the OS
  schedule the wait and avoiding several seconds of host-UI freeze during
  WebView2 cold start in DCC / Qt embeddings. The wait is now driven by a
  real auto-reset event signaled from the WebView2 builder callback (via
  `SetEvent`), so the waiter wakes up on demand instead of polling on a
  50 ms tick.
* **windows**: `apply_child_window_style` now drains pending Win32 messages
  scoped to the embedded HWND before / after each style mutation, and skips
  redundant `SetParent` calls when the parent already matches. After the
  `GWL_STYLE` / `GWL_EXSTYLE` mutations it now issues a side-effect-free
  `SetWindowPos(SWP_FRAMECHANGED)` so the new styles are committed to the
  NC frame even when the `SetParent` branch short-circuits.
* **python**: `EventTimer._is_core_ready` now delegates entirely to
  `WebView.is_ready` and no longer inspects `_core` / `_async_core`
  directly. Stub-compatibility, lock acquisition and dual-core readiness
  are all owned by `WebView.is_ready`, which removes the duplicated
  fallback path and its inconsistent stub-warning policy.

### Fixed

* **windows**: `subclass_for_zero_nc_area` released the `parking_lot::Mutex`
  before installing the new `WndProc`, fixing a deadlock where
  `SetWindowPos(SWP_FRAMECHANGED)` re-entered the same non-reentrant mutex
  via the synchronous `WM_NCCALCSIZE` dispatch.

## [0.5.2](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.1...auroraview-v0.5.2) (2026-04-25)


### Bug Fixes

* **python:** skip core event registration when _core is None in packed mode ([0867005](https://github.com/loonghao/auroraview/commit/086700547d1e9ab0edf0448c5ebb26406605ef08))


### Documentation

* refactor AGENTS.md as progressive map and add AI-facing docs ([#380](https://github.com/loonghao/auroraview/issues/380)) ([e60290a](https://github.com/loonghao/auroraview/commit/e60290a0740f13600b084e81dd713124c5b0c2b1))

## [0.5.1](https://github.com/loonghao/auroraview/compare/auroraview-v0.5.0...auroraview-v0.5.1) (2026-04-24)


### Bug Fixes

* **ci:** fix npm publishing and add DCC integration tests ([a03ead1](https://github.com/loonghao/auroraview/commit/a03ead16ea6af485f0d2bc48331c743a10a43224))

## [0.5.0](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.19...auroraview-v0.5.0) (2026-04-17)


### ⚠ BREAKING CHANGES

* remove packages/auroraview-mcp Python package (#365, part of #364)

### Features

* **mcp:** add crates/auroraview-mcp adapter skeleton over CDP (Phase 2 of [#364](https://github.com/loonghao/auroraview/issues/364)) ([113839d](https://github.com/loonghao/auroraview/commit/113839d02c34026dcf72a1f3d4c72768a0470502))
* remove packages/auroraview-mcp Python package ([#365](https://github.com/loonghao/auroraview/issues/365), part of [#364](https://github.com/loonghao/auroraview/issues/364)) ([6cf179a](https://github.com/loonghao/auroraview/commit/6cf179acfee746038ad621a81a32a24dd81dfbd9))

## [0.4.19](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.18...auroraview-v0.4.19) (2026-04-09)


### Bug Fixes

* **ci:** add libwayland-dev to test-plugins job for rfd 0.17 Linux support ([d136dfe](https://github.com/loonghao/auroraview/commit/d136dfe1185d4b3f88492a39a2a68a2c749be8a2))

## [0.4.18](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.17...auroraview-v0.4.18) (2026-04-06)


### Features

* **auto-improve:** squash 76 commits - perf, tests, cleanup, hot-reload, telemetry ([555bd0a](https://github.com/loonghao/auroraview/commit/555bd0a0132337f06082aa2feaaf6a519ea17052))
* **e2e:** integrate ProofShot + agent-browser for E2E testing ([9c604d7](https://github.com/loonghao/auroraview/commit/9c604d74f0c793b51816d69b1dbbe5cf54cd5ea7))
* **e2e:** integrate ProofShot + agent-browser for visual E2E testing and self-iteration ([636c6a7](https://github.com/loonghao/auroraview/commit/636c6a7c7e7199444c82c38d58633c0e0abfb321))
* **e2e:** integrate ProofShot + agent-browser for visual E2E testing and self-iteration ([#329](https://github.com/loonghao/auroraview/issues/329)) ([636c6a7](https://github.com/loonghao/auroraview/commit/636c6a7c7e7199444c82c38d58633c0e0abfb321))


### Bug Fixes

* **ci:** remove blank line in sdk-ci.yml heredoc causing SDK Ready false failure ([1e7d98c](https://github.com/loonghao/auroraview/commit/1e7d98c526ee1f80e979e620388aa4fecaa52337))
* **mcp:** apply ruff format to providers.py and telemetry.py ([c17a0ed](https://github.com/loonghao/auroraview/commit/c17a0ed1691c0c78beb3a62fb348c121195871b6))

## [0.4.17](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.16...auroraview-v0.4.17) (2026-03-28)


### Bug Fixes

* **ci:** resolve release E2E test failures ([e68c1f3](https://github.com/loonghao/auroraview/commit/e68c1f3df52565cf2d5ba6aed2f8e1ce828b097c))
* **ci:** use github.token instead of secrets in composite action ([7ecacbc](https://github.com/loonghao/auroraview/commit/7ecacbc79e7b151e3f092d6d90a62d197fa89cd9))
* update test expectations for default ports and SDK e2e navigation ([35e5f95](https://github.com/loonghao/auroraview/commit/35e5f957a1799d55a4d0090608d7dded73d9162b))

## [0.4.16](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.15...auroraview-v0.4.16) (2026-03-24)


### Bug Fixes

* **ci:** resolve release [#266](https://github.com/loonghao/auroraview/issues/266) failures (py37 wheel, SDK E2E, artifact versions) ([bd561d0](https://github.com/loonghao/auroraview/commit/bd561d0f771af960fc0d7109477c6eb6369c9c46))

## [0.4.15](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.14...auroraview-v0.4.15) (2026-03-23)


### Code Refactoring

* remove dead BackendType enum and WebViewBackend alias ([8acf68c](https://github.com/loonghao/auroraview/commit/8acf68c73994dc36e9de6aa6de72b94012cbba7c))

## [0.4.14](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.13...auroraview-v0.4.14) (2026-03-23)


### Code Refactoring

* code quality cleanup - fix metadata and remove dead code ([c785f8c](https://github.com/loonghao/auroraview/commit/c785f8c912a6fed7a695488b9a91420a19a30f6f))
* **deps:** replace once_cell with std::sync::LazyLock ([#287](https://github.com/loonghao/auroraview/issues/287)) ([ee5edff](https://github.com/loonghao/auroraview/commit/ee5edffb25143459003e0aa6727cbb57b59b22d2))
* improve code quality and robustness ([26fc05c](https://github.com/loonghao/auroraview/commit/26fc05cbc3d73b8522c26ff7b33ff221f576d2fe))
* remove dead code and audit allow(dead_code) suppressions ([1ebae0b](https://github.com/loonghao/auroraview/commit/1ebae0bb4081cdbcafedc7827a95c25f377d1346))
* remove flume dependency and dead metrics.rs ([19e94e8](https://github.com/loonghao/auroraview/commit/19e94e87a61c049685678a6bca4765da4e97d969))
* remove unused IPC batch module and empty feature flag ([20c938a](https://github.com/loonghao/auroraview/commit/20c938ae169e5b76f4966e2f573f01ea8ddd327f))
* remove unused num_cpus dependency and empty feature flags ([d0f3097](https://github.com/loonghao/auroraview/commit/d0f3097752ac0a0a40bb00926668779921a46d45))
* replace eprintln! with tracing macros for structured logging ([1cb8a30](https://github.com/loonghao/auroraview/commit/1cb8a307628c40fcc687af4cc010bfa9cf15f8fa))
* replace unwrap() with safe response builders in protocol handlers ([071e4e1](https://github.com/loonghao/auroraview/commit/071e4e18d68da5ab78cc47d0aabeebc5d71d226d))
* slim tokio features from full to specific subset ([#298](https://github.com/loonghao/auroraview/issues/298)) ([6f14eee](https://github.com/loonghao/auroraview/commit/6f14eee89416fe766ed3afa725980856d34cf714))

## [0.4.13](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.12...auroraview-v0.4.13) (2026-03-22)


### Bug Fixes

* **ci:** resolve commitlint, Rust lifetime, and Python skip errors ([62c38fc](https://github.com/loonghao/auroraview/commit/62c38fc6931884ae027e391bb378ae00112e789e))
* **test:** resolve clippy approx_constant and rustfmt in IPC test ([e3432a2](https://github.com/loonghao/auroraview/commit/e3432a23fb373e9307cb799585bf0520e64e49d5))
* **test:** resolve import error and ruff format in IPC tests ([faff997](https://github.com/loonghao/auroraview/commit/faff9975d3904425d2a6ff552fb3dac209cc5ee8))

## [0.4.12](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.11...auroraview-v0.4.12) (2026-03-15)


### Bug Fixes

* **ci:** improve workflow shell compatibility ([d9fea19](https://github.com/loonghao/auroraview/commit/d9fea19d547034018486661bf08e818bc2618d83))

## [0.4.11](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.10...auroraview-v0.4.11) (2026-03-13)


### Bug Fixes

* **ci:** call Playwright directly in sdk recipe ([e936e22](https://github.com/loonghao/auroraview/commit/e936e22925af88646426557ac3baa461f1df837c))
* **ci:** call Playwright directly in sdk recipe ([14353b2](https://github.com/loonghao/auroraview/commit/14353b20e51611e1e013c888ddc0cb936bcf245f))
* **ci:** stabilize release publish workflow ([f8c5726](https://github.com/loonghao/auroraview/commit/f8c57269f75091d68e51a5634d9ca2631d70b9c8))
* stabilize release validation and ignore e2e artifacts ([c617d50](https://github.com/loonghao/auroraview/commit/c617d50cfddf5631d2cda2acb742369254e82339))

## [0.4.10](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.9...auroraview-v0.4.10) (2026-03-12)


### Features

* switch gallery e2e screenshots to playwright ([9718655](https://github.com/loonghao/auroraview/commit/97186555d9c7dc35b45cf59e275f06eb05ddbbd2))


### Bug Fixes

* **ci:** replace deprecated windows-2019, add bun setup, run vx ensure before build ([fb5cf31](https://github.com/loonghao/auroraview/commit/fb5cf31aabeb0be9f43906a9feb39deeb48c658b))

## [0.4.9](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.8...auroraview-v0.4.9) (2026-03-01)


### Features

* add telemetry stack and migrate pre-commit to vx prek ([9a1deee](https://github.com/loonghao/auroraview/commit/9a1deeeb3dbb260654d8b089fb6da5dd0abb3e49))
* **pack:** add vx-only dependency mode and auto vx ensure ([0b376ae](https://github.com/loonghao/auroraview/commit/0b376ae5cad89cabc99d32c61c60abd2e975a820))


### Bug Fixes

* **gallery:** restore installExtensionFromUrl hook wiring ([f287723](https://github.com/loonghao/auroraview/commit/f287723605678ff1ca18b944acaaa1b07b66afcf))
* **pack:** stream python standalone download to avoid size limit ([0b0b499](https://github.com/loonghao/auroraview/commit/0b0b4997d560230aee74da759cdfc74aaf7d545a))
* **pack:** stream vx/downloader responses to avoid body limits ([490d5b8](https://github.com/loonghao/auroraview/commit/490d5b8da329612d78ca79e178d232c7813f6f33))
* **pack:** use ureq for downloads, fix vx release URL pattern ([53f449f](https://github.com/loonghao/auroraview/commit/53f449f12f8e82c5aabd693345b0bb79f3671b2d))
* **py:** add telemetry fallback for environments without native core ([dde251b](https://github.com/loonghao/auroraview/commit/dde251bfaf1160b8458c40ca951e02e1b4a78f67))
* skip _core.pyd check in packed mode & feat: add auroraview-telemetry crate ([adf0457](https://github.com/loonghao/auroraview/commit/adf0457973a425cb1b9ee5321ae87e6a23e59830))


### Code Refactoring

* **pack:** use vx to manage rcedit instead of manual download ([e694b53](https://github.com/loonghao/auroraview/commit/e694b53bf0346048bb41885122fe790e697f5c4d))

## [0.4.8](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.7...auroraview-v0.4.8) (2026-02-08)


### Bug Fixes

* add publishConfig for scoped npm package and enhanced diagnostics ([259232d](https://github.com/loonghao/auroraview/commit/259232d8fd4eee0542d1448a59ebd29a18fb1d12))


### Documentation

* update CI pipeline documentation with release workflow details ([4ad760b](https://github.com/loonghao/auroraview/commit/4ad760bf51dafa975a9dac64270413234afc0bda))

## [0.4.7](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.6...auroraview-v0.4.7) (2026-02-08)


### Bug Fixes

* resolve dependency API breakage for ureq 3.x and image 0.25 ([a004497](https://github.com/loonghao/auroraview/commit/a0044977d6405551d634a1504e7d50d811e4ef1a))

## [Unreleased]

### Added

* **deps**: update `dcc-mcp-core` from v0.13.2 to v0.14.23
  * New features: `DccDispatcher`, cross-DCC main thread scheduling, `HostAdapter` base class
  * Improved Python 3.7/3.8 compatibility
  * Fixed gateway dynamic capability routing logic

### Fixed

* **security**: fix 47 Dependabot security vulnerabilities (20 high, 21 medium, 6 low)
  * Updated npm dependencies: `@playwright/test`, `@types/node`, `@types/react`, `@vitest/coverage-v8`, `serve`, `tsup`, `typescript`, `vitest`, `vue`
  * Updated Rust dependencies: `cargo update` to lock compatible versions
  * Updated Python dependencies: `uv lock --upgrade` (17 packages)
  * Fixed transitive dependency `postcss` (CVE-2026-41305)
  * Added `"ignoreDeprecations": "6.0"` to `tsconfig.json` (fixed TypeScript 6.0 deprecation)
* **code quality**: resolve ruff warnings (F841, SIM117, I001, F401)
  * Removed unused variable `history` in `agent.py`
  * Merged nested `with` statements in `test_agent.py` (4 occurrences)
  * Organized imports and removed unused imports
## [0.4.6](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.5...auroraview-v0.4.6) (2026-02-08)


### Features

* **api:** auto-enable window API in create_webview() ([8442374](https://github.com/loonghao/auroraview/commit/8442374c42aae886af941d5454c687cf3df837f4))
* **sdk:** add feature detection and window management APIs ([b1da6e2](https://github.com/loonghao/auroraview/commit/b1da6e29b99cb0f1997695ac7ae0f13f923709b1))


### Bug Fixes

* add frontend assets build steps to CI workflows ([06a99fc](https://github.com/loonghao/auroraview/commit/06a99fc595a18a992c14027f6b085b981f96e6fe))
* add frontend assets build to all CI workflows that compile Rust ([16e9e3e](https://github.com/loonghao/auroraview/commit/16e9e3ec66e40028f7d37cfd394e3e20661a90df))
* correct variable name in window_manager_tests.rs ([fe5efe3](https://github.com/loonghao/auroraview/commit/fe5efe329e6531e2270294b6a0243a38c207b692))
* keep _is_closing True after closeEvent ([d036df2](https://github.com/loonghao/auroraview/commit/d036df281002ca6ce099cba132a6dfedc551c3b5))
* make pack output executable name platform-aware ([b9f5d6a](https://github.com/loonghao/auroraview/commit/b9f5d6acb9bbff7f5fd3962dcecf95a17e1dc6ac))
* remove unnecessary `mut` from fs_scope in auroraview-cli ([58bc68a](https://github.com/loonghao/auroraview/commit/58bc68ab525b3214b8406aa4e02ee09d783d75ab))
* resolve CI failures - unused import and formatting ([89e1a48](https://github.com/loonghao/auroraview/commit/89e1a485ea44cf9ea35f073cb0e2201a2bc00cc4))
* resolve CI failures for TypeScript and submodule migration ([29ef24e](https://github.com/loonghao/auroraview/commit/29ef24e5b7e4d854d20569d12b02c0637c24c34f))
* resolve CI failures in auroraview-pack and standalone tests ([fe834f6](https://github.com/loonghao/auroraview/commit/fe834f69cca2bbfa6d3acd3b8ad2fd482467baac))
* resolve unit test failures in cookies and settings serialization ([b19ded5](https://github.com/loonghao/auroraview/commit/b19ded5b1f5b32a8e61d117af0e0aaf50baf5fab))
* **sdk:** fix TypeScript type conversion in features.ts ([42f44c6](https://github.com/loonghao/auroraview/commit/42f44c684f75fd0630017f8ae15e70920e011813))
* update repository URL and SDK package name references ([570cc03](https://github.com/loonghao/auroraview/commit/570cc039ae11e792cc2cc07a83d5ac6d5ac9c0f9))


### Code Refactoring

* migrate submodules to crates for simplified project structure ([d37cbdd](https://github.com/loonghao/auroraview/commit/d37cbddaee061077e469e09146554e972a608f48))
* restructure architecture and consolidate platform-specific implementations ([a51dd6d](https://github.com/loonghao/auroraview/commit/a51dd6dd49461d26841af3f38585968327046ec8))


### Documentation

* add llms.txt and llms-full.txt following llmstxt.org protocol ([29ce14a](https://github.com/loonghao/auroraview/commit/29ce14a77f411c3905f0375493b08b44690d75ce))
* update llms.txt with SDK features and window management APIs ([8ccfbb2](https://github.com/loonghao/auroraview/commit/8ccfbb25186dedaa628388d6bf4a3cd828cbde36))

## [0.4.5](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.4...auroraview-v0.4.5) (2026-01-20)


### Features

* **ai-agent:** add AI Agent + CDP integration documentation and examples ([6145f24](https://github.com/loonghao/auroraview/commit/6145f246a2ba9a3e93a1f9045609d813d51b37c2))
* **python:** add multi-panel and browser features, refactor testing module ([30f34e9](https://github.com/loonghao/auroraview/commit/30f34e9b44168fe586d389d2d19b262b88d89798))
* **rust:** add browser-related crates and multi-panel support ([bbc406c](https://github.com/loonghao/auroraview/commit/bbc406ca759bea3b96f427e8a820ab4cdd370fe2))


### Bug Fixes

* add _async_chat_and_emit method and remove sensitive logging ([ab6e62e](https://github.com/loonghao/auroraview/commit/ab6e62e544e3d9177af321abddbd030b98aeeb50))
* add cfg attributes for Windows-only variables and fix clippy lint ([77ad8a4](https://github.com/loonghao/auroraview/commit/77ad8a424a398da531ab92c7d9aad7674bb547f9))
* add cross-platform support for tab_manager event loop ([34051da](https://github.com/loonghao/auroraview/commit/34051da07c9e320d473613c6058e7264c8348bae))
* add missing parameters to QtWebView.create_deferred() ([2bd883f](https://github.com/loonghao/auroraview/commit/2bd883f3c1ff4be92f3995a227893fc2b1a91605))
* add UTF-8 encoding declaration and missing _window_id attribute ([f58e79d](https://github.com/loonghao/auroraview/commit/f58e79d00395a7704999781cc32df9c6fc547361))
* cross-platform compilation for auroraview-browser ([7547f7a](https://github.com/loonghao/auroraview/commit/7547f7aed932b764388151099f82e5825639d758))
* make header_height cross-platform and fix unused code warnings ([8838d49](https://github.com/loonghao/auroraview/commit/8838d498936ba124785f6cfdf2863605a2a28826))
* mark header_height as Windows-only in create_tab ([0930b86](https://github.com/loonghao/auroraview/commit/0930b86dc26d4d917430d8b3a724e77ab2cc2cfa))
* mock _load_tab_webview in test_navigate to avoid native lib dependency ([08014e4](https://github.com/loonghao/auroraview/commit/08014e45e2e1219af9a456b8666071ea133006a5))
* resolve dead links and clippy warnings ([43a90cb](https://github.com/loonghao/auroraview/commit/43a90cbe0c205cf8903962046f43f5b709807ec3))
* resolve lint errors in test and feature modules ([44c2708](https://github.com/loonghao/auroraview/commit/44c2708109389b200170d2016c6679a025e2482a))
* resolve ruff lint errors (B904, I001) ([393605c](https://github.com/loonghao/auroraview/commit/393605c77519713babfc4c60047b5d6b8b610f40))
* resolve unused variables and PyO3 API updates ([8a39227](https://github.com/loonghao/auroraview/commit/8a392276582932a98393cba613ba7cd585ef374a))
* SDK tests and Rust clippy lint issues ([c7edcbb](https://github.com/loonghao/auroraview/commit/c7edcbb163c59e9f895f98b1497a8fca21881c1b))
* skip test_showevent_auto_initialization in CI to avoid WebView2 crash ([a89a2af](https://github.com/loonghao/auroraview/commit/a89a2af5af0648c9c5d23565bef05bb2220a1fa6))
* update PyO3 0.27 FromPyObject API and fix Bool conversion ([bbecf9b](https://github.com/loonghao/auroraview/commit/bbecf9b6f0bd4bdbc5a1c569591307ad1ab96b20))
* use tempfile for bookmark tests to ensure isolated state ([4db928c](https://github.com/loonghao/auroraview/commit/4db928cfff7cea121e8c135b3289483ab3ff062f))
* use to_owned() for Borrowed to Bound conversion ([048040d](https://github.com/loonghao/auroraview/commit/048040d44d720a7272ad419440d25eb91d754e5c))


### Documentation

* fix chrome-devtools MCP config and add Playwright MCP integration ([b8e9fbd](https://github.com/loonghao/auroraview/commit/b8e9fbdd513d803934a9d4a56629f056ca14475b))

## [0.4.4](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.3...auroraview-v0.4.4) (2026-01-14)


### Bug Fixes

* improve Qt test cleanup to avoid access violations in CI ([eb741b4](https://github.com/loonghao/auroraview/commit/eb741b4b7c6685abaccab6031d990fe66054c7e3))
* resolve CI failures ([dd47a76](https://github.com/loonghao/auroraview/commit/dd47a761efede486ecadb8f70d63ce685e4750e7))

## [0.4.3](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.2...auroraview-v0.4.3) (2026-01-13)


### Features

* **api:** add unified WebView API with comprehensive documentation ([2efc72c](https://github.com/loonghao/auroraview/commit/2efc72cd49d5edcd000872f479408ee75e863863))


### Bug Fixes

* add missing parameters to WebView.create() and WebViewFactory.create() ([8c4260d](https://github.com/loonghao/auroraview/commit/8c4260da8aead8e2e3b816f0b1d62576fc8fc51f))
* correct mixin import path in test_unified_api.py ([efe80f9](https://github.com/loonghao/auroraview/commit/efe80f9724516223133ad7383071f796ecd50e9e))
* enable Qt tests on Windows CI ([a067af1](https://github.com/loonghao/auroraview/commit/a067af196292e100e8f1d2dc612fa5c246a8f599))
* enable Qt tests on Windows CI ([22221ad](https://github.com/loonghao/auroraview/commit/22221ad5bd2a7923b69deb9e19dc53f472aae05d))
* make pdoc generation optional and non-interactive ([15fb941](https://github.com/loonghao/auroraview/commit/15fb9414d4b76601b44b816ea716acb03296e03e))
* resolve merge conflicts in Qt test files ([eb1ddbd](https://github.com/loonghao/auroraview/commit/eb1ddbd70058799cce7b9e13f701478a2f1710ca))
* skip QtWebView instantiation tests when _core not available ([a9b056d](https://github.com/loonghao/auroraview/commit/a9b056ddd2389f9f2e9031507e4c4b8bf29eb491))


### Documentation

* add unified show method documentation ([b365e08](https://github.com/loonghao/auroraview/commit/b365e08629a3f9aa29051df9dfe7cf3f1c80d308))
* move Chinese unified-api to correct location ([23a958c](https://github.com/loonghao/auroraview/commit/23a958c95074ae7210fbd8abe519318ed1179b6c))

## [0.4.2](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.1...auroraview-v0.4.2) (2026-01-11)


### Features

* **backend:** implement WebViewBackend trait abstraction ([bced235](https://github.com/loonghao/auroraview/commit/bced2359771525d0063c058736dd9dea22f73a80))


### Bug Fixes

* escape all Arc&lt;Mutex&lt;WryWebView&gt;&gt; in docs to prevent HTML parsing errors ([117d865](https://github.com/loonghao/auroraview/commit/117d8654dc1367126c9e9bb8409b6940e590b2a7))
* resolve CI build errors in NativeBackend migration ([c711578](https://github.com/loonghao/auroraview/commit/c7115783b3621a02160f11cc77863df0daef8140))
* resolve CI test failure and docs build error ([f3ee3de](https://github.com/loonghao/auroraview/commit/f3ee3de64492f5547871813930dcb7db79b9e2ee))


### Code Refactoring

* **backend:** migrate NativeBackend to PyBindingsBackend trait ([2bdd9a1](https://github.com/loonghao/auroraview/commit/2bdd9a181cd990c242368eb4bcf1bc337622ece3))

## [0.4.1](https://github.com/loonghao/auroraview/compare/auroraview-v0.4.0...auroraview-v0.4.1) (2026-01-10)


### Bug Fixes

* **ci:** resolve concurrency deadlock in reusable workflows ([fc33719](https://github.com/loonghao/auroraview/commit/fc33719c6e073e587df52e9049dd823620f2ee72))

## [0.4.0](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.38...auroraview-v0.4.0) (2026-01-10)


### ⚠ BREAKING CHANGES

* Major architecture refactoring

### Features

* add _post_eval_js_hook support for Qt integration and testing ([233332f](https://github.com/loonghao/auroraview/commit/233332f29922584eb7540b2ce04b326a8b4e800e))
* add allow_file_protocol parameter for local resource loading ([37f2bea](https://github.com/loonghao/auroraview/commit/37f2bea513e6442a91629768f2c548a77836ebf6))
* add always-on-top window option ([0e7de4c](https://github.com/loonghao/auroraview/commit/0e7de4cbece4cec5043eb0f69fa53dd0e7ba8069))
* add apply_qt6_dialog_optimizations function ([434236d](https://github.com/loonghao/auroraview/commit/434236d23679307d419d61a138fc849fafb6260a))
* add Chrome Extension APIs support for AuroraView ([c482db2](https://github.com/loonghao/auroraview/commit/c482db24e724520300031b08602e387534e61f61))
* add CLI support for standalone WebView launcher ([983dc85](https://github.com/loonghao/auroraview/commit/983dc855c141f3b29da1ec600aabd282d0dd74c5))
* add cross-platform PlaywrightBrowser tests with CI browser installation ([d1dbc5b](https://github.com/loonghao/auroraview/commit/d1dbc5b6eb225dffe591dce40ccaa04e102267ee))
* add cross-platform Python tests (Linux, Windows, macOS) ([016ae05](https://github.com/loonghao/auroraview/commit/016ae05174adaf4b3e60cf53aa9a8960ae7d5de0))
* add file:// protocol support and reorganize test files ([226ce71](https://github.com/loonghao/auroraview/commit/226ce714490a8cdf28a8c02b50d4a954a384d1d2))
* add Gallery app with plugin system and API unification ([51307db](https://github.com/loonghao/auroraview/commit/51307dbab10a93adcffdfc6ffbea6814a913c939))
* add ipckit LocalSocket IPC support for high-performance subprocess communication ([7681610](https://github.com/loonghao/auroraview/commit/7681610bc90386f27e15f249e1cac63fab2cb8ea))
* add native file drop events and shell plugin enhancements ([6729a56](https://github.com/loonghao/auroraview/commit/6729a565cc0ffa0fe593b3a6708f1be42aab4c21))
* add prepare_html_with_local_assets utility function ([5952ca3](https://github.com/loonghao/auroraview/commit/5952ca3a2195b735b49eb435bb6396c0f4d2eaa0))
* add Python 3.7 support with separate non-abi3 builds ([bfcc0c8](https://github.com/loonghao/auroraview/commit/bfcc0c8c373d41a4587ee6f38a2bfb4914e4ac35))
* add Qt5/Qt6 compatibility layer and diagnostics ([acf9fe8](https://github.com/loonghao/auroraview/commit/acf9fe846ae044fe8d332322b511eb4179faa9e6))
* add window effects APIs (click-through, vibrancy) ([b44dd31](https://github.com/loonghao/auroraview/commit/b44dd315bfc68a4d8018cb202da79437ded26736))
* add window maximization and file protocol support ([9c09855](https://github.com/loonghao/auroraview/commit/9c0985597fad4cd537c6cb6cad363c9a42a8dd74))
* add window maximization when width/height is 0 ([930da84](https://github.com/loonghao/auroraview/commit/930da8408ba7b5829d9afa339b293a769c23707c))
* add xvfb support for headless UI tests in CI ([5eaf136](https://github.com/loonghao/auroraview/commit/5eaf136100f0d929ba630a41664951095c9629b7))
* **aurora-protect:** add hybrid encryption for Python bytecode protection ([f8f5701](https://github.com/loonghao/auroraview/commit/f8f57012b5b1d966f46c4599ce3bafb39d1d2f7f))
* auto-convert relative paths to auroraview:// protocol and add always_on_top ([66fc2a1](https://github.com/loonghao/auroraview/commit/66fc2a1a4a20c50cea53168a1c1e68f639e0eeaf))
* **child-window:** add unified child window system for examples ([95cf437](https://github.com/loonghao/auroraview/commit/95cf437c7b8c7120fa27c137d23461fa68590b42))
* **ci:** add package-isolated CI pipelines ([c9aa915](https://github.com/loonghao/auroraview/commit/c9aa9155c81721ff86793d1db3641e120cfadd3a))
* **cli:** add install scripts for auroraview-cli ([cba8def](https://github.com/loonghao/auroraview/commit/cba8def363a83e7eb09d679341ca107d82e602c2))
* **cli:** add self-update command ([b5a26e4](https://github.com/loonghao/auroraview/commit/b5a26e4f736a35c2177ae0f6a290920b48fb0e08))
* **cli:** improve CLI experience and update documentation ([c03c261](https://github.com/loonghao/auroraview/commit/c03c261da90f66a47fdc5abc6b48da74311942dd))
* **docs:** auto-generate examples documentation from examples/ directory ([c33c259](https://github.com/loonghao/auroraview/commit/c33c259620e65b5ed91a9b6fb4b39364293b4e25))
* **dom:** add comprehensive DOM manipulation module ([20cb0fb](https://github.com/loonghao/auroraview/commit/20cb0fb2f89467e8d98cb87cb9fed750b4caead5))
* **dom:** add Rust-native DOM batch operations for high performance ([64ccb50](https://github.com/loonghao/auroraview/commit/64ccb5036bfa76581e88d0af0c5a3138d01a9df2))
* enhance gallery E2E screenshots with multi-page capture ([6cad8a9](https://github.com/loonghao/auroraview/commit/6cad8a91dd736fff14a1c5de2153ee06423c6d60))
* enhance test coverage and IPC benchmarks ([8a994d1](https://github.com/loonghao/auroraview/commit/8a994d1dbc04afb7e5f6497990f47dd766be8ecd))
* expose Rust CLI utilities to Python for enhanced functionality ([bc96ed5](https://github.com/loonghao/auroraview/commit/bc96ed55cb5d1b13b0f7c6e223179f2e025be2ea))
* floating toolbar and MCP RFC ([4236e40](https://github.com/loonghao/auroraview/commit/4236e405730dc318269a5fa152e2396c3e49d7d5))
* **gallery:** add GSAP animations and floating toolbar examples ([2ccea7d](https://github.com/loonghao/auroraview/commit/2ccea7d2328be72d52d3fc3bc48ba55e5f793bbf))
* **gallery:** dependency installer with white theme ([5852ad0](https://github.com/loonghao/auroraview/commit/5852ad059f0f82d2560875d6ccdb3ff62ebd2b55))
* implement desktop events with plugin system integration ([f60d2c7](https://github.com/loonghao/auroraview/commit/f60d2c7c4f663ff96ba560c3ec147c333b212178))
* implement IPC emit and async callback mechanisms ([8ff92ce](https://github.com/loonghao/auroraview/commit/8ff92ce6d021200fec8c3f051a1ee7214e3bde98))
* implement vx packed dependency bootstrap system ([ccdccb5](https://github.com/loonghao/auroraview/commit/ccdccb517b5d97e47a69b23514f14482a605c3f4))
* improve DCC mode HWND handling and reduce log noise ([ef43cfd](https://github.com/loonghao/auroraview/commit/ef43cfd49674dec0d9e4591152de7b6231741cce))
* **ipc:** add IpcChannel Python client and comprehensive E2E tests ([7189ce9](https://github.com/loonghao/auroraview/commit/7189ce9cfdd9af96328f358c8e288d56b0d63663))
* **mcp:** implement AuroraView MCP Server (RFC-0001 Phase 1) ([43078eb](https://github.com/loonghao/auroraview/commit/43078eb5a05f1fddba934710d8ca58c8e0a0087f))
* **mcp:** implement Phase 2 Gallery integration tools ([5ae7cc8](https://github.com/loonghao/auroraview/commit/5ae7cc850bf0eaedbe6cf0fee0fc863b59333c52))
* **mcp:** implement Phase 3 DCC support tools ([a6691dd](https://github.com/loonghao/auroraview/commit/a6691dd71f20fcf90c1525a8a0201452f066610d))
* migrate all Rust tests to rstest integration tests ([085e524](https://github.com/loonghao/auroraview/commit/085e52480132f773c3ebdb1e142eb3de4b397c7e))
* migrate all unit tests to rstest framework ([5d0ec35](https://github.com/loonghao/auroraview/commit/5d0ec35a8985d0d872ab5235de931ce0b72fd11d))
* migrate IPC and HTTP discovery tests to rstest integration tests ([20a6c61](https://github.com/loonghao/auroraview/commit/20a6c61a69b435b8db922338bb3b148437c4e60a))
* optimize standalone mode with loading screen and unified event loop ([5975b79](https://github.com/loonghao/auroraview/commit/5975b790a0eb2bfc4e88dca5dc6ebedec08845c0))
* **pack:** add automatic Python dependency collection ([6430170](https://github.com/loonghao/auroraview/commit/64301703ce1c8624483e09bcae7520a115846611))
* **pack:** add custom window icon support for title bar and taskbar ([70b8e57](https://github.com/loonghao/auroraview/commit/70b8e572f6821d9c8770800ce19765b55a574ba6))
* **pack:** add hooks.collect support for bundling examples ([4e4a893](https://github.com/loonghao/auroraview/commit/4e4a893f046047bf9cb5bed05a6b43781d098937))
* **pack:** add standalone Python runtime bundling strategy ([906aec4](https://github.com/loonghao/auroraview/commit/906aec4389aae4fb047376b92254b6f87675139d))
* **pack:** add standalone Python runtime bundling strategy ([6c914ef](https://github.com/loonghao/auroraview/commit/6c914ef88511d9bafb640a091d83f37d48dd75ad))
* **pack:** add Windows resource editor for icon and subsystem modification - Add resource_editor.rs with rcedit integration for icon/version info - Implement native PE header modification for subsystem (GUI/Console) - Fix rcedit argument order and add file size validation - Move resource modifications before overlay write (rcedit compatibility) - Update packer flow: resources -&gt; subsystem -&gt; overlay - Add EventLoopProxy import fix in desktop.rs - Update gallery pack config with correct icon paths ([f136bfb](https://github.com/loonghao/auroraview/commit/f136bfbd7b8cf5e4ea7f70bf05ca3d080dcf60e9))
* **pack:** complete MVP for auroraview-pack and auroraview-cli crates ([72811de](https://github.com/loonghao/auroraview/commit/72811de66c277e69fe0ddad92ad6b5b721d2f9e3))
* **packed:** show loading screen while waiting for Python backend ([b3efaec](https://github.com/loonghao/auroraview/commit/b3efaec017614b5ab6cc18ff2ba11db39cd4cb59))
* **pack:** unified icon config with auto format conversion ([e63f27f](https://github.com/loonghao/auroraview/commit/e63f27fdf1c8466e21166615c7ff1cf10aebee0e))
* **qt:** improve embedded WebView geometry sync and window styling ([ae091e9](https://github.com/loonghao/auroraview/commit/ae091e9dc6a01f7c6e989e8fcb83c8dcd6a004d0))
* refactor architecture - migrate core modules to auroraview-core crate ([2085d94](https://github.com/loonghao/auroraview/commit/2085d94fe9a26cc25909f105d890dd360c949b7e))
* **signals:** add Qt-inspired signal-slot event system ([373b93d](https://github.com/loonghao/auroraview/commit/373b93dbf6feaaf22d5896294c3b34e72ff8e3af))
* support Windows absolute paths in auroraview:// protocol ([1fd4431](https://github.com/loonghao/auroraview/commit/1fd4431776f5c0a487474130cdfa96365abe22a4))
* **testing:** add DOM-based testing framework ([d7e8227](https://github.com/loonghao/auroraview/commit/d7e8227a1af601d2e0a6e7b173fe6b37757cf28f))
* **testing:** add Edge WebDriver support for E2E testing ([f14907b](https://github.com/loonghao/auroraview/commit/f14907b81f36bc83be8142d95184e1fe09c78439))
* **testing:** add Midscene bridge JS injection via Rust assets ([eb41d93](https://github.com/loonghao/auroraview/commit/eb41d9327895d868cdbb7cb2875642b273bf2103))
* **testing:** add PlaywrightBrowser for Playwright-based UI testing ([3988d1a](https://github.com/loonghao/auroraview/commit/3988d1aafc977f426e5f222216c9e97aef8c61c7))
* **thread-safety:** add DCC thread-safe utilities and WebView dcc_mode support ([1b2e3c3](https://github.com/loonghao/auroraview/commit/1b2e3c3ecda68257bcb4dff4ba3307f9f7de8dbd))
* upgrade windows crate to 0.62 ([4667a8f](https://github.com/loonghao/auroraview/commit/4667a8f163e18e0272e0d13fabe254872d401653))
* **utils:** add thread dispatcher for DCC main thread execution ([796a592](https://github.com/loonghao/auroraview/commit/796a592ca9aac92f248af182914f8da6e42340c1))


### Bug Fixes

* add __future__ annotations for Python 3.9 compatibility ([cb04732](https://github.com/loonghao/auroraview/commit/cb04732181ff902d2af927b0bdf237af189f35aa))
* add Cargo.lock to ensure reproducible builds ([63b2420](https://github.com/loonghao/auroraview/commit/63b2420256eb9b39b90154831f1c1ad37b479e5e))
* add cfg guards for Windows-only code paths ([458a89f](https://github.com/loonghao/auroraview/commit/458a89f3c42e936e454caf30162a36b57d20468d))
* add cfg(windows) for platform-specific imports ([93d13d4](https://github.com/loonghao/auroraview/commit/93d13d4e8f16e1174023fd69c5ce0893505faf07))
* add cfg(windows) to WindowStyleHints.decorations field ([5388db0](https://github.com/loonghao/auroraview/commit/5388db03f1fc5ade0d3732eaa19cf680bdfefeaf))
* add conditional compilation for test imports on Windows-only tests ([7f8b6ad](https://github.com/loonghao/auroraview/commit/7f8b6adf3c36391e03518daa878021622b02712d))
* add libxdo-dev dependency for Linux builds and fix dead_code warning ([8e3620f](https://github.com/loonghao/auroraview/commit/8e3620fcf471e19be19ae464d6af2e8a2b213bf8))
* add missing description field in CollectPattern test ([a8137aa](https://github.com/loonghao/auroraview/commit/a8137aae080bdcafd29d6858515c7adcd3488fe3))
* add missing serde_json::Value import in tests ([6877c45](https://github.com/loonghao/auroraview/commit/6877c455f259e459599b5b0fbec428f4ff16a7b9))
* add python-bindings feature to all maturin-args in CI workflows ([d79d8b8](https://github.com/loonghao/auroraview/commit/d79d8b806f7c364199bc7c417ba0f7cc51302b33))
* add python-bindings feature to Linux build in CI ([8fabe2c](https://github.com/loonghao/auroraview/commit/8fabe2c25fde84191c06ebe4b0ac51a3c7e19c81))
* add Qt system dependencies for Linux CI ([c521dd0](https://github.com/loonghao/auroraview/commit/c521dd04d3aabf1b735ce6f55162abff9d7ed658))
* add remote_debugging_port to Python WebView and fix CI vx action ([7004c55](https://github.com/loonghao/auroraview/commit/7004c55dcefc338085534a22a50f45e64eefa6de))
* add skipif decorator to test_api_injection_timing for Qt dependency ([e0c4181](https://github.com/loonghao/auroraview/commit/e0c4181c28df15c58398ad0da6e234a2822ae965))
* add test-helpers feature to Timer conditional compilation ([2f0d2cc](https://github.com/loonghao/auroraview/commit/2f0d2ccdc9bd7389854fa4804329694374df4861))
* add url-utils to python-bindings feature and export png_bytes_to_ico ([156a4d3](https://github.com/loonghao/auroraview/commit/156a4d35f3d5851f7d0b191b4e3ec67513e54091))
* add UTF-8 encoding declarations for Python 3.7 compatibility ([b24beb1](https://github.com/loonghao/auroraview/commit/b24beb14569ab64afa438bec4a54fe81f15364ca))
* add x-release-please-version tag to version fields ([f1d4ec0](https://github.com/loonghao/auroraview/commit/f1d4ec0ff09a4941bfeae4a0d6afa76f0062ad7d))
* address P0/P1 security and stability issues from code review ([189d649](https://github.com/loonghao/auroraview/commit/189d64914e1f28ad861de01fc115322bfe9529fd))
* always show window when show() is called explicitly ([f5d07a0](https://github.com/loonghao/auroraview/commit/f5d07a04c71420ea89ec0a7f9e067bc8cdef9f1e))
* auto-merge _core extension when bundling auroraview source ([090f18c](https://github.com/loonghao/auroraview/commit/090f18cefa997715cffbeb704986dd3d1d00ece0))
* **ci:** add npm rebuild rollup to fix native module issue in CI ([9fa7462](https://github.com/loonghao/auroraview/commit/9fa746240fd9e43e31514c219abddba525cf2a2d))
* **ci:** add npm retry and improve gallery artifact handling ([5624d22](https://github.com/loonghao/auroraview/commit/5624d221f6f78aa03fe05f4e0f1573e5a2d8708e))
* **ci:** add Python 3.13 support and fix Windows/macOS abi3 wheel builds ([0517854](https://github.com/loonghao/auroraview/commit/05178547ec5880a606686aa3db489470febc9e15))
* **ci:** add python-bindings feature for Qt tests build ([24080f7](https://github.com/loonghao/auroraview/commit/24080f7dcd26e4792b895e3b7e253a7138066a86))
* **ci:** align artifact names between build-wheels and release workflows ([dd6fd61](https://github.com/loonghao/auroraview/commit/dd6fd611977c9b2535c50f0860ac43c9495c3d8d))
* **ci:** build SDK before Gallery to resolve @auroraview/sdk/react import ([f99b10e](https://github.com/loonghao/auroraview/commit/f99b10e7fea32de7c15f301b480f3673b995489f))
* **ci:** correct PyPI artifact filtering to preserve sdist ([9ca85f1](https://github.com/loonghao/auroraview/commit/9ca85f18239f3179448c2445924af341a804c3d1))
* **ci:** correct Rust integration test names in CI configuration ([1efed3a](https://github.com/loonghao/auroraview/commit/1efed3a6edabc3091bd3e5e163222aabe4993250))
* **ci:** correct rust-toolchain action name ([d688621](https://github.com/loonghao/auroraview/commit/d6886217307bd9f7923d362a8078a545de95064e))
* **ci:** create venv for wheel installation test\n\n- Create .test-venv with specified Python version\n- Install wheel into venv instead of system\n- Verify imports using venv Python directly ([a02eea3](https://github.com/loonghao/auroraview/commit/a02eea3097d77c13c970ecba2a7c290eceff8785))
* **ci:** ensure webkit2gtk runtime libraries are available on Linux ([64ce0bf](https://github.com/loonghao/auroraview/commit/64ce0bf9e3625c239b32ee77da042f3d8e159927))
* **ci:** exclude auroraview-cli from rust coverage tests ([6474e8e](https://github.com/loonghao/auroraview/commit/6474e8e4856a064e1541dc9d7710871360c504d3))
* **ci:** fix npm and PyPI publish failures ([0dbf1db](https://github.com/loonghao/auroraview/commit/0dbf1db03aaed3a002e5a2688ca9200478b2ccc2))
* **ci:** fix SDK and Gallery build issues in release workflow ([1b95e28](https://github.com/loonghao/auroraview/commit/1b95e28302e2e0cca1c0dad7a8e5e753f7ee60ad))
* **ci:** improve sdk-ci concurrency to prevent hanging jobs ([b639d9f](https://github.com/loonghao/auroraview/commit/b639d9fd92d8f083e3281959c627d2977d82de65))
* **ci:** install dev dependencies for pytest and ruff\n\nAdd --extra dev to vx uv sync to install pytest, pytest-asyncio, pytest-cov, and ruff from optional-dependencies. ([29a40eb](https://github.com/loonghao/auroraview/commit/29a40eb0ea9713aa21f7f9f0196a4ca74462e5ac))
* **ci:** install Linux runtime libs unconditionally in gallery-pack ([fa4f19e](https://github.com/loonghao/auroraview/commit/fa4f19ea973e6b2ab83d7ceadf2edaaefed74c0d))
* **ci:** pass GITHUB_TOKEN and use venv executables for CLI test\n\n- Add GITHUB_TOKEN env var to vx uv venv/pip commands\n- Use .test-venv/bin/auroraview-mcp instead of global command\n- Windows uses .test-venv\\Scripts\\auroraview-mcp.exe ([3278d97](https://github.com/loonghao/auroraview/commit/3278d976f712add1469ecc28fa4f35dc978c633f))
* **ci:** preserve release-please changelog and add version to artifact names ([a6a338e](https://github.com/loonghao/auroraview/commit/a6a338ef5fc1271ffae068f9512b0203c9ea060e))
* **ci:** remove duplicate PR trigger from sdk-ci.yml ([446eb20](https://github.com/loonghao/auroraview/commit/446eb20fd28abf8a8727dd65239904966c7722ba))
* **ci:** rename sdk-assets artifact in build-gallery.yml to avoid conflict ([507320d](https://github.com/loonghao/auroraview/commit/507320d6172c14eb6a66a6037dc6a014d8578b53))
* **ci:** resolve artifact name conflicts between workflows ([fcf7f96](https://github.com/loonghao/auroraview/commit/fcf7f969786c234958eb497599d664598941c1e9))
* **ci:** resolve artifact name conflicts in release workflow ([5ed09f9](https://github.com/loonghao/auroraview/commit/5ed09f92112752f7b86c357aad4cecd93f0425e0))
* **ci:** resolve Python 3.7 test failures and unify GitHub Actions versions ([849f44b](https://github.com/loonghao/auroraview/commit/849f44b1d8c4febc16b3ad5bad840d653d98ab6c))
* **ci:** update gallery pack workflow for direct executable output ([9c1a27c](https://github.com/loonghao/auroraview/commit/9c1a27c0fd733535af1ace50f4609a096deada08))
* **ci:** update vx to v0.6.3 ([703bb9e](https://github.com/loonghao/auroraview/commit/703bb9ec46863793d685ad7f85da6044e5f4320e))
* **ci:** use 'uv run' instead of 'uvx' for pytest in mcp-ci ([f72fb9c](https://github.com/loonghao/auroraview/commit/f72fb9cbfbd705bf615f0495865cde9c39e74f24))
* **ci:** use clean npm install to fix rollup native module issue ([734ecb1](https://github.com/loonghao/auroraview/commit/734ecb1d1c9034c34e0e94de985fb2a8a6361ac7))
* **ci:** use correct Python executable path for uv venv ([8359367](https://github.com/loonghao/auroraview/commit/835936708a844179e75716a90d73cfefaddbef98))
* **ci:** use correct tag format auroraview-v* for release-please ([678f0fa](https://github.com/loonghao/auroraview/commit/678f0fa128be931e4e6f4c3fa2f2f34c6752d552))
* **ci:** use correct vx action path loonghao/vx@vx-v0.5.15 ([c3ec938](https://github.com/loonghao/auroraview/commit/c3ec9388dc4384b97bda2439d5104e720f44ec14))
* **ci:** use PySide6&gt;=6.8 for Python 3.13+ compatibility ([2aa8281](https://github.com/loonghao/auroraview/commit/2aa8281e5ca1a888b960dc7cfe773e62a8850434))
* **ci:** use separate cache keys for sccache vs non-sccache builds ([d3ce23c](https://github.com/loonghao/auroraview/commit/d3ce23c5e8ef870196915be1c9afdd9469142f16))
* **ci:** use shell: bash for rm -rf on Windows runners ([144486a](https://github.com/loonghao/auroraview/commit/144486a6b058067fb74ceecd2476a6cffb3375ff))
* **ci:** use unique concurrency group for sdk-ci to avoid deadlock ([6b0026b](https://github.com/loonghao/auroraview/commit/6b0026b76e87237c80a3ea90add2657c3685ea5e))
* **cli:** add timeout to command execution in info command ([02e719f](https://github.com/loonghao/auroraview/commit/02e719f7489941dd2a3bf5966da12e124d47e9af))
* **cli:** improve HTML rewriting to preserve absolute URLs ([6b2a21a](https://github.com/loonghao/auroraview/commit/6b2a21ab37e2846a967949d1871a4f3047756716))
* clippy field_reassign_with_default warning and enhance pre-commit ([6d52f4f](https://github.com/loonghao/auroraview/commit/6d52f4f1a673ecdedc7d4da943d544c096f016bb))
* **cli:** resolve clippy warnings in self_update ([e2af1bb](https://github.com/loonghao/auroraview/commit/e2af1bb2f1783f63ff026836fda7a12030e1ebf2))
* **cli:** use Path instead of PathBuf in extract_binary ([b87b1ac](https://github.com/loonghao/auroraview/commit/b87b1ac18dbb472f5d57b419d3d4ba05c23ec3eb))
* **cli:** use Stdio::null() in info command to prevent hanging ([7651e65](https://github.com/loonghao/auroraview/commit/7651e65a4ef4d15c9aa2977320bad83a4879c956))
* code formatting and Linux webkit2gtk runtime library ([b81848b](https://github.com/loonghao/auroraview/commit/b81848bfbe97ab46001a24ffbdcf4f940caa29ac))
* correct dev_tools default test assertion ([800b363](https://github.com/loonghao/auroraview/commit/800b363f43a387392d2ffed6e5a61a093a55c7e2))
* correct function name in cli_utils test ([402c629](https://github.com/loonghao/auroraview/commit/402c629e366ed72b9c50d30607aadf0f59bd0f45))
* correct PyList creation in batch processing ([38c2304](https://github.com/loonghao/auroraview/commit/38c23046fed50ae5e1daa96782e540081fd72436))
* correct Qt test paths in pr-checks.yml ([4b562a6](https://github.com/loonghao/auroraview/commit/4b562a619d1da0ffffaefe658c10446e803dd30d))
* correct test file paths in noxfile.py and README ([404b17a](https://github.com/loonghao/auroraview/commit/404b17ada4cbe5d14a9813fb479086ddf69de869))
* correct wry API and image crate import in CLI ([75c00ef](https://github.com/loonghao/auroraview/commit/75c00efd6acdafd651697ba5b51e3086df01a50a))
* **deps:** upgrade askama to 0.15 to resolve version conflict with warp ([53a2aeb](https://github.com/loonghao/auroraview/commit/53a2aebba86cf027adc3d2d57300cc16cd19e46b))
* disable sccache for Python 3.7 builds to avoid GLIBC incompatibility ([ae895f7](https://github.com/loonghao/auroraview/commit/ae895f789825e6608c18eacd173cfd711c93e9fc))
* **docs:** fix dead links and incorrect references ([7d73ac5](https://github.com/loonghao/auroraview/commit/7d73ac5f4c779da5cfce0c0bbbe5342fb08d6861))
* **docs:** install Qt6 system dependencies for PySide6 ([715c725](https://github.com/loonghao/auroraview/commit/715c7250807991a9047312d93af7c52d479f51d5))
* **docs:** install qtpy and PySide6 for pdoc generation ([7314b17](https://github.com/loonghao/auroraview/commit/7314b17895da1ec52028e9df6548848d8a72b8e6))
* **docs:** remove .md extension from internal links for VitePress ([a181e96](https://github.com/loonghao/auroraview/commit/a181e967f11554bb83f07f1bb3b1c347e7c3c057))
* **docs:** remove enablement parameter that requires admin permissions ([bc43219](https://github.com/loonghao/auroraview/commit/bc432196a2c229e96eea008a30c5b624640d3a04))
* **docs:** resolve dead links and add child module tests ([e56a02d](https://github.com/loonghao/auroraview/commit/e56a02db3cc07761f49f917e3973c8931c83d07f))
* **docs:** skip pdoc generation, use manual API docs ([01cef3e](https://github.com/loonghao/auroraview/commit/01cef3e521b1b36339e41a278a7e244f2b52d639))
* downgrade image to 0.24 and add Qt test dependencies ([b0e21dd](https://github.com/loonghao/auroraview/commit/b0e21dd68a8b7068057f42ff988248ca9887fab3))
* downgrade simd-json to 0.13 for Rust 1.80 compatibility ([3be5429](https://github.com/loonghao/auroraview/commit/3be542950a4feb1a1887b6d72185e9ce6cd99306))
* downgrade tao to 0.33 to avoid dlopen2 edition2024 requirement ([d8dfa15](https://github.com/loonghao/auroraview/commit/d8dfa158c0b5da693d345c0aec9f4d11be6f141e))
* emit returns False when no handlers registered ([d93921d](https://github.com/loonghao/auroraview/commit/d93921dbe2ded419202bb47663e57a1769c14b35))
* emit() returns False when no handlers registered ([bfe6cc5](https://github.com/loonghao/auroraview/commit/bfe6cc5f0b1512fb2aec567bb2f3748844da4b93))
* ensure all type annotations are Python 3.7+ compatible ([5dc07e1](https://github.com/loonghao/auroraview/commit/5dc07e1ff0f18b5b7f055625530d643ccb607c59))
* exclude qt module from pdoc generation in CI ([43c2698](https://github.com/loonghao/auroraview/commit/43c26983e648890f80a3a5070d7ea9219b65e407))
* exclude qt module from pdoc generation in CI ([a5a47dc](https://github.com/loonghao/auroraview/commit/a5a47dceb1f84e8d67d93cee92f1e5890aceca34))
* Fix Python 3.7 compatibility and CI workflow issues ([87a15e3](https://github.com/loonghao/auroraview/commit/87a15e33ced44a046bdcc929b45b154f14410dbb))
* format rust code and use urlparse for URL validation ([af3f2fb](https://github.com/loonghao/auroraview/commit/af3f2fbcb3f184b69f90195dc085a7036a7bba63))
* **gallery:** add ApiResult types and fix vite react resolution ([c739c13](https://github.com/loonghao/auroraview/commit/c739c132b11ade7bed6153194d3dc1f9f7d51e42))
* handle poisoned mutex gracefully to prevent panic on close ([a5a6cd3](https://github.com/loonghao/auroraview/commit/a5a6cd316566dad1b28ad9c7f8b1518e6895d8b3))
* implement pure Python CLI for uvx compatibility ([96f7c94](https://github.com/loonghao/auroraview/commit/96f7c9434ae51f52bc6cc50edccc4fa00727a450))
* import testing fixtures in conftest and skip UI tests in CI ([635368b](https://github.com/loonghao/auroraview/commit/635368b9b74318c6d086f23500acc87bd954613b))
* improve CI test stability ([b9f7ca3](https://github.com/loonghao/auroraview/commit/b9f7ca3300d14bee9d8a0035687e132b9143a54d))
* improve test compatibility for cross-platform and CI environments ([08c37a7](https://github.com/loonghao/auroraview/commit/08c37a79c810653ce7ba544cb376791c3ea0e23e))
* improve timer test stability on macOS CI ([8ebb6d9](https://github.com/loonghao/auroraview/commit/8ebb6d933f24c338d6cca840a19407c81a1d0d81))
* init_com_sta available on all platforms ([fbdfe56](https://github.com/loonghao/auroraview/commit/fbdfe562b6de5f871a82b02a0895c42823278363))
* is_fullstack() now checks for specific backend configs (python/go/rust/node) ([03be590](https://github.com/loonghao/auroraview/commit/03be590eb38def1d8808e57f7fd2e6792f6c7b9e))
* **justfile:** remove duplicate test-pack recipe ([3b2494e](https://github.com/loonghao/auroraview/commit/3b2494e2841466ab48408ff080640860c5c41aa9))
* make CI tests more robust for Windows and macOS ([0f303bf](https://github.com/loonghao/auroraview/commit/0f303bf8415857dbbf3f2fb7f0dbf2ff86007555))
* make ClientInfo public and allow dead_code for emit_event ([1eb2290](https://github.com/loonghao/auroraview/commit/1eb229054f613d7199b7046bdb7135633ac22312))
* make ctypes and wintypes imports platform-specific ([d76f452](https://github.com/loonghao/auroraview/commit/d76f4523994fad40a19be2d641d1436bd9704392))
* **mcp:** remove asyncio.run() wrapper for mcp.run()\n\nFastMCP's run() is synchronous and handles async internally.\nUsing asyncio.run() causes 'ValueError: a coroutine was expected'. ([1bf6b2c](https://github.com/loonghao/auroraview/commit/1bf6b2cd0fedf81231d6df2901d742b9c8d7d7c8))
* mock run_standalone instead of WebView in CLI tests ([584ec21](https://github.com/loonghao/auroraview/commit/584ec2196292b5e184de07a08178bbfcfdcd6343))
* only download wheel artifacts for PyPI publish, exclude CLI binaries ([bf0c0fd](https://github.com/loonghao/auroraview/commit/bf0c0fd46b71c4ce1a2ca47e855eabae30542ba3))
* only include core modules without third-party deps for pdoc ([1fb640b](https://github.com/loonghao/auroraview/commit/1fb640bcff0e14187c683b5ceb8d77fdf2b42830))
* **packed:** register API methods dynamically from Python handlers ([90e3410](https://github.com/loonghao/auroraview/commit/90e34106778231fce6ceea1b6a004914f3e52495))
* **pack:** execute before_build commands and fix output_dir path resolution - Add before_build command execution in CLI pack command - Run before_build commands in manifest directory (base_dir) - Fix output_dir to be resolved relative to base_dir - This fixes the issue where dist directory was not created because before_build was not executed ([35c3201](https://github.com/loonghao/auroraview/commit/35c32014fef9c6711002d47855f3f93497a4301b))
* **pack:** fix icon_path variable shadowing in PackConfig::from_manifest ([417f5db](https://github.com/loonghao/auroraview/commit/417f5dbc08eb05fe0550b4d68a73e6a11f79cf90))
* pin dlopen2 to 0.8.1 to avoid edition2024 requirement ([9454d5b](https://github.com/loonghao/auroraview/commit/9454d5b7659fdb51c8bbd781a4dcf6404d6a73d3))
* **plugins:** clear AURORAVIEW_PACKED for spawned processes ([497faf5](https://github.com/loonghao/auroraview/commit/497faf549c0b33f8463061d848d5dabddd32a0bb))
* Python 3.7 compatibility and format test file ([9295609](https://github.com/loonghao/auroraview/commit/92956097dde2d5b8499edb431fc67d6dca419fa3))
* Python 3.7/3.8 type annotation compatibility and timer test stability ([386367c](https://github.com/loonghao/auroraview/commit/386367c233bbf07dae51de9204c10dd7baa9e438))
* Qt placeholder tests to work in CI environments ([039cffe](https://github.com/loonghao/auroraview/commit/039cffe14d7d97e7b9200a870409c66a16a91fac))
* remove equals sign from mDNS metadata key in test ([4a95aee](https://github.com/loonghao/auroraview/commit/4a95aee53d59617dc117f990f1b5654f9594a6e9))
* remove race condition in port availability test ([ca091f3](https://github.com/loonghao/auroraview/commit/ca091f3c9df7a121404d931c2af21388b1b84edc))
* remove unused Duration import on non-Windows platforms ([541d9b7](https://github.com/loonghao/auroraview/commit/541d9b7ab41f4872bf4be6bbffe7244cc76789f2))
* remove unused import and add ruff select options to pre-commit ([e0d29af](https://github.com/loonghao/auroraview/commit/e0d29af46fc48a53f9b9be73fd1b3278dcdc4759))
* remove unused imports and variables in test_child.py ([f501b5c](https://github.com/loonghao/auroraview/commit/f501b5c89c0d044b679058cff3e84015d098645f))
* remove unused imports in test_headless_webview.py ([a15b48e](https://github.com/loonghao/auroraview/commit/a15b48e47986e90e5c215d916354ad35eb2b00b2))
* remove unused imports in test_headless_webview.py ([59ca770](https://github.com/loonghao/auroraview/commit/59ca770adcf4bb7e0ec5be0227c7d516a8ec335f))
* remove unused os import ([a579302](https://github.com/loonghao/auroraview/commit/a579302e3234ff1510697ec242e8acbca17270f6))
* remove unused sys import and add auto_show unit tests ([de413b4](https://github.com/loonghao/auroraview/commit/de413b45f10e1a58121c5fe88b4ddcf7c0269b56))
* remove unused variable and use vx in pr-checks ([e874b96](https://github.com/loonghao/auroraview/commit/e874b96ef3cbdb335dfb0f32f523ca8e2495045c))
* remove unused variable in browser-extension client ([e3e3822](https://github.com/loonghao/auroraview/commit/e3e38228e4955492f692e4be4379d4d5e5e56795))
* remove useless format! macro in benchmark ([4f6f558](https://github.com/loonghao/auroraview/commit/4f6f5583d18bd6638819464f7b3352a25da6c325))
* rename plugin_error to from_plugin to avoid clippy self_named_constructors ([900a3ee](https://github.com/loonghao/auroraview/commit/900a3ee0a87e05905f7f7a6098f970e93d33d6cb))
* rename unused loop variables to satisfy ruff B007 ([27afe25](https://github.com/loonghao/auroraview/commit/27afe251d4c4d243ddba0f3b696a476b50462e92))
* replace deprecated macos-13 runner with macos-latest cross-compile ([ebc0842](https://github.com/loonghao/auroraview/commit/ebc0842c4bc48730d72c86a56aa7865c3db0c216))
* resolve abi3-py38 conflict with Python 3.7 and CI test issues ([558df0f](https://github.com/loonghao/auroraview/commit/558df0f1e3bb318a277aaebdad7b2cc82f5f1340))
* resolve clippy warnings and CI ruff installation ([68c3e18](https://github.com/loonghao/auroraview/commit/68c3e185d69fa256ae3c8acf43c6506c82a00de5))
* resolve clippy warnings in auroraview-extensions ([d4a868a](https://github.com/loonghao/auroraview/commit/d4a868a8a5df11823491b7d105b346a57d4fb284))
* resolve clippy warnings in auroraview-pack ([42bdb09](https://github.com/loonghao/auroraview/commit/42bdb09983dfcdd0432d23b9c6c89acb8377240e))
* resolve cross-platform compilation errors for Linux CI ([652b4fa](https://github.com/loonghao/auroraview/commit/652b4fa710d2137f3af2f154d6e20753b86bcf9e))
* resolve dead links in zh/guide/getting-started.md ([d4d5e84](https://github.com/loonghao/auroraview/commit/d4d5e84ad12cd16ab5582baa65c80235e2142ece))
* resolve fmt issues and add tests for builder module ([c31b417](https://github.com/loonghao/auroraview/commit/c31b417637b49c998381c87472d6a1d46949c236))
* resolve get_hwnd returning None and add URL auto-normalization ([8a82b8e](https://github.com/loonghao/auroraview/commit/8a82b8e5fef53f267131c39b37968569fe0464a0))
* resolve lint and clippy warnings ([c15ad33](https://github.com/loonghao/auroraview/commit/c15ad33230e6455a3cff37e3a16ce4db8ce72230))
* resolve macOS abi3 wheel build issues ([3fa8d78](https://github.com/loonghao/auroraview/commit/3fa8d785e14d89cb1a48b861dffa4070f827a964))
* resolve macOS CI cache setup hashFiles errors ([5fc5968](https://github.com/loonghao/auroraview/commit/5fc59686275a6595a946342e784e4c7b5ee7c329))
* resolve Rust import conflicts and fix docs workflow path ([d9cc907](https://github.com/loonghao/auroraview/commit/d9cc907a245d55fd7ce90fe0840a541961fbb9a1))
* resolve test failure and clippy warnings ([00626e5](https://github.com/loonghao/auroraview/commit/00626e5be9de37d82a6687a743f2e936ac7d1669))
* resolve unit test collection errors on Linux CI ([3fe9007](https://github.com/loonghao/auroraview/commit/3fe9007771d91fd72c390c7ca5102fa8817322b5))
* resolve unused import and add more config tests ([4a25926](https://github.com/loonghao/auroraview/commit/4a2592601c484e4d9495e68f3952e7fb7ae58319))
* resolve unused imports and mut warnings for cross-platform build ([a39640d](https://github.com/loonghao/auroraview/commit/a39640d7a8e824a60447e64e337636aa5796583e))
* restore Windows-only imports and suppress hwnd warning ([553a461](https://github.com/loonghao/auroraview/commit/553a4612f9d255e0bb5bc3d4b500e6676e1500a7))
* rustdoc bare URLs and timer test flakiness on macOS CI ([56cc05b](https://github.com/loonghao/auroraview/commit/56cc05be4237dfc0ba5a919d6aa0200a39b1a53f))
* **sdk:** fix TypeScript type conversion error in attachPlugin ([1c6b397](https://github.com/loonghao/auroraview/commit/1c6b397fce1114be07b661673321c455605ba4b8))
* separate Python lint from ci-lint, add system deps earlier ([ca913da](https://github.com/loonghao/auroraview/commit/ca913dafe6017a8d4bfe535e11cc52e379584597))
* skip Browser tests on Linux CI and fix localStorage test ([df162ed](https://github.com/loonghao/auroraview/commit/df162eda8960c9b504d3be72df50430be25bf9df))
* skip Browser tests on macOS CI and fix actions/checkout version ([57fcd73](https://github.com/loonghao/auroraview/commit/57fcd732e266e69990332be33eff781a0c4903f9))
* skip PlaywrightBrowser native mode tests in CI ([cbd6e88](https://github.com/loonghao/auroraview/commit/cbd6e8811a1cfb5dc1af9c7a1fcec739b99f9304))
* skip WebView browser tests in CI on all platforms ([200d76c](https://github.com/loonghao/auroraview/commit/200d76c11e93f606b9206e7a1f8b7dfe44958186))
* specify modules explicitly for pdoc to exclude qt ([bfe41dc](https://github.com/loonghao/auroraview/commit/bfe41dca9cb3ef57edd2a6ba41ab579590b6342d))
* suppress dead_code warnings for platform-specific code ([9bd0235](https://github.com/loonghao/auroraview/commit/9bd0235f91f45ff03f3103da865faa8abccd1504))
* **test:** ignore IPC integration tests in CI coverage ([af090a1](https://github.com/loonghao/auroraview/commit/af090a18f6e7f1225b870ac68462b0a7f2602b77))
* **testing:** add missing testing modules and UTF-8 encoding ([8797ff4](https://github.com/loonghao/auroraview/commit/8797ff4f6f2386d8935230c9febfc9446dfef9ab))
* **testing:** add UTF-8 encoding declaration to all testing modules ([6c71c89](https://github.com/loonghao/auroraview/commit/6c71c89baa23724e29626c070e8d4332c22834ae))
* **testing:** remove unused variable tag in midscene.py ([94bf869](https://github.com/loonghao/auroraview/commit/94bf86977de67f38383fa9a8c87ec302b961c749))
* **test:** skip ready signal in test_processes_valid_request ([d362824](https://github.com/loonghao/auroraview/commit/d362824e767246de4a86ecc140ccca96057be600))
* **tests:** update tests for DOM API migration ([d55968e](https://github.com/loonghao/auroraview/commit/d55968e5c02aa82d2f9ef6270e05e7beae56ed11))
* **test:** use python3 on Linux for IPC integration tests ([949f9ce](https://github.com/loonghao/auroraview/commit/949f9cee123283a3b609fd910a1742e93189acf1))
* unused variable in shell plugin test ([a5964ba](https://github.com/loonghao/auroraview/commit/a5964ba8d74d5b5e5461a308c379ef70dbfee27a))
* unused variable in shell plugin test ([eddde5a](https://github.com/loonghao/auroraview/commit/eddde5aa37390d7fb21749f9d3e3d76e2f29e18b))
* update bom test to match fallback pattern in JS templates ([afc10ed](https://github.com/loonghao/auroraview/commit/afc10ed605de2004ce1e44e579203ba6257f6ba7))
* update documentation examples to use ignore instead of no_run ([c3842ea](https://github.com/loonghao/auroraview/commit/c3842ea76b13e71e7b2fb8a70561fc72db0a70ce))
* update field names to match IsolationConfig and BuildConfig structs ([3bfee13](https://github.com/loonghao/auroraview/commit/3bfee138550ff7a04e5a7e258feeaacc439effba))
* update file protocol tests to use valid HTTP URIs ([12ba42c](https://github.com/loonghao/auroraview/commit/12ba42ce80f30b8342036b67a00cf3b35f63426f))
* update generator_tests to use new Manifest structure ([0e0f9b0](https://github.com/loonghao/auroraview/commit/0e0f9b0296e82db87c73199e25f7ede4f944f618))
* update integration tests for CI compatibility ([d2ababf](https://github.com/loonghao/auroraview/commit/d2ababf242be5c45cd08ff490b448f0b08f36b84))
* update PyList API for PyO3 0.27.1 compatibility ([06afb93](https://github.com/loonghao/auroraview/commit/06afb93c6c36263c269d534bcc909436e81630c5))
* update SDK assets artifact name to use pr- prefix ([40d565b](https://github.com/loonghao/auroraview/commit/40d565bac81d00eb097aeb3aea19cf91aa9c49a9))
* update test to expect Python 3.11 as default version ([2d83a79](https://github.com/loonghao/auroraview/commit/2d83a79244e980c826d65be212e5730c901f93ea))
* update wry WebViewBuilder API from with_web_context to new_with_web_context ([4d30b05](https://github.com/loonghao/auroraview/commit/4d30b0530235c25f16d5cddec87d0bec02532524))
* use 'vx uv run pytest' instead of 'vx pytest' ([bc8157d](https://github.com/loonghao/auroraview/commit/bc8157d736c6b25b6f2b86ab820cca0b18c43bb9))
* use allow(unused_variables) instead of underscore prefix for platform-specific vars ([ecfa552](https://github.com/loonghao/auroraview/commit/ecfa55292fc999eeaf52e67b0c47294ef23ea92f))
* use empty PyList in ipc_batch integration test ([ff9d989](https://github.com/loonghao/auroraview/commit/ff9d989bcf31d478aec5d5abdeb304da6c7dea8d))
* use find_spec instead of import for playwright check ([5dfc9e0](https://github.com/loonghao/auroraview/commit/5dfc9e032008bcacaf75ad9e5c38fab304d709a1))
* use force=True in Locator tests to skip actionability checks ([c0dcd76](https://github.com/loonghao/auroraview/commit/c0dcd7638116dd7a9bc49d412a6e2d06613cd4b6))
* use localhost.local. for mDNS hostname to comply with spec ([def1d93](https://github.com/loonghao/auroraview/commit/def1d93545fe42e01095ceb4e88b2929cd2644e4))
* use native load_url for splash screen navigation ([d13fda0](https://github.com/loonghao/auroraview/commit/d13fda0cc7e10dd2ca7f13e7d33e18ee97393202))
* use Optional[] instead of | union syntax for Python 3.7 compatibility ([330759e](https://github.com/loonghao/auroraview/commit/330759e8c8955cb385802ace2d81f0fc07cd606e))
* use PyOxidizerBuilderConfig instead of PyOxidizerConfig in tests ([5be9148](https://github.com/loonghao/auroraview/commit/5be914843e72895aead2c20fe80b88fc024d3346))
* use std::slice::from_ref instead of clone for slice ([5e08053](https://github.com/loonghao/auroraview/commit/5e0805342957ad6c2441e5ebafb5cda06ee0cd07))
* use typing_extensions.Literal for Python 3.7 compatibility ([00519d1](https://github.com/loonghao/auroraview/commit/00519d18d7e633970ae7fb91ce8578d34341f50c))
* use Union syntax for Python 3.7-3.9 compatibility ([4d46cb2](https://github.com/loonghao/auroraview/commit/4d46cb2e78231f025ea5e6338430cc8043b0e484))
* use vx pytest instead of vx uv run pytest ([0070a2c](https://github.com/loonghao/auroraview/commit/0070a2c63306e486ede62be55e78baa2cea40d98))


### Performance Improvements

* add resize event throttling to maintain 60 FPS ([0b1f12d](https://github.com/loonghao/auroraview/commit/0b1f12d1a24cd9bbc382d3cc1f76c448dae0c4b1))
* **logging:** add conditional verbose logging for DCC environments ([004ffe1](https://github.com/loonghao/auroraview/commit/004ffe1f1b27e1854bb50c5d60bba3efea8118d6))
* **pack:** streaming decompression and WebView2 warmup ([f47b132](https://github.com/loonghao/auroraview/commit/f47b1322c3b902a1c9f19178bebf95958a8487cf))
* **qt:** optimize window style operations and fix initialization timing ([3fe3025](https://github.com/loonghao/auroraview/commit/3fe3025caf68d4a5928529b3abb670bf65067fe3))
* **warmup:** auto-start WebView2 warmup on module import ([4f04815](https://github.com/loonghao/auroraview/commit/4f04815d06bbf00962e5bdc6ee4aac68c19f74e8))


### Code Refactoring

* **ci:** unify PR and release build flows using build-wheel action ([2b0bc97](https://github.com/loonghao/auroraview/commit/2b0bc977a80f1c817bbf9cb0ec033d483d23386b))
* **ci:** use vx uvx instead of vx uv run ([72bd133](https://github.com/loonghao/auroraview/commit/72bd133edeb4a0ea8dca67cdb85096557dcd0b0e))
* clean up dead code and fix integration test imports ([39b116c](https://github.com/loonghao/auroraview/commit/39b116cbe68cf390e1530686816012506e37d997))
* **cli:** split packed.rs into modular structure ([95e48d4](https://github.com/loonghao/auroraview/commit/95e48d49b3bcf0ac298343b0ef3d8208a8d13dcc))
* extract more shared WebView builder logic to auroraview-core ([e782c86](https://github.com/loonghao/auroraview/commit/e782c865f33c03aa4cb6d76c8dc1adea873ac34a))
* extract shared WebView builder logic to auroraview-core ([19a02dd](https://github.com/loonghao/auroraview/commit/19a02dd551b25dd157eda4011ae218a7e424e6cc))
* implement dependency injection for EventTimer backends ([9b942a3](https://github.com/loonghao/auroraview/commit/9b942a367d58f2c712787bce96b9e1485a883de8))
* move in-block imports to module top level ([cb6cc3b](https://github.com/loonghao/auroraview/commit/cb6cc3b12fc82ebcbc5a7bea810bafd44bac27cc))
* **pack:** remove redundant api_methods static configuration ([b921222](https://github.com/loonghao/auroraview/commit/b9212224fdc680436bdc1ccf59726299756d36b5))
* **plugins:** modularize plugin system into separate crates ([74b34d5](https://github.com/loonghao/auroraview/commit/74b34d5ce4379074fdc2848d4f5ac9f3a5ff256c))
* remove debug file logging, use tracing instead ([497b6c4](https://github.com/loonghao/auroraview/commit/497b6c48394f695b2471e40290f745413b5fee1a))
* rename standalone to desktop with backward compatibility ([c43b6bb](https://github.com/loonghao/auroraview/commit/c43b6bb3611b89e3867e9349dd5b24c7eacd462a))
* reorganize tests into crate-specific directories and add visibility modifiers ([f1137a9](https://github.com/loonghao/auroraview/commit/f1137a9e820e2da52e9fbb78bbb0bc2355e93fa4))
* replace Playwright native tests with WebView2 Browser tests ([a658808](https://github.com/loonghao/auroraview/commit/a65880878ccee04f1fff446ce12c0ccdaa94848c))
* simplify EventTimer by removing DCC-specific implementations ([32fa559](https://github.com/loonghao/auroraview/commit/32fa559be544fbd771d3bac99c2f89346cad5cb5))
* **testing:** replace legacy testing modules with HeadlessWebView framework ([5e67fc7](https://github.com/loonghao/auroraview/commit/5e67fc7d7979263128102d8d292567a8ad425d07))
* update test files for cross-platform WebView testing ([8a393df](https://github.com/loonghao/auroraview/commit/8a393dfdfba4987c32e695828d6ce0d74d70bae1))
* update test_auroratest_browser.py for cross-platform WebView testing ([c2cfa72](https://github.com/loonghao/auroraview/commit/c2cfa726e94f40ee709e574e7f98829954dead3c))
* use official vx GitHub Action instead of manual install ([1b1a40b](https://github.com/loonghao/auroraview/commit/1b1a40b768a1495f085d1801116f30d9cdc5d843))
* use qtpy for QTimer import instead of direct Qt binding imports ([b2651f7](https://github.com/loonghao/auroraview/commit/b2651f7f621d18d2b7349d8a1b50f07d1944c477))


### Documentation

* add browser automation and example demos sections to testing framework guide ([20ae94a](https://github.com/loonghao/auroraview/commit/20ae94aae53cb81322fcbc8ab2578d3ec80dd591))
* add Chinese DCC documentation ([24c9fa2](https://github.com/loonghao/auroraview/commit/24c9fa27045ee32fdf74b358f6143501693eba80))
* add custom protocol best practices and security documentation ([e520924](https://github.com/loonghao/auroraview/commit/e5209246cb57c6806248eb7f1acc776b04e85ccc))
* add design philosophy, advanced usage, SDK guide and contributing docs ([7dffb9c](https://github.com/loonghao/auroraview/commit/7dffb9c9ea3f099d270f15b8e09fac7d2804e3a4))
* add JS-Python communication guide and improve coverage config ([89c350d](https://github.com/loonghao/auroraview/commit/89c350dd5eb268864db9c20e4032c07a6c70ca0e))
* add new features documentation (Gallery, System Tray, Floating Panels, Plugin System) ([87a9d2b](https://github.com/loonghao/auroraview/commit/87a9d2babad62252bbcff7cb54c37cd6d2981236))
* add pack example with custom icon and console hiding features ([7081466](https://github.com/loonghao/auroraview/commit/7081466a4e1d7fed57a69ac434e7bebded65557e))
* add project vision and motivation to homepage ([c550bc0](https://github.com/loonghao/auroraview/commit/c550bc005809497f15bb26c223ab673535629b96))
* add Python 3.7 Windows CLI workaround for uv/uvx ([ce92fd0](https://github.com/loonghao/auroraview/commit/ce92fd00d8726c7fa8f039b872d6dc7ba99ea993))
* add run_standalone examples for local resource loading ([2d8f254](https://github.com/loonghao/auroraview/commit/2d8f254fcceab156a18d91ef9e61204e03715ae5))
* add SDK README and fix GitHub Pages deployment ([a991acd](https://github.com/loonghao/auroraview/commit/a991acd0cfac056369340779df41245c5174ddc9))
* add Unreal Engine to navigation and improve threading documentation ([10abd88](https://github.com/loonghao/auroraview/commit/10abd88975741f63041f97cdad8a426e02ac1c1c))
* clarify three integration modes and add gallery screenshots ([5311cb2](https://github.com/loonghao/auroraview/commit/5311cb2a4746fd26feaedf66e19ecda857efc52a))
* **dcc:** add thread safety sections and Substance Painter integration ([c34ba1f](https://github.com/loonghao/auroraview/commit/c34ba1fbae2e07184328057bdc364b3138c2a5d3))
* deep comparison between AuroraView and PyWebView ([a958523](https://github.com/loonghao/auroraview/commit/a958523105fa16a98c0c7a597a04340a87164315))
* migrate to VitePress documentation site and add pack examples ([ed75901](https://github.com/loonghao/auroraview/commit/ed75901b5c3dc5bf87286604442aa3e5100367c7))
* update API examples and add llms.txt index file ([d441e69](https://github.com/loonghao/auroraview/commit/d441e696a0a552595e9254ee8356d252109d5528))
* update comparison with comprehensive DOM API section ([ce5c878](https://github.com/loonghao/auroraview/commit/ce5c878a275bf8eceaa3a3b1c34847f7cf35e86c))
* update Python version range to include 3.13 ([f5e2f63](https://github.com/loonghao/auroraview/commit/f5e2f63cf9188382e54adbbebbcab2833a35ca40))

## [0.3.38](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.37...auroraview-v0.3.38) (2026-01-08)


### Features

* **gallery:** dependency installer with white theme ([5852ad0](https://github.com/loonghao/auroraview/commit/5852ad059f0f82d2560875d6ccdb3ff62ebd2b55))
* **thread-safety:** add DCC thread-safe utilities and WebView dcc_mode support ([1b2e3c3](https://github.com/loonghao/auroraview/commit/1b2e3c3ecda68257bcb4dff4ba3307f9f7de8dbd))


### Bug Fixes

* **ci:** resolve Python 3.7 test failures and unify GitHub Actions versions ([849f44b](https://github.com/loonghao/auroraview/commit/849f44b1d8c4febc16b3ad5bad840d653d98ab6c))
* **ci:** use correct Python executable path for uv venv ([8359367](https://github.com/loonghao/auroraview/commit/835936708a844179e75716a90d73cfefaddbef98))


### Documentation

* **dcc:** add thread safety sections and Substance Painter integration ([c34ba1f](https://github.com/loonghao/auroraview/commit/c34ba1fbae2e07184328057bdc364b3138c2a5d3))

## [0.3.37](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.36...auroraview-v0.3.37) (2025-12-31)


### Documentation

* add project vision and motivation to homepage ([c550bc0](https://github.com/loonghao/auroraview/commit/c550bc005809497f15bb26c223ab673535629b96))

## [0.3.36](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.35...auroraview-v0.3.36) (2025-12-31)


### Bug Fixes

* add remote_debugging_port to Python WebView and fix CI vx action ([7004c55](https://github.com/loonghao/auroraview/commit/7004c55dcefc338085534a22a50f45e64eefa6de))
* exclude qt module from pdoc generation in CI ([43c2698](https://github.com/loonghao/auroraview/commit/43c26983e648890f80a3a5070d7ea9219b65e407))
* exclude qt module from pdoc generation in CI ([a5a47dc](https://github.com/loonghao/auroraview/commit/a5a47dceb1f84e8d67d93cee92f1e5890aceca34))
* only include core modules without third-party deps for pdoc ([1fb640b](https://github.com/loonghao/auroraview/commit/1fb640bcff0e14187c683b5ceb8d77fdf2b42830))
* rename unused loop variables to satisfy ruff B007 ([27afe25](https://github.com/loonghao/auroraview/commit/27afe251d4c4d243ddba0f3b696a476b50462e92))
* separate Python lint from ci-lint, add system deps earlier ([ca913da](https://github.com/loonghao/auroraview/commit/ca913dafe6017a8d4bfe535e11cc52e379584597))
* specify modules explicitly for pdoc to exclude qt ([bfe41dc](https://github.com/loonghao/auroraview/commit/bfe41dca9cb3ef57edd2a6ba41ab579590b6342d))
* use 'vx uv run pytest' instead of 'vx pytest' ([bc8157d](https://github.com/loonghao/auroraview/commit/bc8157d736c6b25b6f2b86ab820cca0b18c43bb9))
* use vx pytest instead of vx uv run pytest ([0070a2c](https://github.com/loonghao/auroraview/commit/0070a2c63306e486ede62be55e78baa2cea40d98))

## [0.3.35](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.34...auroraview-v0.3.35) (2025-12-31)


### Features

* **mcp:** implement Phase 3 DCC support tools ([a6691dd](https://github.com/loonghao/auroraview/commit/a6691dd71f20fcf90c1525a8a0201452f066610d))

## [0.3.34](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.33...auroraview-v0.3.34) (2025-12-30)


### Features

* **mcp:** implement Phase 2 Gallery integration tools ([5ae7cc8](https://github.com/loonghao/auroraview/commit/5ae7cc850bf0eaedbe6cf0fee0fc863b59333c52))


### Bug Fixes

* **ci:** update vx to v0.6.3 ([703bb9e](https://github.com/loonghao/auroraview/commit/703bb9ec46863793d685ad7f85da6044e5f4320e))
* **ci:** use correct vx action path loonghao/vx@vx-v0.5.15 ([c3ec938](https://github.com/loonghao/auroraview/commit/c3ec9388dc4384b97bda2439d5104e720f44ec14))
* **deps:** upgrade askama to 0.15 to resolve version conflict with warp ([53a2aeb](https://github.com/loonghao/auroraview/commit/53a2aebba86cf027adc3d2d57300cc16cd19e46b))


### Code Refactoring

* **ci:** use vx uvx instead of vx uv run ([72bd133](https://github.com/loonghao/auroraview/commit/72bd133edeb4a0ea8dca67cdb85096557dcd0b0e))

## [0.3.33](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.32...auroraview-v0.3.33) (2025-12-30)


### Features

* **cli:** add install scripts for auroraview-cli ([cba8def](https://github.com/loonghao/auroraview/commit/cba8def363a83e7eb09d679341ca107d82e602c2))
* **cli:** add self-update command ([b5a26e4](https://github.com/loonghao/auroraview/commit/b5a26e4f736a35c2177ae0f6a290920b48fb0e08))
* **mcp:** implement AuroraView MCP Server (RFC-0001 Phase 1) ([43078eb](https://github.com/loonghao/auroraview/commit/43078eb5a05f1fddba934710d8ca58c8e0a0087f))


### Bug Fixes

* **cli:** resolve clippy warnings in self_update ([e2af1bb](https://github.com/loonghao/auroraview/commit/e2af1bb2f1783f63ff026836fda7a12030e1ebf2))
* **cli:** use Path instead of PathBuf in extract_binary ([b87b1ac](https://github.com/loonghao/auroraview/commit/b87b1ac18dbb472f5d57b419d3d4ba05c23ec3eb))

## [0.3.32](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.31...auroraview-v0.3.32) (2025-12-30)


### Bug Fixes

* **ci:** preserve release-please changelog and add version to artifact names ([a6a338e](https://github.com/loonghao/auroraview/commit/a6a338ef5fc1271ffae068f9512b0203c9ea060e))

## [0.3.31](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.30...auroraview-v0.3.31) (2025-12-30)


### Features

* **utils:** add thread dispatcher for DCC main thread execution ([796a592](https://github.com/loonghao/auroraview/commit/796a592ca9aac92f248af182914f8da6e42340c1))


### Bug Fixes

* **docs:** remove .md extension from internal links for VitePress ([a181e96](https://github.com/loonghao/auroraview/commit/a181e967f11554bb83f07f1bb3b1c347e7c3c057))
* remove unused variable and use vx in pr-checks ([e874b96](https://github.com/loonghao/auroraview/commit/e874b96ef3cbdb335dfb0f32f523ca8e2495045c))


### Documentation

* add Chinese DCC documentation ([24c9fa2](https://github.com/loonghao/auroraview/commit/24c9fa27045ee32fdf74b358f6143501693eba80))

## [0.3.30](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.29...auroraview-v0.3.30) (2025-12-30)


### Features

* floating toolbar and MCP RFC ([4236e40](https://github.com/loonghao/auroraview/commit/4236e405730dc318269a5fa152e2396c3e49d7d5))
* **gallery:** add GSAP animations and floating toolbar examples ([2ccea7d](https://github.com/loonghao/auroraview/commit/2ccea7d2328be72d52d3fc3bc48ba55e5f793bbf))


### Bug Fixes

* add cfg(windows) to WindowStyleHints.decorations field ([5388db0](https://github.com/loonghao/auroraview/commit/5388db03f1fc5ade0d3732eaa19cf680bdfefeaf))
* **docs:** install Qt6 system dependencies for PySide6 ([715c725](https://github.com/loonghao/auroraview/commit/715c7250807991a9047312d93af7c52d479f51d5))
* **docs:** install qtpy and PySide6 for pdoc generation ([7314b17](https://github.com/loonghao/auroraview/commit/7314b17895da1ec52028e9df6548848d8a72b8e6))
* **docs:** skip pdoc generation, use manual API docs ([01cef3e](https://github.com/loonghao/auroraview/commit/01cef3e521b1b36339e41a278a7e244f2b52d639))


### Code Refactoring

* use official vx GitHub Action instead of manual install ([1b1a40b](https://github.com/loonghao/auroraview/commit/1b1a40b768a1495f085d1801116f30d9cdc5d843))

## [0.3.29](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.28...auroraview-v0.3.29) (2025-12-28)


### Features

* **testing:** add Midscene bridge JS injection via Rust assets ([eb41d93](https://github.com/loonghao/auroraview/commit/eb41d9327895d868cdbb7cb2875642b273bf2103))


### Bug Fixes

* format rust code and use urlparse for URL validation ([af3f2fb](https://github.com/loonghao/auroraview/commit/af3f2fbcb3f184b69f90195dc085a7036a7bba63))
* remove unused os import ([a579302](https://github.com/loonghao/auroraview/commit/a579302e3234ff1510697ec242e8acbca17270f6))
* **testing:** add missing testing modules and UTF-8 encoding ([8797ff4](https://github.com/loonghao/auroraview/commit/8797ff4f6f2386d8935230c9febfc9446dfef9ab))
* **testing:** add UTF-8 encoding declaration to all testing modules ([6c71c89](https://github.com/loonghao/auroraview/commit/6c71c89baa23724e29626c070e8d4332c22834ae))
* **testing:** remove unused variable tag in midscene.py ([94bf869](https://github.com/loonghao/auroraview/commit/94bf86977de67f38383fa9a8c87ec302b961c749))


### Documentation

* add browser automation and example demos sections to testing framework guide ([20ae94a](https://github.com/loonghao/auroraview/commit/20ae94aae53cb81322fcbc8ab2578d3ec80dd591))

## [0.3.28](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.27...auroraview-v0.3.28) (2025-12-28)


### Bug Fixes

* **docs:** fix dead links and incorrect references ([7d73ac5](https://github.com/loonghao/auroraview/commit/7d73ac5f4c779da5cfce0c0bbbe5342fb08d6861))


### Documentation

* add design philosophy, advanced usage, SDK guide and contributing docs ([7dffb9c](https://github.com/loonghao/auroraview/commit/7dffb9c9ea3f099d270f15b8e09fac7d2804e3a4))

## [0.3.27](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.26...auroraview-v0.3.27) (2025-12-28)


### Features

* add window effects APIs (click-through, vibrancy) ([b44dd31](https://github.com/loonghao/auroraview/commit/b44dd315bfc68a4d8018cb202da79437ded26736))
* **docs:** auto-generate examples documentation from examples/ directory ([c33c259](https://github.com/loonghao/auroraview/commit/c33c259620e65b5ed91a9b6fb4b39364293b4e25))


### Bug Fixes

* **ci:** remove duplicate PR trigger from sdk-ci.yml ([446eb20](https://github.com/loonghao/auroraview/commit/446eb20fd28abf8a8727dd65239904966c7722ba))
* **sdk:** fix TypeScript type conversion error in attachPlugin ([1c6b397](https://github.com/loonghao/auroraview/commit/1c6b397fce1114be07b661673321c455605ba4b8))
* suppress dead_code warnings for platform-specific code ([9bd0235](https://github.com/loonghao/auroraview/commit/9bd0235f91f45ff03f3103da865faa8abccd1504))


### Documentation

* clarify three integration modes and add gallery screenshots ([5311cb2](https://github.com/loonghao/auroraview/commit/5311cb2a4746fd26feaedf66e19ecda857efc52a))

## [0.3.26](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.25...auroraview-v0.3.26) (2025-12-27)


### Features

* add Chrome Extension APIs support for AuroraView ([c482db2](https://github.com/loonghao/auroraview/commit/c482db24e724520300031b08602e387534e61f61))
* **child-window:** add unified child window system for examples ([95cf437](https://github.com/loonghao/auroraview/commit/95cf437c7b8c7120fa27c137d23461fa68590b42))


### Bug Fixes

* **ci:** ensure webkit2gtk runtime libraries are available on Linux ([64ce0bf](https://github.com/loonghao/auroraview/commit/64ce0bf9e3625c239b32ee77da042f3d8e159927))
* **ci:** install Linux runtime libs unconditionally in gallery-pack ([fa4f19e](https://github.com/loonghao/auroraview/commit/fa4f19ea973e6b2ab83d7ceadf2edaaefed74c0d))
* code formatting and Linux webkit2gtk runtime library ([b81848b](https://github.com/loonghao/auroraview/commit/b81848bfbe97ab46001a24ffbdcf4f940caa29ac))
* **docs:** resolve dead links and add child module tests ([e56a02d](https://github.com/loonghao/auroraview/commit/e56a02db3cc07761f49f917e3973c8931c83d07f))
* make ClientInfo public and allow dead_code for emit_event ([1eb2290](https://github.com/loonghao/auroraview/commit/1eb229054f613d7199b7046bdb7135633ac22312))
* remove unused imports and variables in test_child.py ([f501b5c](https://github.com/loonghao/auroraview/commit/f501b5c89c0d044b679058cff3e84015d098645f))
* remove unused variable in browser-extension client ([e3e3822](https://github.com/loonghao/auroraview/commit/e3e38228e4955492f692e4be4379d4d5e5e56795))
* rename plugin_error to from_plugin to avoid clippy self_named_constructors ([900a3ee](https://github.com/loonghao/auroraview/commit/900a3ee0a87e05905f7f7a6098f970e93d33d6cb))
* resolve clippy warnings in auroraview-extensions ([d4a868a](https://github.com/loonghao/auroraview/commit/d4a868a8a5df11823491b7d105b346a57d4fb284))
* resolve test failure and clippy warnings ([00626e5](https://github.com/loonghao/auroraview/commit/00626e5be9de37d82a6687a743f2e936ac7d1669))
* restore Windows-only imports and suppress hwnd warning ([553a461](https://github.com/loonghao/auroraview/commit/553a4612f9d255e0bb5bc3d4b500e6676e1500a7))
* use allow(unused_variables) instead of underscore prefix for platform-specific vars ([ecfa552](https://github.com/loonghao/auroraview/commit/ecfa55292fc999eeaf52e67b0c47294ef23ea92f))

## [0.3.25](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.24...auroraview-v0.3.25) (2025-12-25)


### Code Refactoring

* **plugins:** modularize plugin system into separate crates ([74b34d5](https://github.com/loonghao/auroraview/commit/74b34d5ce4379074fdc2848d4f5ac9f3a5ff256c))

## [0.3.24](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.23...auroraview-v0.3.24) (2025-12-24)


### Features

* **cli:** improve CLI experience and update documentation ([c03c261](https://github.com/loonghao/auroraview/commit/c03c261da90f66a47fdc5abc6b48da74311942dd))


### Bug Fixes

* address P0/P1 security and stability issues from code review ([189d649](https://github.com/loonghao/auroraview/commit/189d64914e1f28ad861de01fc115322bfe9529fd))

## [0.3.23](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.22...auroraview-v0.3.23) (2025-12-23)


### Bug Fixes

* **docs:** remove enablement parameter that requires admin permissions ([bc43219](https://github.com/loonghao/auroraview/commit/bc432196a2c229e96eea008a30c5b624640d3a04))

## [0.3.22](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.21...auroraview-v0.3.22) (2025-12-22)


### Documentation

* add SDK README and fix GitHub Pages deployment ([a991acd](https://github.com/loonghao/auroraview/commit/a991acd0cfac056369340779df41245c5174ddc9))

## [0.3.21](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.20...auroraview-v0.3.21) (2025-12-22)


### Features

* **pack:** add custom window icon support for title bar and taskbar ([70b8e57](https://github.com/loonghao/auroraview/commit/70b8e572f6821d9c8770800ce19765b55a574ba6))
* **pack:** add Windows resource editor for icon and subsystem modification - Add resource_editor.rs with rcedit integration for icon/version info - Implement native PE header modification for subsystem (GUI/Console) - Fix rcedit argument order and add file size validation - Move resource modifications before overlay write (rcedit compatibility) - Update packer flow: resources -&gt; subsystem -&gt; overlay - Add EventLoopProxy import fix in desktop.rs - Update gallery pack config with correct icon paths ([f136bfb](https://github.com/loonghao/auroraview/commit/f136bfbd7b8cf5e4ea7f70bf05ca3d080dcf60e9))
* **pack:** unified icon config with auto format conversion ([e63f27f](https://github.com/loonghao/auroraview/commit/e63f27fdf1c8466e21166615c7ff1cf10aebee0e))


### Bug Fixes

* add missing description field in CollectPattern test ([a8137aa](https://github.com/loonghao/auroraview/commit/a8137aae080bdcafd29d6858515c7adcd3488fe3))
* **ci:** fix npm and PyPI publish failures ([0dbf1db](https://github.com/loonghao/auroraview/commit/0dbf1db03aaed3a002e5a2688ca9200478b2ccc2))
* is_fullstack() now checks for specific backend configs (python/go/rust/node) ([03be590](https://github.com/loonghao/auroraview/commit/03be590eb38def1d8808e57f7fd2e6792f6c7b9e))
* **pack:** execute before_build commands and fix output_dir path resolution - Add before_build command execution in CLI pack command - Run before_build commands in manifest directory (base_dir) - Fix output_dir to be resolved relative to base_dir - This fixes the issue where dist directory was not created because before_build was not executed ([35c3201](https://github.com/loonghao/auroraview/commit/35c32014fef9c6711002d47855f3f93497a4301b))
* **pack:** fix icon_path variable shadowing in PackConfig::from_manifest ([417f5db](https://github.com/loonghao/auroraview/commit/417f5dbc08eb05fe0550b4d68a73e6a11f79cf90))
* resolve clippy warnings in auroraview-pack ([42bdb09](https://github.com/loonghao/auroraview/commit/42bdb09983dfcdd0432d23b9c6c89acb8377240e))
* resolve dead links in zh/guide/getting-started.md ([d4d5e84](https://github.com/loonghao/auroraview/commit/d4d5e84ad12cd16ab5582baa65c80235e2142ece))
* resolve Rust import conflicts and fix docs workflow path ([d9cc907](https://github.com/loonghao/auroraview/commit/d9cc907a245d55fd7ce90fe0840a541961fbb9a1))
* update field names to match IsolationConfig and BuildConfig structs ([3bfee13](https://github.com/loonghao/auroraview/commit/3bfee138550ff7a04e5a7e258feeaacc439effba))
* update generator_tests to use new Manifest structure ([0e0f9b0](https://github.com/loonghao/auroraview/commit/0e0f9b0296e82db87c73199e25f7ede4f944f618))
* update test to expect Python 3.11 as default version ([2d83a79](https://github.com/loonghao/auroraview/commit/2d83a79244e980c826d65be212e5730c901f93ea))
* use PyOxidizerBuilderConfig instead of PyOxidizerConfig in tests ([5be9148](https://github.com/loonghao/auroraview/commit/5be914843e72895aead2c20fe80b88fc024d3346))


### Documentation

* add pack example with custom icon and console hiding features ([7081466](https://github.com/loonghao/auroraview/commit/7081466a4e1d7fed57a69ac434e7bebded65557e))
* migrate to VitePress documentation site and add pack examples ([ed75901](https://github.com/loonghao/auroraview/commit/ed75901b5c3dc5bf87286604442aa3e5100367c7))

## [0.3.20](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.19...auroraview-v0.3.20) (2025-12-21)


### Features

* **aurora-protect:** add hybrid encryption for Python bytecode protection ([f8f5701](https://github.com/loonghao/auroraview/commit/f8f57012b5b1d966f46c4599ce3bafb39d1d2f7f))


### Bug Fixes

* use std::slice::from_ref instead of clone for slice ([5e08053](https://github.com/loonghao/auroraview/commit/5e0805342957ad6c2441e5ebafb5cda06ee0cd07))

## [0.3.19](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.18...auroraview-v0.3.19) (2025-12-18)


### Bug Fixes

* **ci:** resolve artifact name conflicts between workflows ([fcf7f96](https://github.com/loonghao/auroraview/commit/fcf7f969786c234958eb497599d664598941c1e9))

## [0.3.18](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.17...auroraview-v0.3.18) (2025-12-18)


### Bug Fixes

* auto-merge _core extension when bundling auroraview source ([090f18c](https://github.com/loonghao/auroraview/commit/090f18cefa997715cffbeb704986dd3d1d00ece0))
* update SDK assets artifact name to use pr- prefix ([40d565b](https://github.com/loonghao/auroraview/commit/40d565bac81d00eb097aeb3aea19cf91aa9c49a9))

## [0.3.17](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.16...auroraview-v0.3.17) (2025-12-18)


### Bug Fixes

* **ci:** resolve artifact name conflicts in release workflow ([5ed09f9](https://github.com/loonghao/auroraview/commit/5ed09f92112752f7b86c357aad4cecd93f0425e0))

## [0.3.16](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.15...auroraview-v0.3.16) (2025-12-17)


### Bug Fixes

* **ci:** rename sdk-assets artifact in build-gallery.yml to avoid conflict ([507320d](https://github.com/loonghao/auroraview/commit/507320d6172c14eb6a66a6037dc6a014d8578b53))

## [0.3.15](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.14...auroraview-v0.3.15) (2025-12-17)


### Bug Fixes

* **ci:** fix SDK and Gallery build issues in release workflow ([1b95e28](https://github.com/loonghao/auroraview/commit/1b95e28302e2e0cca1c0dad7a8e5e753f7ee60ad))

## [0.3.14](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.13...auroraview-v0.3.14) (2025-12-17)


### Features

* add ipckit LocalSocket IPC support for high-performance subprocess communication ([7681610](https://github.com/loonghao/auroraview/commit/7681610bc90386f27e15f249e1cac63fab2cb8ea))
* **ipc:** add IpcChannel Python client and comprehensive E2E tests ([7189ce9](https://github.com/loonghao/auroraview/commit/7189ce9cfdd9af96328f358c8e288d56b0d63663))


### Bug Fixes

* **ci:** add npm rebuild rollup to fix native module issue in CI ([9fa7462](https://github.com/loonghao/auroraview/commit/9fa746240fd9e43e31514c219abddba525cf2a2d))
* **ci:** build SDK before Gallery to resolve @auroraview/sdk/react import ([f99b10e](https://github.com/loonghao/auroraview/commit/f99b10e7fea32de7c15f301b480f3673b995489f))
* **ci:** improve sdk-ci concurrency to prevent hanging jobs ([b639d9f](https://github.com/loonghao/auroraview/commit/b639d9fd92d8f083e3281959c627d2977d82de65))
* **ci:** use clean npm install to fix rollup native module issue ([734ecb1](https://github.com/loonghao/auroraview/commit/734ecb1d1c9034c34e0e94de985fb2a8a6361ac7))
* **ci:** use shell: bash for rm -rf on Windows runners ([144486a](https://github.com/loonghao/auroraview/commit/144486a6b058067fb74ceecd2476a6cffb3375ff))
* **ci:** use unique concurrency group for sdk-ci to avoid deadlock ([6b0026b](https://github.com/loonghao/auroraview/commit/6b0026b76e87237c80a3ea90add2657c3685ea5e))
* **gallery:** add ApiResult types and fix vite react resolution ([c739c13](https://github.com/loonghao/auroraview/commit/c739c132b11ade7bed6153194d3dc1f9f7d51e42))
* **packed:** register API methods dynamically from Python handlers ([90e3410](https://github.com/loonghao/auroraview/commit/90e34106778231fce6ceea1b6a004914f3e52495))
* **plugins:** clear AURORAVIEW_PACKED for spawned processes ([497faf5](https://github.com/loonghao/auroraview/commit/497faf549c0b33f8463061d848d5dabddd32a0bb))
* remove unused imports in test_headless_webview.py ([a15b48e](https://github.com/loonghao/auroraview/commit/a15b48e47986e90e5c215d916354ad35eb2b00b2))
* resolve unused imports and mut warnings for cross-platform build ([a39640d](https://github.com/loonghao/auroraview/commit/a39640d7a8e824a60447e64e337636aa5796583e))


### Code Refactoring

* **cli:** split packed.rs into modular structure ([95e48d4](https://github.com/loonghao/auroraview/commit/95e48d49b3bcf0ac298343b0ef3d8208a8d13dcc))
* **pack:** remove redundant api_methods static configuration ([b921222](https://github.com/loonghao/auroraview/commit/b9212224fdc680436bdc1ccf59726299756d36b5))

## [0.3.13](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.12...auroraview-v0.3.13) (2025-12-14)


### Features

* enhance gallery E2E screenshots with multi-page capture ([6cad8a9](https://github.com/loonghao/auroraview/commit/6cad8a91dd736fff14a1c5de2153ee06423c6d60))
* **packed:** show loading screen while waiting for Python backend ([b3efaec](https://github.com/loonghao/auroraview/commit/b3efaec017614b5ab6cc18ff2ba11db39cd4cb59))
* **testing:** add Edge WebDriver support for E2E testing ([f14907b](https://github.com/loonghao/auroraview/commit/f14907b81f36bc83be8142d95184e1fe09c78439))


### Bug Fixes

* **ci:** add npm retry and improve gallery artifact handling ([5624d22](https://github.com/loonghao/auroraview/commit/5624d221f6f78aa03fe05f4e0f1573e5a2d8708e))
* **ci:** exclude auroraview-cli from rust coverage tests ([6474e8e](https://github.com/loonghao/auroraview/commit/6474e8e4856a064e1541dc9d7710871360c504d3))
* **ci:** use separate cache keys for sccache vs non-sccache builds ([d3ce23c](https://github.com/loonghao/auroraview/commit/d3ce23c5e8ef870196915be1c9afdd9469142f16))
* **cli:** add timeout to command execution in info command ([02e719f](https://github.com/loonghao/auroraview/commit/02e719f7489941dd2a3bf5966da12e124d47e9af))
* clippy field_reassign_with_default warning and enhance pre-commit ([6d52f4f](https://github.com/loonghao/auroraview/commit/6d52f4f1a673ecdedc7d4da943d544c096f016bb))
* **cli:** use Stdio::null() in info command to prevent hanging ([7651e65](https://github.com/loonghao/auroraview/commit/7651e65a4ef4d15c9aa2977320bad83a4879c956))
* remove unused imports in test_headless_webview.py ([59ca770](https://github.com/loonghao/auroraview/commit/59ca770adcf4bb7e0ec5be0227c7d516a8ec335f))
* **test:** ignore IPC integration tests in CI coverage ([af090a1](https://github.com/loonghao/auroraview/commit/af090a18f6e7f1225b870ac68462b0a7f2602b77))
* **test:** skip ready signal in test_processes_valid_request ([d362824](https://github.com/loonghao/auroraview/commit/d362824e767246de4a86ecc140ccca96057be600))
* **test:** use python3 on Linux for IPC integration tests ([949f9ce](https://github.com/loonghao/auroraview/commit/949f9cee123283a3b609fd910a1742e93189acf1))


### Code Refactoring

* reorganize tests into crate-specific directories and add visibility modifiers ([f1137a9](https://github.com/loonghao/auroraview/commit/f1137a9e820e2da52e9fbb78bbb0bc2355e93fa4))

## [0.3.12](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.11...auroraview-v0.3.12) (2025-12-14)


### Features

* **pack:** add automatic Python dependency collection ([6430170](https://github.com/loonghao/auroraview/commit/64301703ce1c8624483e09bcae7520a115846611))
* **pack:** add hooks.collect support for bundling examples ([4e4a893](https://github.com/loonghao/auroraview/commit/4e4a893f046047bf9cb5bed05a6b43781d098937))
* **pack:** add standalone Python runtime bundling strategy ([906aec4](https://github.com/loonghao/auroraview/commit/906aec4389aae4fb047376b92254b6f87675139d))
* **pack:** add standalone Python runtime bundling strategy ([6c914ef](https://github.com/loonghao/auroraview/commit/6c914ef88511d9bafb640a091d83f37d48dd75ad))


### Bug Fixes

* **ci:** update gallery pack workflow for direct executable output ([9c1a27c](https://github.com/loonghao/auroraview/commit/9c1a27c0fd733535af1ace50f4609a096deada08))


### Performance Improvements

* **pack:** streaming decompression and WebView2 warmup ([f47b132](https://github.com/loonghao/auroraview/commit/f47b1322c3b902a1c9f19178bebf95958a8487cf))

## [0.3.11](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.10...auroraview-v0.3.11) (2025-12-13)


### Features

* add Gallery app with plugin system and API unification ([51307db](https://github.com/loonghao/auroraview/commit/51307dbab10a93adcffdfc6ffbea6814a913c939))


### Bug Fixes

* add cfg guards for Windows-only code paths ([458a89f](https://github.com/loonghao/auroraview/commit/458a89f3c42e936e454caf30162a36b57d20468d))
* add libxdo-dev dependency for Linux builds and fix dead_code warning ([8e3620f](https://github.com/loonghao/auroraview/commit/8e3620fcf471e19be19ae464d6af2e8a2b213bf8))
* update wry WebViewBuilder API from with_web_context to new_with_web_context ([4d30b05](https://github.com/loonghao/auroraview/commit/4d30b0530235c25f16d5cddec87d0bec02532524))


### Documentation

* add new features documentation (Gallery, System Tray, Floating Panels, Plugin System) ([87a9d2b](https://github.com/loonghao/auroraview/commit/87a9d2babad62252bbcff7cb54c37cd6d2981236))

## [0.3.10](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.9...auroraview-v0.3.10) (2025-12-11)


### Features

* add native file drop events and shell plugin enhancements ([6729a56](https://github.com/loonghao/auroraview/commit/6729a565cc0ffa0fe593b3a6708f1be42aab4c21))


### Bug Fixes

* add cfg(windows) for platform-specific imports ([93d13d4](https://github.com/loonghao/auroraview/commit/93d13d4e8f16e1174023fd69c5ce0893505faf07))
* correct dev_tools default test assertion ([800b363](https://github.com/loonghao/auroraview/commit/800b363f43a387392d2ffed6e5a61a093a55c7e2))
* init_com_sta available on all platforms ([fbdfe56](https://github.com/loonghao/auroraview/commit/fbdfe562b6de5f871a82b02a0895c42823278363))
* resolve fmt issues and add tests for builder module ([c31b417](https://github.com/loonghao/auroraview/commit/c31b417637b49c998381c87472d6a1d46949c236))


### Code Refactoring

* extract more shared WebView builder logic to auroraview-core ([e782c86](https://github.com/loonghao/auroraview/commit/e782c865f33c03aa4cb6d76c8dc1adea873ac34a))
* extract shared WebView builder logic to auroraview-core ([19a02dd](https://github.com/loonghao/auroraview/commit/19a02dd551b25dd157eda4011ae218a7e424e6cc))
* rename standalone to desktop with backward compatibility ([c43b6bb](https://github.com/loonghao/auroraview/commit/c43b6bb3611b89e3867e9349dd5b24c7eacd462a))

## [0.3.9](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.8...auroraview-v0.3.9) (2025-12-11)


### Bug Fixes

* **ci:** use correct tag format auroraview-v* for release-please ([678f0fa](https://github.com/loonghao/auroraview/commit/678f0fa128be931e4e6f4c3fa2f2f34c6752d552))


### Documentation

* add Python 3.7 Windows CLI workaround for uv/uvx ([ce92fd0](https://github.com/loonghao/auroraview/commit/ce92fd00d8726c7fa8f039b872d6dc7ba99ea993))

## [0.3.8](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.7...auroraview-v0.3.8) (2025-12-11)


### Features

* implement desktop events with plugin system integration ([f60d2c7](https://github.com/loonghao/auroraview/commit/f60d2c7c4f663ff96ba560c3ec147c333b212178))
* implement IPC emit and async callback mechanisms ([8ff92ce](https://github.com/loonghao/auroraview/commit/8ff92ce6d021200fec8c3f051a1ee7214e3bde98))


### Bug Fixes

* emit returns False when no handlers registered ([d93921d](https://github.com/loonghao/auroraview/commit/d93921dbe2ded419202bb47663e57a1769c14b35))
* emit() returns False when no handlers registered ([bfe6cc5](https://github.com/loonghao/auroraview/commit/bfe6cc5f0b1512fb2aec567bb2f3748844da4b93))
* improve timer test stability on macOS CI ([8ebb6d9](https://github.com/loonghao/auroraview/commit/8ebb6d933f24c338d6cca840a19407c81a1d0d81))
* resolve get_hwnd returning None and add URL auto-normalization ([8a82b8e](https://github.com/loonghao/auroraview/commit/8a82b8e5fef53f267131c39b37968569fe0464a0))
* use native load_url for splash screen navigation ([d13fda0](https://github.com/loonghao/auroraview/commit/d13fda0cc7e10dd2ca7f13e7d33e18ee97393202))

## [0.3.7](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.6...auroraview-v0.3.7) (2025-12-10)


### Features

* enhance test coverage and IPC benchmarks ([8a994d1](https://github.com/loonghao/auroraview/commit/8a994d1dbc04afb7e5f6497990f47dd766be8ecd))


### Bug Fixes

* remove useless format! macro in benchmark ([4f6f558](https://github.com/loonghao/auroraview/commit/4f6f5583d18bd6638819464f7b3352a25da6c325))

## [0.3.6](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.5...auroraview-v0.3.6) (2025-12-10)


### Bug Fixes

* add UTF-8 encoding declarations for Python 3.7 compatibility ([b24beb1](https://github.com/loonghao/auroraview/commit/b24beb14569ab64afa438bec4a54fe81f15364ca))

## [0.3.5](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.4...auroraview-v0.3.5) (2025-12-10)


### Bug Fixes

* add python-bindings feature to all maturin-args in CI workflows ([d79d8b8](https://github.com/loonghao/auroraview/commit/d79d8b806f7c364199bc7c417ba0f7cc51302b33))

## [0.3.4](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.3...auroraview-v0.3.4) (2025-12-10)


### Bug Fixes

* **ci:** align artifact names between build-wheels and release workflows ([dd6fd61](https://github.com/loonghao/auroraview/commit/dd6fd611977c9b2535c50f0860ac43c9495c3d8d))
* **ci:** use PySide6&gt;=6.8 for Python 3.13+ compatibility ([2aa8281](https://github.com/loonghao/auroraview/commit/2aa8281e5ca1a888b960dc7cfe773e62a8850434))


### Code Refactoring

* **ci:** unify PR and release build flows using build-wheel action ([2b0bc97](https://github.com/loonghao/auroraview/commit/2b0bc977a80f1c817bbf9cb0ec033d483d23386b))


### Documentation

* update Python version range to include 3.13 ([f5e2f63](https://github.com/loonghao/auroraview/commit/f5e2f63cf9188382e54adbbebbcab2833a35ca40))

## [0.3.3](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.2...auroraview-v0.3.3) (2025-12-09)


### Bug Fixes

* **ci:** add Python 3.13 support and fix Windows/macOS abi3 wheel builds ([0517854](https://github.com/loonghao/auroraview/commit/05178547ec5880a606686aa3db489470febc9e15))

## [0.3.2](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.1...auroraview-v0.3.2) (2025-12-09)


### Bug Fixes

* **ci:** correct PyPI artifact filtering to preserve sdist ([9ca85f1](https://github.com/loonghao/auroraview/commit/9ca85f18239f3179448c2445924af341a804c3d1))
* rustdoc bare URLs and timer test flakiness on macOS CI ([56cc05b](https://github.com/loonghao/auroraview/commit/56cc05be4237dfc0ba5a919d6aa0200a39b1a53f))

## [0.3.1](https://github.com/loonghao/auroraview/compare/auroraview-v0.3.0...auroraview-v0.3.1) (2025-12-09)


### Features

* add Python 3.7 support with separate non-abi3 builds ([bfcc0c8](https://github.com/loonghao/auroraview/commit/bfcc0c8c373d41a4587ee6f38a2bfb4914e4ac35))


### Bug Fixes

* add missing serde_json::Value import in tests ([6877c45](https://github.com/loonghao/auroraview/commit/6877c455f259e459599b5b0fbec428f4ff16a7b9))
* add Qt system dependencies for Linux CI ([c521dd0](https://github.com/loonghao/auroraview/commit/c521dd04d3aabf1b735ce6f55162abff9d7ed658))
* always show window when show() is called explicitly ([f5d07a0](https://github.com/loonghao/auroraview/commit/f5d07a04c71420ea89ec0a7f9e067bc8cdef9f1e))
* **ci:** add python-bindings feature for Qt tests build ([24080f7](https://github.com/loonghao/auroraview/commit/24080f7dcd26e4792b895e3b7e253a7138066a86))
* disable sccache for Python 3.7 builds to avoid GLIBC incompatibility ([ae895f7](https://github.com/loonghao/auroraview/commit/ae895f789825e6608c18eacd173cfd711c93e9fc))
* downgrade image to 0.24 and add Qt test dependencies ([b0e21dd](https://github.com/loonghao/auroraview/commit/b0e21dd68a8b7068057f42ff988248ca9887fab3))
* downgrade simd-json to 0.13 for Rust 1.80 compatibility ([3be5429](https://github.com/loonghao/auroraview/commit/3be542950a4feb1a1887b6d72185e9ce6cd99306))
* downgrade tao to 0.33 to avoid dlopen2 edition2024 requirement ([d8dfa15](https://github.com/loonghao/auroraview/commit/d8dfa158c0b5da693d345c0aec9f4d11be6f141e))
* ensure all type annotations are Python 3.7+ compatible ([5dc07e1](https://github.com/loonghao/auroraview/commit/5dc07e1ff0f18b5b7f055625530d643ccb607c59))
* improve test compatibility for cross-platform and CI environments ([08c37a7](https://github.com/loonghao/auroraview/commit/08c37a79c810653ce7ba544cb376791c3ea0e23e))
* only download wheel artifacts for PyPI publish, exclude CLI binaries ([bf0c0fd](https://github.com/loonghao/auroraview/commit/bf0c0fd46b71c4ce1a2ca47e855eabae30542ba3))
* pin dlopen2 to 0.8.1 to avoid edition2024 requirement ([9454d5b](https://github.com/loonghao/auroraview/commit/9454d5b7659fdb51c8bbd781a4dcf6404d6a73d3))
* Python 3.7/3.8 type annotation compatibility and timer test stability ([386367c](https://github.com/loonghao/auroraview/commit/386367c233bbf07dae51de9204c10dd7baa9e438))
* Qt placeholder tests to work in CI environments ([039cffe](https://github.com/loonghao/auroraview/commit/039cffe14d7d97e7b9200a870409c66a16a91fac))
* remove unused import and add ruff select options to pre-commit ([e0d29af](https://github.com/loonghao/auroraview/commit/e0d29af46fc48a53f9b9be73fd1b3278dcdc4759))
* remove unused sys import and add auto_show unit tests ([de413b4](https://github.com/loonghao/auroraview/commit/de413b45f10e1a58121c5fe88b4ddcf7c0269b56))
* resolve abi3-py38 conflict with Python 3.7 and CI test issues ([558df0f](https://github.com/loonghao/auroraview/commit/558df0f1e3bb318a277aaebdad7b2cc82f5f1340))
* skip WebView browser tests in CI on all platforms ([200d76c](https://github.com/loonghao/auroraview/commit/200d76c11e93f606b9206e7a1f8b7dfe44958186))
* use typing_extensions.Literal for Python 3.7 compatibility ([00519d1](https://github.com/loonghao/auroraview/commit/00519d18d7e633970ae7fb91ce8578d34341f50c))

## [0.3.0](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.22...auroraview-v0.3.0) (2025-12-08)


### ⚠ BREAKING CHANGES

* Major architecture refactoring

### Features

* add apply_qt6_dialog_optimizations function ([434236d](https://github.com/loonghao/auroraview/commit/434236d23679307d419d61a138fc849fafb6260a))
* add cross-platform PlaywrightBrowser tests with CI browser installation ([d1dbc5b](https://github.com/loonghao/auroraview/commit/d1dbc5b6eb225dffe591dce40ccaa04e102267ee))
* add cross-platform Python tests (Linux, Windows, macOS) ([016ae05](https://github.com/loonghao/auroraview/commit/016ae05174adaf4b3e60cf53aa9a8960ae7d5de0))
* add Qt5/Qt6 compatibility layer and diagnostics ([acf9fe8](https://github.com/loonghao/auroraview/commit/acf9fe846ae044fe8d332322b511eb4179faa9e6))
* add xvfb support for headless UI tests in CI ([5eaf136](https://github.com/loonghao/auroraview/commit/5eaf136100f0d929ba630a41664951095c9629b7))
* **pack:** complete MVP for auroraview-pack and auroraview-cli crates ([72811de](https://github.com/loonghao/auroraview/commit/72811de66c277e69fe0ddad92ad6b5b721d2f9e3))
* refactor architecture - migrate core modules to auroraview-core crate ([2085d94](https://github.com/loonghao/auroraview/commit/2085d94fe9a26cc25909f105d890dd360c949b7e))
* **signals:** add Qt-inspired signal-slot event system ([373b93d](https://github.com/loonghao/auroraview/commit/373b93dbf6feaaf22d5896294c3b34e72ff8e3af))
* **testing:** add PlaywrightBrowser for Playwright-based UI testing ([3988d1a](https://github.com/loonghao/auroraview/commit/3988d1aafc977f426e5f222216c9e97aef8c61c7))


### Bug Fixes

* add python-bindings feature to Linux build in CI ([8fabe2c](https://github.com/loonghao/auroraview/commit/8fabe2c25fde84191c06ebe4b0ac51a3c7e19c81))
* add url-utils to python-bindings feature and export png_bytes_to_ico ([156a4d3](https://github.com/loonghao/auroraview/commit/156a4d35f3d5851f7d0b191b4e3ec67513e54091))
* add x-release-please-version tag to version fields ([f1d4ec0](https://github.com/loonghao/auroraview/commit/f1d4ec0ff09a4941bfeae4a0d6afa76f0062ad7d))
* **ci:** correct Rust integration test names in CI configuration ([1efed3a](https://github.com/loonghao/auroraview/commit/1efed3a6edabc3091bd3e5e163222aabe4993250))
* **ci:** correct rust-toolchain action name ([d688621](https://github.com/loonghao/auroraview/commit/d6886217307bd9f7923d362a8078a545de95064e))
* correct function name in cli_utils test ([402c629](https://github.com/loonghao/auroraview/commit/402c629e366ed72b9c50d30607aadf0f59bd0f45))
* correct Qt test paths in pr-checks.yml ([4b562a6](https://github.com/loonghao/auroraview/commit/4b562a619d1da0ffffaefe658c10446e803dd30d))
* correct test file paths in noxfile.py and README ([404b17a](https://github.com/loonghao/auroraview/commit/404b17ada4cbe5d14a9813fb479086ddf69de869))
* correct wry API and image crate import in CLI ([75c00ef](https://github.com/loonghao/auroraview/commit/75c00efd6acdafd651697ba5b51e3086df01a50a))
* handle poisoned mutex gracefully to prevent panic on close ([a5a6cd3](https://github.com/loonghao/auroraview/commit/a5a6cd316566dad1b28ad9c7f8b1518e6895d8b3))
* import testing fixtures in conftest and skip UI tests in CI ([635368b](https://github.com/loonghao/auroraview/commit/635368b9b74318c6d086f23500acc87bd954613b))
* replace deprecated macos-13 runner with macos-latest cross-compile ([ebc0842](https://github.com/loonghao/auroraview/commit/ebc0842c4bc48730d72c86a56aa7865c3db0c216))
* resolve clippy warnings and CI ruff installation ([68c3e18](https://github.com/loonghao/auroraview/commit/68c3e185d69fa256ae3c8acf43c6506c82a00de5))
* resolve cross-platform compilation errors for Linux CI ([652b4fa](https://github.com/loonghao/auroraview/commit/652b4fa710d2137f3af2f154d6e20753b86bcf9e))
* resolve lint and clippy warnings ([c15ad33](https://github.com/loonghao/auroraview/commit/c15ad33230e6455a3cff37e3a16ce4db8ce72230))
* resolve unit test collection errors on Linux CI ([3fe9007](https://github.com/loonghao/auroraview/commit/3fe9007771d91fd72c390c7ca5102fa8817322b5))
* skip Browser tests on Linux CI and fix localStorage test ([df162ed](https://github.com/loonghao/auroraview/commit/df162eda8960c9b504d3be72df50430be25bf9df))
* skip Browser tests on macOS CI and fix actions/checkout version ([57fcd73](https://github.com/loonghao/auroraview/commit/57fcd732e266e69990332be33eff781a0c4903f9))
* skip PlaywrightBrowser native mode tests in CI ([cbd6e88](https://github.com/loonghao/auroraview/commit/cbd6e8811a1cfb5dc1af9c7a1fcec739b99f9304))
* unused variable in shell plugin test ([a5964ba](https://github.com/loonghao/auroraview/commit/a5964ba8d74d5b5e5461a308c379ef70dbfee27a))
* unused variable in shell plugin test ([eddde5a](https://github.com/loonghao/auroraview/commit/eddde5aa37390d7fb21749f9d3e3d76e2f29e18b))
* update bom test to match fallback pattern in JS templates ([afc10ed](https://github.com/loonghao/auroraview/commit/afc10ed605de2004ce1e44e579203ba6257f6ba7))
* update integration tests for CI compatibility ([d2ababf](https://github.com/loonghao/auroraview/commit/d2ababf242be5c45cd08ff490b448f0b08f36b84))
* use find_spec instead of import for playwright check ([5dfc9e0](https://github.com/loonghao/auroraview/commit/5dfc9e032008bcacaf75ad9e5c38fab304d709a1))
* use force=True in Locator tests to skip actionability checks ([c0dcd76](https://github.com/loonghao/auroraview/commit/c0dcd7638116dd7a9bc49d412a6e2d06613cd4b6))


### Performance Improvements

* **logging:** add conditional verbose logging for DCC environments ([004ffe1](https://github.com/loonghao/auroraview/commit/004ffe1f1b27e1854bb50c5d60bba3efea8118d6))
* **qt:** optimize window style operations and fix initialization timing ([3fe3025](https://github.com/loonghao/auroraview/commit/3fe3025caf68d4a5928529b3abb670bf65067fe3))
* **warmup:** auto-start WebView2 warmup on module import ([4f04815](https://github.com/loonghao/auroraview/commit/4f04815d06bbf00962e5bdc6ee4aac68c19f74e8))


### Code Refactoring

* clean up dead code and fix integration test imports ([39b116c](https://github.com/loonghao/auroraview/commit/39b116cbe68cf390e1530686816012506e37d997))
* replace Playwright native tests with WebView2 Browser tests ([a658808](https://github.com/loonghao/auroraview/commit/a65880878ccee04f1fff446ce12c0ccdaa94848c))
* **testing:** replace legacy testing modules with HeadlessWebView framework ([5e67fc7](https://github.com/loonghao/auroraview/commit/5e67fc7d7979263128102d8d292567a8ad425d07))
* update test files for cross-platform WebView testing ([8a393df](https://github.com/loonghao/auroraview/commit/8a393dfdfba4987c32e695828d6ce0d74d70bae1))
* update test_auroratest_browser.py for cross-platform WebView testing ([c2cfa72](https://github.com/loonghao/auroraview/commit/c2cfa726e94f40ee709e574e7f98829954dead3c))


### Documentation

* add JS-Python communication guide and improve coverage config ([89c350d](https://github.com/loonghao/auroraview/commit/89c350dd5eb268864db9c20e4032c07a6c70ca0e))
* update API examples and add llms.txt index file ([d441e69](https://github.com/loonghao/auroraview/commit/d441e696a0a552595e9254ee8356d252109d5528))

## [0.2.22](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.21...auroraview-v0.2.22) (2025-11-30)


### Features

* **dom:** add comprehensive DOM manipulation module ([20cb0fb](https://github.com/loonghao/auroraview/commit/20cb0fb2f89467e8d98cb87cb9fed750b4caead5))
* **dom:** add Rust-native DOM batch operations for high performance ([64ccb50](https://github.com/loonghao/auroraview/commit/64ccb5036bfa76581e88d0af0c5a3138d01a9df2))
* **testing:** add DOM-based testing framework ([d7e8227](https://github.com/loonghao/auroraview/commit/d7e8227a1af601d2e0a6e7b173fe6b37757cf28f))


### Bug Fixes

* improve CI test stability ([b9f7ca3](https://github.com/loonghao/auroraview/commit/b9f7ca3300d14bee9d8a0035687e132b9143a54d))
* Python 3.7 compatibility and format test file ([9295609](https://github.com/loonghao/auroraview/commit/92956097dde2d5b8499edb431fc67d6dca419fa3))
* **tests:** update tests for DOM API migration ([d55968e](https://github.com/loonghao/auroraview/commit/d55968e5c02aa82d2f9ef6270e05e7beae56ed11))


### Documentation

* deep comparison between AuroraView and PyWebView ([a958523](https://github.com/loonghao/auroraview/commit/a958523105fa16a98c0c7a597a04340a87164315))
* update comparison with comprehensive DOM API section ([ce5c878](https://github.com/loonghao/auroraview/commit/ce5c878a275bf8eceaa3a3b1c34847f7cf35e86c))

## [0.2.21](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.20...auroraview-v0.2.21) (2025-11-28)


### Features

* auto-convert relative paths to auroraview:// protocol and add always_on_top ([66fc2a1](https://github.com/loonghao/auroraview/commit/66fc2a1a4a20c50cea53168a1c1e68f639e0eeaf))

## [0.2.20](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.19...auroraview-v0.2.20) (2025-11-27)


### Features

* add window maximization when width/height is 0 ([930da84](https://github.com/loonghao/auroraview/commit/930da8408ba7b5829d9afa339b293a769c23707c))


### Documentation

* add run_standalone examples for local resource loading ([2d8f254](https://github.com/loonghao/auroraview/commit/2d8f254fcceab156a18d91ef9e61204e03715ae5))

## [0.2.19](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.18...auroraview-v0.2.19) (2025-11-27)


### Bug Fixes

* use Optional[] instead of | union syntax for Python 3.7 compatibility ([330759e](https://github.com/loonghao/auroraview/commit/330759e8c8955cb385802ace2d81f0fc07cd606e))

## [0.2.18](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.17...auroraview-v0.2.18) (2025-11-27)


### Features

* add allow_file_protocol parameter for local resource loading ([37f2bea](https://github.com/loonghao/auroraview/commit/37f2bea513e6442a91629768f2c548a77836ebf6))


### Code Refactoring

* remove debug file logging, use tracing instead ([497b6c4](https://github.com/loonghao/auroraview/commit/497b6c48394f695b2471e40290f745413b5fee1a))


### Documentation

* add custom protocol best practices and security documentation ([e520924](https://github.com/loonghao/auroraview/commit/e5209246cb57c6806248eb7f1acc776b04e85ccc))

## [0.2.17](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.16...auroraview-v0.2.17) (2025-11-26)


### Bug Fixes

* make CI tests more robust for Windows and macOS ([0f303bf](https://github.com/loonghao/auroraview/commit/0f303bf8415857dbbf3f2fb7f0dbf2ff86007555))

## [0.2.16](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.15...auroraview-v0.2.16) (2025-11-26)


### Features

* support Windows absolute paths in auroraview:// protocol ([1fd4431](https://github.com/loonghao/auroraview/commit/1fd4431776f5c0a487474130cdfa96365abe22a4))

## [0.2.15](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.14...auroraview-v0.2.15) (2025-11-25)


### Features

* add _post_eval_js_hook support for Qt integration and testing ([233332f](https://github.com/loonghao/auroraview/commit/233332f29922584eb7540b2ce04b326a8b4e800e))
* add file:// protocol support and reorganize test files ([226ce71](https://github.com/loonghao/auroraview/commit/226ce714490a8cdf28a8c02b50d4a954a384d1d2))
* add prepare_html_with_local_assets utility function ([5952ca3](https://github.com/loonghao/auroraview/commit/5952ca3a2195b735b49eb435bb6396c0f4d2eaa0))
* improve DCC mode HWND handling and reduce log noise ([ef43cfd](https://github.com/loonghao/auroraview/commit/ef43cfd49674dec0d9e4591152de7b6231741cce))
* **qt:** improve embedded WebView geometry sync and window styling ([ae091e9](https://github.com/loonghao/auroraview/commit/ae091e9dc6a01f7c6e989e8fcb83c8dcd6a004d0))


### Bug Fixes

* add __future__ annotations for Python 3.9 compatibility ([cb04732](https://github.com/loonghao/auroraview/commit/cb04732181ff902d2af927b0bdf237af189f35aa))
* add skipif decorator to test_api_injection_timing for Qt dependency ([e0c4181](https://github.com/loonghao/auroraview/commit/e0c4181c28df15c58398ad0da6e234a2822ae965))
* make ctypes and wintypes imports platform-specific ([d76f452](https://github.com/loonghao/auroraview/commit/d76f4523994fad40a19be2d641d1436bd9704392))
* use Union syntax for Python 3.7-3.9 compatibility ([4d46cb2](https://github.com/loonghao/auroraview/commit/4d46cb2e78231f025ea5e6338430cc8043b0e484))


### Performance Improvements

* add resize event throttling to maintain 60 FPS ([0b1f12d](https://github.com/loonghao/auroraview/commit/0b1f12d1a24cd9bbc382d3cc1f76c448dae0c4b1))


### Code Refactoring

* move in-block imports to module top level ([cb6cc3b](https://github.com/loonghao/auroraview/commit/cb6cc3b12fc82ebcbc5a7bea810bafd44bac27cc))
* use qtpy for QTimer import instead of direct Qt binding imports ([b2651f7](https://github.com/loonghao/auroraview/commit/b2651f7f621d18d2b7349d8a1b50f07d1944c477))

## [0.2.14](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.13...auroraview-v0.2.14) (2025-11-24)


### Features

* add always-on-top window option ([0e7de4c](https://github.com/loonghao/auroraview/commit/0e7de4cbece4cec5043eb0f69fa53dd0e7ba8069))
* add window maximization and file protocol support ([9c09855](https://github.com/loonghao/auroraview/commit/9c0985597fad4cd537c6cb6cad363c9a42a8dd74))


### Bug Fixes

* update file protocol tests to use valid HTTP URIs ([12ba42c](https://github.com/loonghao/auroraview/commit/12ba42ce80f30b8342036b67a00cf3b35f63426f))

## [0.2.13](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.12...auroraview-v0.2.13) (2025-11-24)


### Bug Fixes

* resolve macOS abi3 wheel build issues ([3fa8d78](https://github.com/loonghao/auroraview/commit/3fa8d785e14d89cb1a48b861dffa4070f827a964))

## [0.2.12](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.11...auroraview-v0.2.12) (2025-11-23)


### Bug Fixes

* resolve macOS CI cache setup hashFiles errors ([5fc5968](https://github.com/loonghao/auroraview/commit/5fc59686275a6595a946342e784e4c7b5ee7c329))


### Code Refactoring

* implement dependency injection for EventTimer backends ([9b942a3](https://github.com/loonghao/auroraview/commit/9b942a367d58f2c712787bce96b9e1485a883de8))
* simplify EventTimer by removing DCC-specific implementations ([32fa559](https://github.com/loonghao/auroraview/commit/32fa559be544fbd771d3bac99c2f89346cad5cb5))

## [0.2.11](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.10...auroraview-v0.2.11) (2025-11-22)


### Features

* optimize standalone mode with loading screen and unified event loop ([5975b79](https://github.com/loonghao/auroraview/commit/5975b790a0eb2bfc4e88dca5dc6ebedec08845c0))


### Bug Fixes

* add Cargo.lock to ensure reproducible builds ([63b2420](https://github.com/loonghao/auroraview/commit/63b2420256eb9b39b90154831f1c1ad37b479e5e))
* mock run_standalone instead of WebView in CLI tests ([584ec21](https://github.com/loonghao/auroraview/commit/584ec2196292b5e184de07a08178bbfcfdcd6343))
* update documentation examples to use ignore instead of no_run ([c3842ea](https://github.com/loonghao/auroraview/commit/c3842ea76b13e71e7b2fb8a70561fc72db0a70ce))

## [0.2.10](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.9...auroraview-v0.2.10) (2025-11-21)


### Features

* expose Rust CLI utilities to Python for enhanced functionality ([bc96ed5](https://github.com/loonghao/auroraview/commit/bc96ed55cb5d1b13b0f7c6e223179f2e025be2ea))


### Bug Fixes

* implement pure Python CLI for uvx compatibility ([96f7c94](https://github.com/loonghao/auroraview/commit/96f7c9434ae51f52bc6cc50edccc4fa00727a450))

## [0.2.9](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.8...auroraview-v0.2.9) (2025-11-21)


### Features

* migrate all Rust tests to rstest integration tests ([085e524](https://github.com/loonghao/auroraview/commit/085e52480132f773c3ebdb1e142eb3de4b397c7e))
* migrate all unit tests to rstest framework ([5d0ec35](https://github.com/loonghao/auroraview/commit/5d0ec35a8985d0d872ab5235de931ce0b72fd11d))
* migrate IPC and HTTP discovery tests to rstest integration tests ([20a6c61](https://github.com/loonghao/auroraview/commit/20a6c61a69b435b8db922338bb3b148437c4e60a))
* upgrade windows crate to 0.62 ([4667a8f](https://github.com/loonghao/auroraview/commit/4667a8f163e18e0272e0d13fabe254872d401653))


### Bug Fixes

* add conditional compilation for test imports on Windows-only tests ([7f8b6ad](https://github.com/loonghao/auroraview/commit/7f8b6adf3c36391e03518daa878021622b02712d))
* add test-helpers feature to Timer conditional compilation ([2f0d2cc](https://github.com/loonghao/auroraview/commit/2f0d2ccdc9bd7389854fa4804329694374df4861))
* correct PyList creation in batch processing ([38c2304](https://github.com/loonghao/auroraview/commit/38c23046fed50ae5e1daa96782e540081fd72436))
* remove equals sign from mDNS metadata key in test ([4a95aee](https://github.com/loonghao/auroraview/commit/4a95aee53d59617dc117f990f1b5654f9594a6e9))
* remove race condition in port availability test ([ca091f3](https://github.com/loonghao/auroraview/commit/ca091f3c9df7a121404d931c2af21388b1b84edc))
* remove unused Duration import on non-Windows platforms ([541d9b7](https://github.com/loonghao/auroraview/commit/541d9b7ab41f4872bf4be6bbffe7244cc76789f2))
* resolve unused import and add more config tests ([4a25926](https://github.com/loonghao/auroraview/commit/4a2592601c484e4d9495e68f3952e7fb7ae58319))
* update PyList API for PyO3 0.27.1 compatibility ([06afb93](https://github.com/loonghao/auroraview/commit/06afb93c6c36263c269d534bcc909436e81630c5))
* use empty PyList in ipc_batch integration test ([ff9d989](https://github.com/loonghao/auroraview/commit/ff9d989bcf31d478aec5d5abdeb304da6c7dea8d))
* use localhost.local. for mDNS hostname to comply with spec ([def1d93](https://github.com/loonghao/auroraview/commit/def1d93545fe42e01095ceb4e88b2929cd2644e4))

## [0.2.8](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.7...auroraview-v0.2.8) (2025-11-18)


### Features

* improve codecov integration with comprehensive configuration ([d3594e2](https://github.com/loonghao/auroraview/commit/d3594e247eb4e69881d31a23ffa12999641ac658))

## [0.2.7](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.6...auroraview-v0.2.7) (2025-11-17)


### Features

* add configurable context menu support ([e2551ec](https://github.com/loonghao/auroraview/commit/e2551ecf6cf19dcb628c1533ddad91d5a38c7df3))
* add custom protocol handlers with mime_guess integration ([9862870](https://github.com/loonghao/auroraview/commit/986287044948c4ff3b1f8f11ce829026bc4688be))


### Bug Fixes

* add custom protocol support to Python WebView API ([5d3322e](https://github.com/loonghao/auroraview/commit/5d3322e1724cee458d5e41a41d6c154d4f07c301))
* correct MIME types and URI handling in protocol tests ([992ecbe](https://github.com/loonghao/auroraview/commit/992ecbe51f7d614b277654aca707d4de4668dc27))
* correct URI path extraction for custom protocols ([ecaf64b](https://github.com/loonghao/auroraview/commit/ecaf64bcc43d1a96298784ad5b265e56e033b2d3))
* disable context menu using JavaScript event prevention ([4382be7](https://github.com/loonghao/auroraview/commit/4382be7b242496a52a9101af9ba963b4219fd37c))
* remove debug markers and fix failing unit tests ([f06b056](https://github.com/loonghao/auroraview/commit/f06b056be5419b4cd6fd66883515fce42abb5896))
* resolve doctest compilation errors ([efbae30](https://github.com/loonghao/auroraview/commit/efbae30b0bd1eaba7b94df30d6ce13ab561879c2))
* strengthen directory traversal protection with path canonicalization ([e17dc35](https://github.com/loonghao/auroraview/commit/e17dc3507be62535f3ccec146cbc4d6fd136896b))


### Code Refactoring

* apply js_assets to backend/native.rs and standalone.rs ([8dd3cc9](https://github.com/loonghao/auroraview/commit/8dd3cc9bd37ca521c8958a81e68b93348edc1c0d))
* complete code cleanup and add IPC metrics API ([03a7244](https://github.com/loonghao/auroraview/commit/03a7244918ac9cc86e995270e2d1769adb48e92c))
* consolidate bindings and remove legacy embedded.rs ([3875d40](https://github.com/loonghao/auroraview/commit/3875d40cf91dab699c468edf0f6df29e8f58a84f))
* extract JavaScript to separate files and apply to embedded.rs ([ebd069e](https://github.com/loonghao/auroraview/commit/ebd069ee5a9a56c6545fadb0b029a2976e77f06a))

## [0.2.6](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.5...auroraview-v0.2.6) (2025-11-17)


### Features

* add automatic event processing for Qt integration ([ac8a689](https://github.com/loonghao/auroraview/commit/ac8a68969275f6723e3ce3ff3e7b92936b94d593))

## [0.2.5](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.4...auroraview-v0.2.5) (2025-11-16)


### Features

* **timer,docs,webview:** add callback deregistration and type hints; embedded helper\n\n- EventTimer: add off_close() and off_tick() for deregistration\n- EventTimer: introduce TimerType Literal for timer backend types\n- WebView: add run_embedded() convenience helper (auto_show + auto_timer)\n- Docs: update EventTimer guide (qtpy note, semantics), add Python embedded best practices\n- Tests: add unit tests for off_close/off_tick\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([61a7e70](https://github.com/loonghao/auroraview/commit/61a7e70a65772a1d53e8324bd9d1fee1d9fddccc))
* **timer:** use qtpy for Qt QTimer backend to support PySide6/PyQt via unified API\n\n- Replace PySide2 direct import with qtpy.QtCore.QTimer\n- Keeps graceful fallback if qtpy not installed (auroraview[qt] installs it)\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([2f4c4dd](https://github.com/loonghao/auroraview/commit/2f4c4dd913bdd97bf0b269fd02c17637ece44ec2))
* upgrade pyo3 to 0.27.1 and warp to 0.4 ([7737c93](https://github.com/loonghao/auroraview/commit/7737c93b8c9e1d7bce3c2dc807c4b5f99e4502cc))


### Bug Fixes

* add delay to ensure port is set before test assertions ([811bf96](https://github.com/loonghao/auroraview/commit/811bf964826464781e72a729b426c6fe0a6b1d5c))
* resolve HTTP discovery test port binding issues ([46b0857](https://github.com/loonghao/auroraview/commit/46b08576c0e130024b6471aac182d6df9b65aefb))
* **rust,features:** gate PyO3 imports and #[pymodule] behind feature python-bindings so rust-coverage can build with --no-default-features; test gating under cfg(all(test, feature))\nci(qt): install pytest-qt, pin PySide6&lt;6.7 and enable QT_DEBUG_PLUGINS for verbose plugin diagnostics\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([81b233f](https://github.com/loonghao/auroraview/commit/81b233f576a32077898785e1e6e17fd74ab5456d))
* support zero-parameter auroraview.call handlers ([93eb389](https://github.com/loonghao/auroraview/commit/93eb389393c80074a2865d9edb10f99bb60474af))
* update tests for dependency upgrades ([129bf5b](https://github.com/loonghao/auroraview/commit/129bf5b8492c1cf066393ffa10e98ae8675166bd))
* use Arc&lt;Mutex&gt; to properly synchronize port binding ([0144f2d](https://github.com/loonghao/auroraview/commit/0144f2dfa54ee412d7eb9f904c82b5ce72f1dc89))
* use mpsc channel for proper address synchronization ([b680067](https://github.com/loonghao/auroraview/commit/b680067bab4c1b07f7c2f7cc0a3d662f3facd648))


### Code Refactoring

* drop EventBridge compatibility from Qt backend ([938d928](https://github.com/loonghao/auroraview/commit/938d92884d2f0631a6743da20617f489ef6f3a59))


### Documentation

* **badges:** add PyPI, Python versions, downloads(pepy), Codecov and PR Checks badges to README/README_zh; fix CI badge to pr-checks.yml\n\nci(coverage): ensure pytest XML coverage uploaded (essentials+qt) and rust doc-test coverage via llvm-cov\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([a1bf2e6](https://github.com/loonghao/auroraview/commit/a1bf2e6f04b034d43a9d718eb903b97eb394c59c))
* document auroraview.call parameter encoding ([7677b51](https://github.com/loonghao/auroraview/commit/7677b51ea0b60188ccb113ff01e89975cd4fc3cf))
* **maya:** qt import via qtpy; finalize NativeWebView -&gt; WebView.create migration\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([b860f83](https://github.com/loonghao/auroraview/commit/b860f835a2fd185cbb6c729d52d7f55b6c8c70f7))
* **qt:** replace PySide2 imports with qtpy across proposal/research docs for consistency\n\n- QT_INTEGRATION_PROPOSAL.md: QWidget/QDialog/QWebEngine* and QtCore -&gt; qtpy\n- RESEARCH_FLET_PYWEBVIEW.md: QWebEngineView -&gt; qtpy import\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([0099469](https://github.com/loonghao/auroraview/commit/0099469f93f9c7f317679c99c229c369ebac134c))
* **readme,maya:** update API references for qtpy + WebView.create; add run_embedded + EventTimer off_* examples\n\n- README/README_zh: add Embedded helper and deregistration samples\n- MAYA_INTEGRATION: migrate NativeWebView -&gt; WebView.create; process_events public API; fix QWidget import and HWND cast\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([07f0736](https://github.com/loonghao/auroraview/commit/07f073666d25af425093436691fd7a2789ae41b0))
* **readme:** add CI/CodeQL/release badges and quick links to CoC/Security ([f9b0c79](https://github.com/loonghao/auroraview/commit/f9b0c791d2c9f61e4f0e830a300499ff91e95aa0))
* **readme:** enrich badges (stars/downloads/activity/issues/cc/mypy/ruff/dependabot/release-please) ([803d1e6](https://github.com/loonghao/auroraview/commit/803d1e6a8ef01715b4f0947542e198f0c93cae41))
* unify API examples to WebView.create and qtpy; fix event processing references; fix pre-commit clippy flag ([44a0a51](https://github.com/loonghao/auroraview/commit/44a0a516fa604447970d141be83d5b3718790691))

## [0.2.4](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.3...auroraview-v0.2.4) (2025-11-12)


### Features

* add __init__.py to example packages and update import docs ([b9acd72](https://github.com/loonghao/auroraview/commit/b9acd7256e29fb61897110cb0d8cf9cd7aef33b8))
* add auto-ready bridge with Qt-style API ([556e84e](https://github.com/loonghao/auroraview/commit/556e84ec6b9e7f46d994c7234c4e1009170f4441))
* add Qt-style signal/slot system for robust event binding ([8f8908b](https://github.com/loonghao/auroraview/commit/8f8908b7de3fc90cb8c4e9090bce3644d2a15a7c))
* **service-discovery:** add module sources (mod, port allocator, python bindings) for CI build\n\n- Add missing service_discovery sources required by new http_discovery tests\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([bc07782](https://github.com/loonghao/auroraview/commit/bc0778256dd4be3ebd3a0f9ccd3a4bb331da70fe))


### Bug Fixes

* change doctest code blocks from text to python to prevent compilation ([cbb0c6b](https://github.com/loonghao/auroraview/commit/cbb0c6b2e400613f0ce53460741c3171107b1c9e))
* **ci, rust:** resolve pytest import error on Windows CI and silence clippy dead_code/unused warnings\n\n- Revert Qt test invocation to 'uv run python -m pytest' (fix No module named pytest)\n- Force software rendering already applied in previous commits\n- Silence Rust warnings to pass -D warnings in CI:\n  * Gate Duration imports with cfg and remove unused imports\n  * Prefix unused function params with underscore on non-Windows\n  * Add #[allow(dead_code)] for public API and platform stubs\n  * Linux platform module: #![allow(dead_code)] and import cleanup\n- Non-Windows message_pump is_window_valid marked #[allow(dead_code)]\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([24e3b7f](https://github.com/loonghao/auroraview/commit/24e3b7f76edbcc776361fbf9de89e850859c91b8))
* **ci:** silence Rust dead_code warnings and harden Qt Windows tests\n\n- timer.rs: cfg-gate should_tick to windows|test to avoid dead_code under clippy all-targets\n- message_pump.rs: add #[allow(dead_code)] to non-windows stub\n- pr-checks.yml: add WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS to disable GPU in headless CI\n- python: format with ruff to satisfy --check\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([737edae](https://github.com/loonghao/auroraview/commit/737edae4cc9d1f66d1358258edd0ea154e3bb1cc))
* handle Qt warnings on Nuke window close gracefully ([957d893](https://github.com/loonghao/auroraview/commit/957d893ef3a94b9d796d7c047a3f090f295ef061))
* implement complete window.auroraview API in initialization scripts ([293dd5c](https://github.com/loonghao/auroraview/commit/293dd5cb73764c9f49d7f59ffd14579672fe6ba8))
* improve Qt backend import error handling for Maya users ([aaf601d](https://github.com/loonghao/auroraview/commit/aaf601dc17ce9aedab08bfcba8b7567690cbf71c))
* inline AuroraViewBridge in test scripts to avoid file loading issues ([6a4ddd7](https://github.com/loonghao/auroraview/commit/6a4ddd70d79a021467c1e83b68769bd79b8eaeb1))
* prevent Nuke from hanging on exit after WebView close ([c84d0f3](https://github.com/loonghao/auroraview/commit/c84d0f3dbd315aae7250c07ecf26a556abf26d69))
* **py:** restore backwards-compat API for tests (on_event, NativeWebView, show_async) ([67bda7c](https://github.com/loonghao/auroraview/commit/67bda7c332beaf3925885abbb2a5a9d4827b0fab))
* **qt:** export _HAS_QT and AuroraViewQt; use qtpy QWebEngineSettings for backend-agnostic devtools; expose alias in qt_integration\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([ed09760](https://github.com/loonghao/auroraview/commit/ed097600b80331a030d2f311e226c76d4ea68a49))
* remove duplicate win module and add dead_code allows ([45c5c9f](https://github.com/loonghao/auroraview/commit/45c5c9fa26b770eafb7512a42f779eaf14d2d153))
* resolve all clippy warnings ([337f9c5](https://github.com/loonghao/auroraview/commit/337f9c5caabd0291b60e6f5544dc1af553eba51f))
* resolve CI lint failures and update deprecated PyO3 APIs ([eb123f8](https://github.com/loonghao/auroraview/commit/eb123f807b6f8710eb9731383e7c49ab4ac5f46b))
* resolve release workflow error and update documentation ([d061a54](https://github.com/loonghao/auroraview/commit/d061a547ce910417108bbf9887c6adbe69db5e81))
* use pytest directly instead of uv run to access built extension ([b05550e](https://github.com/loonghao/auroraview/commit/b05550eb02581e175c1222bf8d8a3df139762bfc))


### Code Refactoring

* cleanup codebase and enhance examples ([0657b3e](https://github.com/loonghao/auroraview/commit/0657b3e2084b322b8ed77b772b3364225a4fc352))
* migrate all Nuke examples to simplified API ([fcebb21](https://github.com/loonghao/auroraview/commit/fcebb21a0dcb285861e427e96cd6d5e5d8765e9a))
* rename example directories to avoid DCC namespace conflicts ([3db8d30](https://github.com/loonghao/auroraview/commit/3db8d30a33aa5dced5dccc63f2abb29bbc0eefdb))
* unify WebView API and remove compatibility layers\n\n- Remove DCC-specific factories (maya/houdini/blender), for_dcc(), process_messages(), and NativeWebView\n- Keep a single entry point: WebView.create(...) with mode=auto (parent -&gt; owner automatically)\n- Fix: expose show_async() as non-blocking helper (equiv. to show(wait=False))\n- Tests: align with unified API; ensure multiple show_async calls are idempotent\n- Docs: simplify DCC examples to rely on parent only (mode implicit)\n\nSigned-off-by: longhao &lt;hal.long@outlook.com&gt; ([120e7b6](https://github.com/loonghao/auroraview/commit/120e7b6191026a33d9828c337f1a8d636c21cb0a))


### Documentation

* add comprehensive installation guides for DCC environments ([f75f225](https://github.com/loonghao/auroraview/commit/f75f225378e4e54ef96297ab6a22e8cc8d7c5a09))
* add comprehensive Nuke IPC testing guide ([a2a311c](https://github.com/loonghao/auroraview/commit/a2a311c4c95c26a6eb298fef86155e44360b84f0))
* add simplified API guide ([743be1f](https://github.com/loonghao/auroraview/commit/743be1f532b69e447869e210f81907bc806555e4))
* add white screen troubleshooting guide and diagnostic tools ([5b55752](https://github.com/loonghao/auroraview/commit/5b55752ff8bbce02b6e21be3d240d7a188ff45a4))
* move examples to separate repository and update README ([1dfd755](https://github.com/loonghao/auroraview/commit/1dfd75546e4cc30df615a6317d96a23957999cd5))

## [0.2.3](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.2...auroraview-v0.2.3) (2025-11-01)


### Bug Fixes

* build only universal2 wheels on macOS ARM64 runners ([f4f26d3](https://github.com/loonghao/auroraview/commit/f4f26d3c386fac9d4098f5ca4e02d6a038626cdf))
* exclude Linux wheels from PyPI and update installation docs ([222f69b](https://github.com/loonghao/auroraview/commit/222f69be41704b5cb71de33b60b7a78345d10633))

## [0.2.2](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.1...auroraview-v0.2.2) (2025-11-01)


### Bug Fixes

* build Linux wheels on host instead of manylinux container ([a42a2ea](https://github.com/loonghao/auroraview/commit/a42a2ea554cb178e5d34ebba6bb82ac9ff10355e))
* install system dependencies in manylinux container and add wheel build test to PR checks ([583bc1a](https://github.com/loonghao/auroraview/commit/583bc1a11ac0d651e7c92ba8a905e0f66a8fb988))
* remove --compatibility flag when manylinux is off ([32706ec](https://github.com/loonghao/auroraview/commit/32706ecc4ea46b60cc69038ff19b56eba55604a6))

## [0.2.1](https://github.com/loonghao/auroraview/compare/auroraview-v0.2.0...auroraview-v0.2.1) (2025-11-01)


### Bug Fixes

* resolve CI build and deployment issues ([0af4121](https://github.com/loonghao/auroraview/commit/0af41218c12b3f431c1c555202901730eead1283))

## [0.2.0](https://github.com/loonghao/auroraview/compare/auroraview-v0.1.0...auroraview-v0.2.0) (2025-11-01)


### ⚠ BREAKING CHANGES

* WebView initialization now requires explicit backend selection

### Features

* add comprehensive testing framework and backend extension support ([5f1ede3](https://github.com/loonghao/auroraview/commit/5f1ede3888b228a80514702a0a16e34584bfc257))
* add decorations parameter to control window title bar ([a41dadc](https://github.com/loonghao/auroraview/commit/a41dadcb8f650707f90c72f5a2114857467a0d06))
* add embedded WebView integration for Maya ([98f3c6b](https://github.com/loonghao/auroraview/commit/98f3c6b9d3fbe0f655aab6128c38ffb18b91e843))
* add factory methods and tree view for better UX ([671318c](https://github.com/loonghao/auroraview/commit/671318c7a32029bc98c4dad001dd4b457eeb162d))
* add non-blocking show_async() method for DCC integration ([790a750](https://github.com/loonghao/auroraview/commit/790a750a57beb109200ec2a292e86ba155ebb74b))
* add performance optimization infrastructure and Servo evaluation ([6b89036](https://github.com/loonghao/auroraview/commit/6b8903620708933c020add120218ec3ffc606ce2))
* add thread-safe event queue for DCC integration ([77bf270](https://github.com/loonghao/auroraview/commit/77bf27036879a6482c12c1f1006a13587d075ecb))
* enhance Maya integration and backend architecture ([cbb9e86](https://github.com/loonghao/auroraview/commit/cbb9e861f67f358062fe3f9693b851099d9e2eac))
* initial project setup with comprehensive tests and CI/CD ([99ae846](https://github.com/loonghao/auroraview/commit/99ae8461d54475cb40fc6cfa851d7de9f96a7c8c))


### Bug Fixes

* add missing libgio-2.0-dev dependency for Linux builds ([ab2ab0b](https://github.com/loonghao/auroraview/commit/ab2ab0bdcbb2b269d851b4419ba375a36a73269b))
* add platform-specific allow attributes for CI lint compliance ([b324a80](https://github.com/loonghao/auroraview/commit/b324a806b0d421f97e248fb4b4ccb5d946923c1b))
* add system dependencies for CI builds ([7cff90d](https://github.com/loonghao/auroraview/commit/7cff90d809a8e01189b246c62bf98218f992c13f))
* allow event loop creation on any thread for DCC integration ([405b0c2](https://github.com/loonghao/auroraview/commit/405b0c25fa34e87eb07115ce7a1477bc4ef22df1))
* change daemon thread to False and document threading issues ([08840e9](https://github.com/loonghao/auroraview/commit/08840e91bec23ffa67ba99f890b7c02605fbed00))
* correct CI workflow YAML structure ([d048752](https://github.com/loonghao/auroraview/commit/d048752a6c928de570252ce3b65aa765b0b696d5))
* correct system dependency package name for Linux builds ([8170478](https://github.com/loonghao/auroraview/commit/8170478a30c19b1645118592591657f845554de3))
* disable manylinux and use correct Ubuntu 24.04 webkit package ([ef46e3d](https://github.com/loonghao/auroraview/commit/ef46e3d97e519ca8d1bc5d34de63a069306009a7))
* improve module loading for Maya environment ([d0a120b](https://github.com/loonghao/auroraview/commit/d0a120bca6b55e2db8cd811b6a7b3f0e19f1ef14))
* organize imports and remove unused imports in test_webview.py ([5f062b5](https://github.com/loonghao/auroraview/commit/5f062b50f2fe161dd3689383a7edc27a21aa5b4b))
* Python 3.7 compatibility and tree view initialization ([45a85fc](https://github.com/loonghao/auroraview/commit/45a85fcfae5955ae9be8f616adb3b7e19adb2141))
* remove problematic rustflags that break CI builds ([ba4bac9](https://github.com/loonghao/auroraview/commit/ba4bac9b63b62c145bc8c0f2cf156ab9f1e230df))
* remove unsupported Linux i686 build target ([5e84bbc](https://github.com/loonghao/auroraview/commit/5e84bbc7ac8a0166e7e2e0964a04cc5b419e6744))
* remove unused imports and mut variables for CI compliance ([a66bf2a](https://github.com/loonghao/auroraview/commit/a66bf2a7b95004c8c0089c1b5cfa24940970dff2))
* resolve all clippy lint errors and code formatting issues ([c3a666d](https://github.com/loonghao/auroraview/commit/c3a666df309838b162ddda6f0fcf79bed3054e19))
* resolve all Rust compiler warnings ([0b921a2](https://github.com/loonghao/auroraview/commit/0b921a269f6a3a2a89ea8593e9c9ef317f84f05f))
* resolve CI lint errors for production readiness ([d1283ba](https://github.com/loonghao/auroraview/commit/d1283ba368ee8609fae09f02d1afdc310574fcf2))
* resolve CI lint errors for production readiness ([500e34d](https://github.com/loonghao/auroraview/commit/500e34d2506fcb9771beea30d160313e3bbda6d6))
* resolve CI linting and coverage issues ([bf2a6d5](https://github.com/loonghao/auroraview/commit/bf2a6d5ff8ed76eeb125a57ab7cd6aa417bfde18))
* resolve close button bug using event loop proxy pattern ([c42c233](https://github.com/loonghao/auroraview/commit/c42c2338cf6aa15f576af4092db80f1d25315b1f))
* resolve JavaScript syntax errors in Maya outliner example ([c91647b](https://github.com/loonghao/auroraview/commit/c91647b70187ee534751b5365835fb1299f4fd1f))
* resolve Linux glib-sys and Windows architecture build errors ([fbd0933](https://github.com/loonghao/auroraview/commit/fbd0933af35462f96fb7cdcfeadf533aba78a626))
* resolve Maya freezing issue by using correct threading model ([1d60a13](https://github.com/loonghao/auroraview/commit/1d60a130f57ff58ce13839c6a72bb4a6223b2661))
* resolve thread safety issue in show_async() ([f2874da](https://github.com/loonghao/auroraview/commit/f2874daf791535839d694037d85726ccb8145bf1))
* update ci-install command to use optional-dependencies instead of dependency-groups ([1ebf39b](https://github.com/loonghao/auroraview/commit/1ebf39b83b1ec321ade75c594e394b4e6c8b234a))
* upgrade PyO3 to 0.24.2 and fix deprecated API usage ([da4541a](https://github.com/loonghao/auroraview/commit/da4541a01136f522194c761f3a6e02743ce21f41))
* use correct Ubuntu package names for GTK dependencies ([f0c619c](https://github.com/loonghao/auroraview/commit/f0c619c068dab597a5b062b80050b1a549177c9d))


### Code Refactoring

* implement modular backend architecture with native and qt support ([fd46e3d](https://github.com/loonghao/auroraview/commit/fd46e3dd4724b348c092a24b62d4d09804734677))
* migrate to PEP 735 dependency-groups following PyRustor pattern ([bd4db4e](https://github.com/loonghao/auroraview/commit/bd4db4e4185aecda8096c8f502f0ddd9fdc39ea7))
* remove unused event_loop_v2.rs ([22a4746](https://github.com/loonghao/auroraview/commit/22a4746707069b9415e06aa67d7b99009dd8a1a9))
* rename PyWebView to AuroraView ([4834842](https://github.com/loonghao/auroraview/commit/48348420f23475c1d4090286eb030d741e48161b))


### Documentation

* add action plan for user testing ([75e4322](https://github.com/loonghao/auroraview/commit/75e432247c54c9beacf1f31dad057f5ebbb4ac3d))
* add CI testing setup summary ([6dcfc7f](https://github.com/loonghao/auroraview/commit/6dcfc7fa3b270379b04f8a317b7cf63b01a7048c))
* add complete solution summary ([f2b3c7d](https://github.com/loonghao/auroraview/commit/f2b3c7d7b797c384e21f6b4f22bd874d3c2042cf))
* add comprehensive local test summary with coverage report ([002b415](https://github.com/loonghao/auroraview/commit/002b415539c69927875a6deff544a9ea4a37fad1))
* add comprehensive Maya integration summary ([90dd29f](https://github.com/loonghao/auroraview/commit/90dd29fe18a914bc078c28f663b4960571c5006c))
* add comprehensive Maya testing examples and guides ([bf268b6](https://github.com/loonghao/auroraview/commit/bf268b63be89c7eaeb3672d9d6767580d8979d9e))
* add comprehensive Maya testing guide ([d9db98b](https://github.com/loonghao/auroraview/commit/d9db98b0bacef06f40416622cefba094acde173b))
* add comprehensive testing guide with just commands ([1e70bd1](https://github.com/loonghao/auroraview/commit/1e70bd174b72ce7e2b6d786e1c4d859078653caf))
* add comprehensive threading diagnosis and fix guide ([463c10d](https://github.com/loonghao/auroraview/commit/463c10d67e287f7070e020b1a454c978bb50c039))
* add critical fix instructions for .pyd file update ([04fff27](https://github.com/loonghao/auroraview/commit/04fff276cd7a2ff438a5087d6d23a382087fac29))
* add detailed testing instructions for Maya integration ([8c077a7](https://github.com/loonghao/auroraview/commit/8c077a71f8dfe613ce7d2ea2cffd1f5dcc920f1a))
* add event loop fix documentation ([e4f200b](https://github.com/loonghao/auroraview/commit/e4f200b5337b68f299872e80f6939dd07662ba45))
* add final CI/CD fixes summary ([16196ea](https://github.com/loonghao/auroraview/commit/16196ea9ae64d88a14ddde471056facb64f7a950))
* add final summary of Maya WebView integration ([641b00e](https://github.com/loonghao/auroraview/commit/641b00e6ab73e82af73c53b71f6b4b5ff46fc3bc))
* add final threading issues summary ([d299e72](https://github.com/loonghao/auroraview/commit/d299e72dab05a24e031189820bfb97fb747b9a09))
* add fix summary documentation ([5c5fed7](https://github.com/loonghao/auroraview/commit/5c5fed7395e8bbebb6deb854323841a82d522e38))
* add Maya integration README ([0ee0aef](https://github.com/loonghao/auroraview/commit/0ee0aef41b3045511c8bcb29c941858a1fdd4fe7))
* add Maya quick start guide ([feb2cca](https://github.com/loonghao/auroraview/commit/feb2ccab1ef372da43e201806e6044220f3b27b8))
* add next steps for testing event loop fix ([86800e8](https://github.com/loonghao/auroraview/commit/86800e856e8013ea000d39c2589791c7c01d4c96))
* add rebuild instructions for event loop fix ([09f3fef](https://github.com/loonghao/auroraview/commit/09f3fefaad006015950d87662a769db42f853a51))
* add threading solution summary ([08ea57f](https://github.com/loonghao/auroraview/commit/08ea57f9905199cecbddf68e58a0f42772f6f794))
* reorganize examples with clear structure and documentation ([29198b5](https://github.com/loonghao/auroraview/commit/29198b51599a783f394358cd66ea80c158eadc9a))
* update CI fixes summary to reflect removal of i686 support ([2a8e996](https://github.com/loonghao/auroraview/commit/2a8e9968c83fb92643baf67dcda28932f045e141))
* update quick start guide with thread safety fix ([02dee4d](https://github.com/loonghao/auroraview/commit/02dee4d826d06dcea4a08e17ad672fc48300e330))
* update quick start with embedded mode recommendations ([d0b0f1f](https://github.com/loonghao/auroraview/commit/d0b0f1f990cf588003acad4169e4cfad4468486d))
* update testing instructions with event loop fix ([dee4158](https://github.com/loonghao/auroraview/commit/dee4158980d79a5a9b30885967b495af2738454b))

## [0.1.0] - 2025-10-28

### Added
- Initial release of AuroraView
- Rust-powered WebView for Python applications
- DCC (Digital Content Creation) software integration support
- PyO3 bindings with abi3 support for Python 3.7+
- WebView builder API with configuration options
- Event system for bidirectional communication between Python and JavaScript
- Support for Maya, 3ds Max, Houdini, and Blender
- Cross-platform support (Windows, macOS, Linux)
- Comprehensive test suite
- Documentation and examples

### Features
- Lightweight WebView framework (~5MB vs ~120MB for Electron)
- Fast performance with <30MB memory footprint
- Seamless DCC integration
- Modern web stack support (React, Vue, etc.)
- Type-safe Rust implementation
- Cross-platform compatibility
