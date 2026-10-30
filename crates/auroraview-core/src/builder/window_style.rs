//! Window style utilities for WebView embedding
//!
//! This module provides platform-specific window style manipulation
//! for embedding WebView as a child window or setting owner relationships.
//!
//! # Window Relationships on Windows
//!
//! ## Child Window (WS_CHILD)
//! - Window is contained within parent's client area
//! - Cannot be moved independently
//! - Coordinates relative to parent
//! - Use for: Embedding WebView in Qt widgets
//!
//! ## Owner Window (GWLP_HWNDPARENT)
//! - Window stays above owner in Z-order
//! - Hidden when owner is minimized
//! - Destroyed when owner is destroyed
//! - Can be positioned freely on screen
//! - Use for: Floating tool windows, dialogs
//!
//! # Official Documentation
//! - [Window Features](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)
//! - [SetWindowLongPtrW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw)

#[cfg(target_os = "windows")]
use windows::Win32::Foundation::HWND;
#[cfg(target_os = "windows")]
use windows::Win32::Graphics::Dwm::{
    DwmExtendFrameIntoClientArea, DwmSetWindowAttribute, DWMWA_NCRENDERING_POLICY,
};
#[cfg(target_os = "windows")]
use windows::Win32::UI::Controls::MARGINS;
#[cfg(target_os = "windows")]
use windows::Win32::UI::WindowsAndMessaging::{
    CallWindowProcW, DispatchMessageW, GetParent, GetWindowLongPtrW, GetWindowLongW, PeekMessageW,
    SetParent, SetWindowLongPtrW, SetWindowLongW, SetWindowPos, TranslateMessage, GWLP_HWNDPARENT,
    GWLP_WNDPROC, GWL_EXSTYLE, GWL_STYLE, MSG, PM_REMOVE, SWP_FRAMECHANGED, SWP_NOACTIVATE,
    SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, WNDPROC, WS_BORDER, WS_CAPTION, WS_CHILD,
    WS_CLIPCHILDREN, WS_DLGFRAME, WS_EX_CLIENTEDGE, WS_EX_CONTEXTHELP, WS_EX_DLGMODALFRAME,
    WS_EX_STATICEDGE, WS_EX_TOOLWINDOW, WS_EX_WINDOWEDGE, WS_POPUP, WS_THICKFRAME,
};

/// Options for applying child window style
#[derive(Debug, Clone, Copy, Default)]
pub struct ChildWindowStyleOptions {
    /// Whether to force window position to (0, 0) within parent
    /// Set to true for DCC/Qt embedding, false for standalone mode
    pub force_position: bool,
}

impl ChildWindowStyleOptions {
    /// Create options for DCC/Qt embedding (forces position to 0,0)
    pub fn for_dcc_embedding() -> Self {
        Self {
            force_position: true,
        }
    }

    /// Create options for standalone mode (preserves position)
    pub fn for_standalone() -> Self {
        Self {
            force_position: false,
        }
    }
}

/// Result of applying child window style
#[derive(Debug)]
pub struct ChildWindowStyleResult {
    /// Original window style
    pub old_style: i32,
    /// New window style
    pub new_style: i32,
    /// Original extended style
    pub old_ex_style: i32,
    /// New extended style
    pub new_ex_style: i32,
}

/// Subclass a window to intercept `WM_NCCALCSIZE` and force zero non-client area.
///
/// tao's `Window Class` WndProc may return a non-zero NC region even after all
/// border/caption style bits are removed. This function subclasses the HWND so that
/// `WM_NCCALCSIZE` always sets the client rect equal to the window rect (NC = 0).
///
/// The original WndProc is stored per-HWND in a global map and forwarded for
/// all other messages.
///
/// # Implementation outline
///
/// The install path is a 4-phase state machine, intentionally split into
/// small helpers so reviewers can read it linearly without having to skim
/// 200 lines of inline `SAFETY` text:
///
///   1. [`claim_subclass_slot`] — atomically reserve the per-HWND map
///      entry with a sentinel under the lock. Concurrent callers
///      short-circuit on `contains_key`.
///   2. [`install_subclass_wndproc`] — call `SetWindowLongPtrW` and
///      detect failure via the `GetLastError` MSDN contract; on
///      failure roll the sentinel back so a retry can run.
///   3. [`upgrade_subclass_slot`] — replace the sentinel with the
///      real previous WndProc so non-`WM_NCCALCSIZE` forwarding works.
///      From this point on, re-entrant lookups from the WM_NCCALCSIZE
///      cascade find the real entry.
///   4. [`commit_subclass_frame`] — `SetWindowPos(SWP_FRAMECHANGED)`
///      to make Windows re-run the NC pass with our subclass active.
///
/// The lock MUST be released between phases 1 and 2 because phase 4's
/// `SWP_FRAMECHANGED` synchronously dispatches `WM_NCCALCSIZE` into
/// [`nc_subclass_wndproc`] on this same thread (parking_lot Mutex is
/// not reentrant). The sentinel keeps that re-entrant lookup correct
/// even though the entry isn't yet pointing at the real original.
///
/// # Safety
/// Uses unsafe Win32 subclassing APIs.
#[cfg(target_os = "windows")]
pub fn subclass_for_zero_nc_area(hwnd: isize) {
    use parking_lot::Mutex;
    use std::collections::HashMap;
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
    use windows::Win32::UI::WindowsAndMessaging::DefWindowProcW;

    const WM_NCCALCSIZE: u32 = 0x0083;

    /// Global map of original WndProcs, keyed by HWND value.
    ///
    /// Map entry semantics:
    ///   * absent           — HWND has not been (and is not currently being) subclassed.
    ///   * `Some(SENTINEL)` — install is in flight on another thread; treat as
    ///     "subclass not yet ready" (forward to `DefWindowProcW` instead of
    ///     trying to call the sentinel address as a wndproc).
    ///   * `Some(orig)`     — install completed; `orig` is the real previous
    ///     WndProc and must receive every non-WM_NCCALCSIZE message.
    static ORIGINAL_WNDPROCS: Mutex<Option<HashMap<isize, isize>>> = Mutex::new(None);

    /// Custom WndProc that zeroes out the NC area.
    ///
    // SAFETY: This function is registered as a window procedure via SetWindowLongPtrW.
    // It is called by Windows with valid HWND/WPARAM/LPARAM for the subclassed window.
    // The original WndProc stored in ORIGINAL_WNDPROCS is guaranteed valid because
    // it was obtained from GetWindowLongPtrW on a live window.
    unsafe extern "system" fn nc_subclass_wndproc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        if msg == WM_NCCALCSIZE && wparam.0 != 0 {
            // wparam == TRUE: lparam points to NCCALCSIZE_PARAMS.
            // The first RECT (rgrc[0]) is the proposed window rect.
            // By returning 0 without modifying it, Windows treats the entire
            // window rect as the client rect → NC area = 0.
            return LRESULT(0);
        }

        // Forward everything else to the original WndProc.
        //
        // Sentinel guard: if the map currently holds the sentinel value
        // (the address of *this* function), it means
        // [`install_subclass_wndproc`] has just installed us via
        // `SetWindowLongPtrW` but [`upgrade_subclass_slot`] has not
        // yet replaced the sentinel with the real original. Calling
        // the sentinel as a wndproc would re-enter
        // `nc_subclass_wndproc` and recurse forever. Falling back to
        // `DefWindowProcW` is the documented safe default for an
        // un-handled message.
        let self_addr = nc_subclass_wndproc as *const () as usize as isize;
        let original = ORIGINAL_WNDPROCS
            .lock()
            .as_ref()
            .and_then(|map| map.get(&(hwnd.0 as isize)).copied())
            .filter(|orig| *orig != self_addr);

        if let Some(orig) = original {
            let wndproc: WNDPROC = std::mem::transmute(orig);
            CallWindowProcW(wndproc, hwnd, msg, wparam, lparam)
        } else {
            DefWindowProcW(hwnd, msg, wparam, lparam)
        }
    }

    /// Outcome of [`claim_subclass_slot`].
    enum SlotClaim {
        /// Slot is ours. The caller MUST proceed to install / upgrade /
        /// commit; on any abort path the sentinel must be rolled back
        /// via `ORIGINAL_WNDPROCS.lock().as_mut().map(|m| m.remove(...))`.
        Acquired { original: isize },
        /// Either an install is already in flight on another thread
        /// (sentinel present) or the subclass was previously installed
        /// (real entry present). Both are no-ops.
        AlreadyHandled,
        /// `GetWindowLongPtrW` returned 0 — the HWND is no longer
        /// valid, or the caller passed a non-window handle. We log
        /// and bail out without touching the map.
        InvalidHwnd,
    }

    /// Phase 1: claim the per-HWND map slot atomically with a sentinel.
    ///
    /// Inserting `self_addr` (the address of [`nc_subclass_wndproc`]
    /// itself) under the lock both dedupes concurrent callers AND gives
    /// the WM_NCCALCSIZE forward path a way to detect the "install in
    /// progress" window. Without it, a concurrent caller could see an
    /// empty map, race past the `contains_key` check, and end up
    /// double-installing the subclass — the later install would
    /// overwrite the earlier one's record of the *real* original
    /// wndproc, leaking it forever.
    ///
    /// The sentinel value is `nc_subclass_wndproc as isize`, which is
    /// guaranteed never to match a legitimate "original" wndproc on
    /// this HWND: legitimate originals are whatever was registered
    /// *before* phase 2, and phase 2 is what installs
    /// `nc_subclass_wndproc` for the first time.
    ///
    /// The lock is released as soon as this function returns. See the
    /// rationale on [`subclass_for_zero_nc_area`] for why this is
    /// mandatory before phase 2's `SetWindowPos(SWP_FRAMECHANGED)`.
    unsafe fn claim_subclass_slot(hwnd: isize, hwnd_win: HWND, self_addr: isize) -> SlotClaim {
        let mut guard = ORIGINAL_WNDPROCS.lock();
        let map = guard.get_or_insert_with(HashMap::new);
        if map.contains_key(&hwnd) {
            return SlotClaim::AlreadyHandled;
        }
        let orig = GetWindowLongPtrW(hwnd_win, GWLP_WNDPROC);
        if orig == 0 {
            tracing::warn!(
                "subclass_for_zero_nc_area: GetWindowLongPtrW returned 0 for HWND 0x{:X}",
                hwnd
            );
            return SlotClaim::InvalidHwnd;
        }
        // Stake the claim with the sentinel; concurrent callers will
        // now hit the `contains_key` short-circuit above.
        map.insert(hwnd, self_addr);
        SlotClaim::Acquired { original: orig }
    }

    /// Roll the slot back to "absent". Called when phase 2 fails.
    fn release_subclass_slot(hwnd: isize) {
        let mut guard = ORIGINAL_WNDPROCS.lock();
        if let Some(map) = guard.as_mut() {
            map.remove(&hwnd);
        }
    }

    /// Phase 2: install the new WndProc.
    ///
    /// Per MSDN, `SetWindowLongPtrW` returns the previous value on
    /// success and 0 on failure — but the previous value can
    /// legitimately be 0 too, so the unambiguous failure check is
    /// `prev == 0 && GetLastError() != 0`. We clear the thread error
    /// first to avoid reading stale state.
    ///
    /// On failure we roll the sentinel back via
    /// [`release_subclass_slot`] so a later retry can proceed.
    unsafe fn install_subclass_wndproc(hwnd: isize, hwnd_win: HWND, self_addr: isize) -> bool {
        use windows::Win32::Foundation::{GetLastError, SetLastError, WIN32_ERROR};

        SetLastError(WIN32_ERROR(0));
        let prev = SetWindowLongPtrW(hwnd_win, GWLP_WNDPROC, self_addr);
        if prev == 0 {
            let err = GetLastError();
            if err.0 != 0 {
                tracing::error!(
                    "subclass_for_zero_nc_area: SetWindowLongPtrW failed for HWND 0x{:X}, \
                     GetLastError=0x{:08X}",
                    hwnd,
                    err.0
                );
                release_subclass_slot(hwnd);
                return false;
            }
        }
        true
    }

    /// Phase 3: upgrade the sentinel to the real original WndProc so
    /// the subclass can forward non-WM_NCCALCSIZE messages.
    ///
    /// From this point on, WM_NCCALCSIZE re-entries from phase 4's
    /// `SetWindowPos` find the real entry (not the sentinel) and
    /// dispatch correctly.
    fn upgrade_subclass_slot(hwnd: isize, original: isize) {
        let mut guard = ORIGINAL_WNDPROCS.lock();
        let map = guard.get_or_insert_with(HashMap::new);
        map.insert(hwnd, original);
    }

    /// Phase 4: trigger NC frame re-calculation so the subclass takes
    /// effect immediately.
    ///
    /// `SWP_FRAMECHANGED` synchronously dispatches `WM_NCCALCSIZE`
    /// into [`nc_subclass_wndproc`] on this thread; the lookup now
    /// finds the real original and the cascade returns cleanly.
    unsafe fn commit_subclass_frame(hwnd_win: HWND) {
        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
    }

    // SAFETY: hwnd is a valid window handle provided by the caller (guaranteed by
    // the `# Safety` contract). All Win32 calls below operate on this valid HWND
    // or stack-local data. The transmute of the original WndProc pointer to WNDPROC
    // (inside `nc_subclass_wndproc`) is safe because the value was obtained from
    // `GetWindowLongPtrW` on the same HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);
        let self_addr = nc_subclass_wndproc as *const () as usize as isize;

        let original = match claim_subclass_slot(hwnd, hwnd_win, self_addr) {
            SlotClaim::Acquired { original } => original,
            SlotClaim::AlreadyHandled | SlotClaim::InvalidHwnd => return,
        };

        if !install_subclass_wndproc(hwnd, hwnd_win, self_addr) {
            return;
        }

        upgrade_subclass_slot(hwnd, original);
        commit_subclass_frame(hwnd_win);

        tracing::info!(
            "Subclassed HWND 0x{:X} for zero NC area (WM_NCCALCSIZE interception)",
            hwnd
        );
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn subclass_for_zero_nc_area(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Drain pending Win32 messages on the *current* thread's queue.
///
/// # Why this is needed
///
/// In DCC-embedded mode (Maya/Houdini/3ds Max + Qt), the host's main thread
/// owns the message loop. When we are deep inside a synchronous Python → Rust
/// call (e.g. `core.show_embedded()`), the host's `GetMessage` loop is paused —
/// any messages produced during our Rust work pile up on this thread's queue.
///
/// Several Win32 calls used by `apply_child_window_style`
/// (`SetWindowLongW`, `SetParent`, `SetWindowPos`) trigger **synchronous**
/// `SendMessage` cascades to the modified window AND its descendants
/// (notably the WebView2 `Chrome_WidgetWin_*` child windows). For windows
/// owned by the **same thread**, `SendMessage` calls the target's `WndProc`
/// inline — but if the target's `WndProc` performs COM marshaling (which
/// WebView2 frequently does), the COM runtime needs the STA's message
/// pump to deliver its own asynchronous responses. With no pump running,
/// the call deadlocks.
///
/// Pumping a single round of pending messages right before / after each
/// big style mutation is the minimum invasive fix: it lets every pending
/// `WM_*` reach its `WndProc` (including any COM RPC reply windows) so the
/// next synchronous `SendMessage` cascade does not pile on top of an
/// already-saturated queue.
///
/// # Scope filter
///
/// `hwnd_filter`:
///   * `Some(hwnd)` — only drain messages targeted at `hwnd` (and its
///     descendants per `PeekMessageW` semantics). Use this in DCC-embedded
///     paths to avoid disturbing the host's own message stream
///     (e.g. Maya/Qt `WM_PAINT` / `WM_TIMER`).
///   * `None` — drain all messages on this thread's queue. Use only when
///     the calling code owns the thread's message loop (standalone / tests).
///
/// # Tracing
///
/// `reason` is a short, static label (e.g. `"pre-style"`,
/// `"post-set-parent"`, `"post-set-window-pos"`) that is logged alongside
/// the dispatched count. It lets diagnostics tell which step in
/// `apply_child_window_style` produced the queue pressure without having
/// to walk the stack.
///
/// This is a *bounded* operation: we drain at most `cap` messages so we
/// can never spin forever if the host keeps producing messages.
#[cfg(target_os = "windows")]
pub(crate) fn drain_thread_messages_for(hwnd_filter: Option<HWND>, cap: u32, reason: &'static str) {
    // SAFETY: PeekMessageW / TranslateMessage / DispatchMessageW are documented
    // Win32 APIs; we own the call (no foreign references) and the MSG buffer
    // is stack-local. No memory safety concerns.
    unsafe {
        let mut msg = MSG::default();
        let mut n: u32 = 0;
        while n < cap && PeekMessageW(&mut msg, hwnd_filter, 0, 0, PM_REMOVE).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
            n += 1;
        }

        // Distinguish three observable outcomes so diagnostics are not silent
        // when the queue is actually saturated:
        //   * n == 0       — quiet path, do nothing.
        //   * 0 < n < cap  — normal cascade fully drained, trace at TRACE.
        //   * n == cap     — drained up to the bound but PeekMessageW *might*
        //     still have more pending. Emit a WARN with rate-limiting context
        //     so operators can spot a real saturation issue (e.g. cap too
        //     low for a particular DCC host) without grepping TRACE logs.
        //     The message is intentionally actionable: it names the call site
        //     (`reason`) and the cap value so bumping `STYLE_MUTATION_DRAIN_CAP`
        //     is a one-line change driven by real evidence rather than
        //     guesswork.
        if n == 0 {
            // Nothing to log: the common "no pending work" path stays silent
            // so we don't spam logs in the steady state.
        } else if n == cap {
            tracing::warn!(
                reason = reason,
                filter = ?hwnd_filter,
                dispatched = n,
                cap = cap,
                "drain_thread_messages_for hit cap; queue may still be saturated \
                 (consider raising STYLE_MUTATION_DRAIN_CAP if this fires under load)"
            );
        } else {
            tracing::trace!(
                reason = reason,
                filter = ?hwnd_filter,
                dispatched = n,
                cap = cap,
                "drain_thread_messages_for"
            );
        }
    }
}

// Non-Windows platforms have no callers: every `drain_thread_messages_for`
// call site is gated behind `#[cfg(target_os = "windows")]`. We deliberately
// do NOT expose a stub to keep cross-platform signature drift impossible.

/// Maximum number of pending Win32 messages drained around each big style
/// mutation in [`apply_child_window_style`].
///
/// Empirically large enough for one full cascade of
/// `WM_NCCALCSIZE` / `WM_WINDOWPOSCHANGED` / `WM_PARENTNOTIFY` /
/// `Chrome_WidgetWin_*` notifications produced by `SetWindowLongW` /
/// `SetParent` / `SetWindowPos`, while staying bounded so we cannot spin
/// forever if the host keeps producing messages.
#[cfg(target_os = "windows")]
const STYLE_MUTATION_DRAIN_CAP: u32 = 256;

/// Apply WS_CHILD style to a window and set its parent
///
/// This function:
/// 1. Removes popup/caption/thickframe/border styles
/// 2. Adds WS_CHILD style
/// 3. Removes extended styles that cause white borders
/// 4. Sets the parent window
/// 5. Subclasses the window to intercept WM_NCCALCSIZE (zero NC area)
/// 6. Applies style changes
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
/// * `parent_hwnd` - Handle to the parent window
/// * `options` - Options for style application
///
/// # Returns
/// Result containing old and new styles, or error message
///
/// # Safety
/// This function uses unsafe Windows API calls.
#[cfg(target_os = "windows")]
pub fn apply_child_window_style(
    hwnd: isize,
    parent_hwnd: isize,
    options: ChildWindowStyleOptions,
) -> Result<ChildWindowStyleResult, String> {
    // SAFETY: Both hwnd and parent_hwnd are valid window handles provided by the caller
    // (guaranteed by the `# Safety` contract). All Win32 APIs (GetWindowLongW,
    // SetWindowLongW, SetParent, SetWindowPos, GetParent, PeekMessageW) operate on
    // these valid handles or stack-local buffers.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);
        let parent_hwnd_win = HWND(parent_hwnd as *mut _);

        // Step 0: Drain any messages left over by wry/WebView2 creation.
        //
        // Without this, the upcoming SetWindowLongW/SetParent/SetWindowPos calls
        // would issue synchronous SendMessage cascades on top of a saturated
        // queue, deadlocking the STA when WebView2's child windows perform COM
        // marshaling. See `drain_thread_messages_for` for full rationale.
        //
        // Scope the drain to messages targeted at our own HWND so we don't
        // disturb the host's (Maya/Houdini/Qt) message stream — those hosts
        // may have ordering assumptions on their own WM_PAINT/WM_INPUT/WM_TIMER.
        drain_thread_messages_for(Some(hwnd_win), STYLE_MUTATION_DRAIN_CAP, "pre-style");

        // Step 1: Compute new styles
        let style = GetWindowLongW(hwnd_win, GWL_STYLE);
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        // Remove popup/caption/thickframe/border styles and add WS_CHILD.
        // WS_CHILD windows cannot be moved independently of their parent.
        let new_style = (style
            & !(WS_POPUP.0 as i32)
            & !(WS_CAPTION.0 as i32)
            & !(WS_THICKFRAME.0 as i32)
            & !(WS_BORDER.0 as i32)
            & !(WS_DLGFRAME.0 as i32))
            | (WS_CHILD.0 as i32);

        // Remove ALL extended styles that can cause white borders or visible edges.
        // WS_EX_STATICEDGE, WS_EX_CLIENTEDGE, WS_EX_WINDOWEDGE, WS_EX_DLGMODALFRAME are the
        // main culprits; WS_EX_CONTEXTHELP can add a frame in some themes.
        let new_ex_style = ex_style
            & !(WS_EX_STATICEDGE.0 as i32)
            & !(WS_EX_CLIENTEDGE.0 as i32)
            & !(WS_EX_WINDOWEDGE.0 as i32)
            & !(WS_EX_DLGMODALFRAME.0 as i32)
            & !(WS_EX_CONTEXTHELP.0 as i32);

        // Step 2: Apply style mutations.
        SetWindowLongW(hwnd_win, GWL_STYLE, new_style);
        SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);

        // Step 2.5: Commit style changes to the NC frame.
        //
        // Per MSDN, GWL_STYLE / GWL_EXSTYLE mutations are not visible to the
        // window's non-client area until the next SetWindowPos with
        // SWP_FRAMECHANGED. Without this commit, when the SetParent branch
        // below short-circuits (`needs_set_parent == false`) the styles
        // would only become visible at step 5's SetWindowPos — leaving a
        // brief window where the new styles are stored but the frame is
        // still drawn from the old ones (visible as a flash of the old
        // caption / border on some DPI / theme combinations).
        //
        // The call is intentionally side-effect-free (no move, size, z-order
        // or activation change); it just triggers the WM_NCCALCSIZE /
        // WM_NCPAINT pass that materialises the style mutation.
        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
        // Drain the resulting WM_NCCALCSIZE / WM_WINDOWPOSCHANGED cascade so
        // it does not pile on top of the next SetParent / SetWindowPos call.
        drain_thread_messages_for(
            Some(hwnd_win),
            STYLE_MUTATION_DRAIN_CAP,
            "post-style-commit",
        );

        // Step 3: Conditionally call SetParent.
        //
        // tao's `with_parent_window(parent_hwnd)` already sets the parent at
        // window-creation time; calling SetParent again here triggers a much
        // larger SendMessage storm because the WebView2 `Chrome_WidgetWin_*`
        // child windows have been created in the meantime and the OS has to
        // notify the *whole* subtree (WM_PARENTNOTIFY, DWM updates, etc.).
        //
        // Only call SetParent when the current parent is actually different
        // from the desired one. Use `GetParent(...).ok()` instead of comparing
        // raw HWND pointers — when GetParent fails (top-level window with no
        // parent, or the call itself errored) it returns Err, and treating
        // that as "different parent" is exactly the behavior we want.
        //
        // Diagnostic level for the Err branch is gated on the *original*
        // style (`style`, before our SetWindowLongW above):
        //
        //   * Original style had `WS_CHILD` set → the HWND was already a
        //     child window, which by definition must have a parent.
        //     `GetParent` returning Err here points at a real anomaly
        //     (parent destroyed, HWND torn down mid-call) — `warn!`.
        //   * Original style did NOT have `WS_CHILD` set → caller passed
        //     a legitimate top-level window (e.g. WS_POPUP) that we are
        //     about to re-parent. This is the normal embedding flow,
        //     not a bug — `debug!` so we don't drown out real warnings
        //     in DCC logs.
        //
        // In both cases we still proceed: `SetParent` is the correct
        // recovery action either way.
        let was_child_originally = (style & (WS_CHILD.0 as i32)) != 0;
        let needs_set_parent = match GetParent(hwnd_win).ok() {
            Some(current) => current.0 != parent_hwnd_win.0,
            None => {
                if was_child_originally {
                    tracing::warn!(
                        "[apply_child_window_style] GetParent returned no parent for HWND 0x{:X} \
                         that already had WS_CHILD set; parent may have been destroyed. \
                         Proceeding with SetParent as recovery.",
                        hwnd
                    );
                } else {
                    tracing::debug!(
                        "[apply_child_window_style] HWND 0x{:X} is currently top-level \
                         (no WS_CHILD); will re-parent to 0x{:X}",
                        hwnd,
                        parent_hwnd
                    );
                }
                true
            }
        };
        if needs_set_parent {
            tracing::info!(
                "[apply_child_window_style] SetParent: HWND 0x{:X} -> 0x{:X}",
                hwnd,
                parent_hwnd
            );
            let _ = SetParent(hwnd_win, Some(parent_hwnd_win));
            // Let WM_PARENTNOTIFY / DWM / Chrome_WidgetWin_* updates settle.
            drain_thread_messages_for(Some(hwnd_win), STYLE_MUTATION_DRAIN_CAP, "post-set-parent");
        } else {
            tracing::debug!(
                "[apply_child_window_style] parent already 0x{:X}, skip SetParent",
                parent_hwnd
            );
        }

        // Step 4: Subclass the window to intercept WM_NCCALCSIZE and force NC area to zero.
        // This is the only reliable way to eliminate the NC region — simply removing
        // style bits and calling SetWindowPos/SWP_FRAMECHANGED is insufficient because
        // tao's WndProc may still return a non-zero NC calculation.
        subclass_for_zero_nc_area(hwnd);

        // Step 5: Apply style changes with SWP_FRAMECHANGED so the subclass takes effect.
        if options.force_position {
            // For DCC/Qt embedding: force position to (0, 0) within parent
            let _ = SetWindowPos(
                hwnd_win,
                None,
                0,
                0,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );
        } else {
            let _ = SetWindowPos(
                hwnd_win,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );
        }

        // Drain again so SetWindowPos's WM_WINDOWPOSCHANGED / WM_NCCALCSIZE /
        // WM_SIZE cascade is delivered before the caller proceeds to the next
        // big Win32 call (e.g. fix_webview2_child_windows). Scoped to our HWND
        // so we don't disturb the host's message stream.
        drain_thread_messages_for(
            Some(hwnd_win),
            STYLE_MUTATION_DRAIN_CAP,
            "post-set-window-pos",
        );

        tracing::info!(
            "Applied WS_CHILD style: HWND 0x{:X} -> Parent 0x{:X} (style 0x{:08X} -> 0x{:08X}, ex_style 0x{:08X} -> 0x{:08X})",
            hwnd,
            parent_hwnd,
            style,
            new_style,
            ex_style,
            new_ex_style
        );

        Ok(ChildWindowStyleResult {
            old_style: style,
            new_style,
            old_ex_style: ex_style,
            new_ex_style,
        })
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn apply_child_window_style(
    _hwnd: isize,
    _parent_hwnd: isize,
    _options: ChildWindowStyleOptions,
) -> Result<ChildWindowStyleResult, String> {
    Err("apply_child_window_style is only supported on Windows".to_string())
}

/// Result of applying owner window style
#[derive(Debug)]
pub struct OwnerWindowStyleResult {
    /// Original extended style
    pub old_ex_style: i32,
    /// New extended style
    pub new_ex_style: i32,
    /// Whether tool window style was applied
    pub tool_window: bool,
}

/// Apply owner relationship to a window.
///
/// This function sets up an owner-owned relationship between windows:
/// - The owned window stays above the owner in Z-order
/// - The owned window is hidden when the owner is minimized
/// - The owned window is destroyed when the owner is destroyed
/// - The owned window can be positioned freely on screen
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
/// * `owner_hwnd` - Handle to the owner window
/// * `tool_window` - If true, applies WS_EX_TOOLWINDOW style (hides from taskbar/Alt+Tab)
///
/// # Official Documentation
/// - [Owned Windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#owned-windows)
/// - [SetWindowLongPtrW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw)
/// - [WS_EX_TOOLWINDOW](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)
///
/// # Safety
/// This function uses unsafe Windows API calls.
#[cfg(target_os = "windows")]
pub fn apply_owner_window_style(
    hwnd: isize,
    owner_hwnd: u64,
    tool_window: bool,
) -> OwnerWindowStyleResult {
    // SAFETY: hwnd is a valid window handle and owner_hwnd is a valid owner handle,
    // both provided by the caller (guaranteed by the `# Safety` contract).
    // Win32 APIs (GetWindowLongW, SetWindowLongW, SetWindowLongPtrW, SetWindowPos)
    // operate on these valid handles.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // Get current extended style
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        // Apply WS_EX_TOOLWINDOW if requested.
        // This hides the window from taskbar and Alt+Tab.
        // Also clear WS_EX_APPWINDOW to avoid forcing taskbar presence.
        const WS_EX_APPWINDOW_BITS: i32 = 0x00040000;
        let new_ex_style = if tool_window {
            (ex_style | (WS_EX_TOOLWINDOW.0 as i32)) & !WS_EX_APPWINDOW_BITS
        } else {
            ex_style
        };

        if new_ex_style != ex_style {
            SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);
        }

        // Set owner relationship using GWLP_HWNDPARENT
        // This is different from SetParent - it sets owner, not parent
        // For popup windows, this establishes owner relationship
        SetWindowLongPtrW(hwnd_win, GWLP_HWNDPARENT, owner_hwnd as isize);

        // Apply style changes
        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );

        tracing::info!(
            "Applied owner relationship: HWND 0x{:X} -> Owner 0x{:X} (tool_window: {}, ex_style 0x{:08X} -> 0x{:08X})",
            hwnd,
            owner_hwnd,
            tool_window,
            ex_style,
            new_ex_style
        );

        OwnerWindowStyleResult {
            old_ex_style: ex_style,
            new_ex_style,
            tool_window,
        }
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn apply_owner_window_style(
    _hwnd: isize,
    _owner_hwnd: u64,
    _tool_window: bool,
) -> OwnerWindowStyleResult {
    OwnerWindowStyleResult {
        old_ex_style: 0,
        new_ex_style: 0,
        tool_window: false,
    }
}

/// Apply WS_EX_TOOLWINDOW style to a window.
///
/// This hides the window from the taskbar and Alt+Tab window switcher.
///
/// Note: WS_EX_APPWINDOW can force a top-level window to appear in the taskbar.
/// For floating tool windows we clear WS_EX_APPWINDOW to ensure it stays hidden.
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
///
/// # Official Documentation
/// - [WS_EX_TOOLWINDOW](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)
#[cfg(target_os = "windows")]
pub fn apply_tool_window_style(hwnd: isize) {
    // SAFETY: hwnd is a valid window handle. GetWindowLongW, SetWindowLongW,
    // and SetWindowPos are called with this valid HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // Get current extended style
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        // WinUser.h constant (stable): WS_EX_APPWINDOW
        const WS_EX_APPWINDOW_BITS: i32 = 0x00040000;

        // Add WS_EX_TOOLWINDOW and clear WS_EX_APPWINDOW
        let new_ex_style = (ex_style | (WS_EX_TOOLWINDOW.0 as i32)) & !WS_EX_APPWINDOW_BITS;

        SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);

        // Apply style changes
        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );

        tracing::info!(
            "Applied tool window style: HWND 0x{:X} (ex_style 0x{:08X} -> 0x{:08X})",
            hwnd,
            ex_style,
            new_ex_style
        );
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn apply_tool_window_style(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Result of applying frameless (no-titlebar) window style.
#[derive(Debug)]
pub struct FramelessWindowStyleResult {
    /// Original window style
    pub old_style: i32,
    /// New window style
    pub new_style: i32,
    /// Original extended style
    pub old_ex_style: i32,
    /// New extended style
    pub new_ex_style: i32,
}

/// Compute the new style/ex_style values for a frameless window.
///
/// This is a pure helper that does not call Win32 APIs.
///
/// On Windows 11 with certain `tao`/`wry` combinations, `with_decorations(false)` may not
/// fully remove `WS_CAPTION`/`WS_THICKFRAME`. This helper defines the canonical bit-masks
/// we want to remove when making a window truly frameless.
pub fn compute_frameless_window_styles(style: i32, ex_style: i32) -> (i32, i32) {
    // WinUser.h constants (stable): keep them local to avoid OS-gated imports.
    const WS_CAPTION_BITS: i32 = 0x00C00000;
    const WS_THICKFRAME_BITS: i32 = 0x00040000;
    const WS_BORDER_BITS: i32 = 0x00800000;
    const WS_DLGFRAME_BITS: i32 = 0x00400000;

    // Also remove system menu / min-max boxes.
    // Keeping these bits on Windows 11 can result in a "ghost" caption area even when
    // WS_CAPTION is cleared (depending on DWM / window type).
    const WS_SYSMENU_BITS: i32 = 0x00080000;
    const WS_MINIMIZEBOX_BITS: i32 = 0x00020000;
    const WS_MAXIMIZEBOX_BITS: i32 = 0x00010000;

    const WS_EX_DLGMODALFRAME_BITS: i32 = 0x00000001;
    const WS_EX_WINDOWEDGE_BITS: i32 = 0x00000100;
    const WS_EX_CLIENTEDGE_BITS: i32 = 0x00000200;
    const WS_EX_STATICEDGE_BITS: i32 = 0x00020000;
    const WS_EX_CONTEXTHELP_BITS: i32 = 0x00000400;

    let new_style = style
        & !WS_CAPTION_BITS
        & !WS_THICKFRAME_BITS
        & !WS_BORDER_BITS
        & !WS_DLGFRAME_BITS
        & !WS_SYSMENU_BITS
        & !WS_MINIMIZEBOX_BITS
        & !WS_MAXIMIZEBOX_BITS;

    let new_ex_style = ex_style
        & !WS_EX_DLGMODALFRAME_BITS
        & !WS_EX_WINDOWEDGE_BITS
        & !WS_EX_CLIENTEDGE_BITS
        & !WS_EX_STATICEDGE_BITS
        & !WS_EX_CONTEXTHELP_BITS;

    (new_style, new_ex_style)
}

/// Force-remove title bar and borders from an existing top-level window.
///
/// This is a Win32 fallback for cases where `tao::WindowBuilder::with_decorations(false)`
/// does not fully take effect on Windows 11.
///
/// Call this after the window is created (and preferably after WebView2 init if you are
/// also applying tool-window/owner styles that might affect WebView2 creation).
#[cfg(target_os = "windows")]
pub fn apply_frameless_window_style(hwnd: isize) -> Result<FramelessWindowStyleResult, String> {
    // SAFETY: hwnd is a valid window handle. GetWindowLongW, SetWindowLongW,
    // and SetWindowPos are called with this valid HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        let style = GetWindowLongW(hwnd_win, GWL_STYLE);
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        let (new_style, new_ex_style) = compute_frameless_window_styles(style, ex_style);

        if new_style != style {
            SetWindowLongW(hwnd_win, GWL_STYLE, new_style);
        }
        if new_ex_style != ex_style {
            SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);
        }

        // Apply style changes
        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );

        tracing::info!(
            "Applied frameless window style: HWND 0x{:X} (style 0x{:08X} -> 0x{:08X}, ex_style 0x{:08X} -> 0x{:08X})",
            hwnd,
            style,
            new_style,
            ex_style,
            new_ex_style
        );

        Ok(FramelessWindowStyleResult {
            old_style: style,
            new_style,
            old_ex_style: ex_style,
            new_ex_style,
        })
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn apply_frameless_window_style(_hwnd: isize) -> Result<FramelessWindowStyleResult, String> {
    Err("apply_frameless_window_style is only supported on Windows".to_string())
}

/// Compute the new style/ex_style values for a borderless popup window.
///
/// This builds on `compute_frameless_window_styles` and additionally forces `WS_POPUP`.
/// This is the most reliable way to get rid of the Win11 title bar / caption buttons.
pub fn compute_frameless_popup_window_styles(style: i32, ex_style: i32) -> (i32, i32) {
    // WinUser.h constants
    const WS_POPUP_BITS: i32 = 0x80000000u32 as i32;
    const WS_CHILD_BITS: i32 = 0x40000000;

    let (base_style, base_ex_style) = compute_frameless_window_styles(style, ex_style);

    // Ensure we are a top-level popup window (not a child window)
    let new_style = (base_style & !WS_CHILD_BITS) | WS_POPUP_BITS;

    (new_style, base_ex_style)
}

/// Force-remove title bar and borders from an existing top-level window by switching to `WS_POPUP`.
///
/// This is a stronger Win32 fallback than `apply_frameless_window_style` and is intended for
/// transparent/frameless tool windows on Windows 11 where DWM may still draw a caption area.
#[cfg(target_os = "windows")]
pub fn apply_frameless_popup_window_style(
    hwnd: isize,
) -> Result<FramelessWindowStyleResult, String> {
    // SAFETY: hwnd is a valid window handle. GetWindowLongW, SetWindowLongW,
    // and SetWindowPos are called with this valid HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        let style = GetWindowLongW(hwnd_win, GWL_STYLE);
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        let (new_style, new_ex_style) = compute_frameless_popup_window_styles(style, ex_style);

        if new_style != style {
            SetWindowLongW(hwnd_win, GWL_STYLE, new_style);
        }
        if new_ex_style != ex_style {
            SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);
        }

        let _ = SetWindowPos(
            hwnd_win,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );

        tracing::info!(
            "Applied frameless popup window style: HWND 0x{:X} (style 0x{:08X} -> 0x{:08X}, ex_style 0x{:08X} -> 0x{:08X})",
            hwnd,
            style,
            new_style,
            ex_style,
            new_ex_style
        );

        Ok(FramelessWindowStyleResult {
            old_style: style,
            new_style,
            old_ex_style: ex_style,
            new_ex_style,
        })
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn apply_frameless_popup_window_style(
    _hwnd: isize,
) -> Result<FramelessWindowStyleResult, String> {
    Err("apply_frameless_popup_window_style is only supported on Windows".to_string())
}

/// Disable window shadow and Win11 frame effects for undecorated (frameless) windows.
///
/// This uses DWM (Desktop Window Manager) attributes to suppress non-client rendering.
/// For transparent frameless tool windows on Windows 11, it's common to also see a subtle
/// border/glow/corner rounding. We explicitly clear those where available.
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
///
/// # Official Documentation
/// - [DwmSetWindowAttribute](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmsetwindowattribute)
/// - [DWMWA_NCRENDERING_POLICY](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)
#[cfg(target_os = "windows")]
pub fn disable_window_shadow(hwnd: isize) {
    // SAFETY: hwnd is a valid window handle. DwmSetWindowAttribute is called with
    // this valid HWND and correctly-sized value buffers (u32). The DWMWINDOWATTRIBUTE
    // numeric values (33-37) are stable Win11 constants.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // DWMNCRP_DISABLED = 1 - Disable non-client area rendering (removes shadow)
        let policy: u32 = 1; // DWMNCRP_DISABLED

        let result = DwmSetWindowAttribute(
            hwnd_win,
            DWMWA_NCRENDERING_POLICY,
            &policy as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );

        if result.is_ok() {
            tracing::info!(
                "Disabled window shadow: HWND 0x{:X} (DWMWA_NCRENDERING_POLICY = DWMNCRP_DISABLED)",
                hwnd
            );
        } else {
            tracing::warn!(
                "Failed to disable window shadow: HWND 0x{:X}, HRESULT: {:?}",
                hwnd,
                result
            );
        }

        // Extra Win11 frame effects suppression.
        // We intentionally construct DWMWINDOWATTRIBUTE by numeric value to avoid SDK/feature gating.
        // Values (stable since Win11):
        // - 33: DWMWA_WINDOW_CORNER_PREFERENCE
        // - 34: DWMWA_BORDER_COLOR
        // - 35: DWMWA_CAPTION_COLOR
        // - 36: DWMWA_TEXT_COLOR
        // - 37: DWMWA_VISIBLE_FRAME_BORDER_THICKNESS
        use windows::Win32::Graphics::Dwm::DWMWINDOWATTRIBUTE;

        // DWMWCP_DONOTROUND = 1
        let corner_pref: u32 = 1;
        let _ = DwmSetWindowAttribute(
            hwnd_win,
            DWMWINDOWATTRIBUTE(33),
            &corner_pref as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );

        // DWMWA_COLOR_NONE = 0xFFFFFFFE
        let color_none: u32 = 0xFFFFFFFE;
        let _ = DwmSetWindowAttribute(
            hwnd_win,
            DWMWINDOWATTRIBUTE(34),
            &color_none as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );
        let _ = DwmSetWindowAttribute(
            hwnd_win,
            DWMWINDOWATTRIBUTE(35),
            &color_none as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );
        let _ = DwmSetWindowAttribute(
            hwnd_win,
            DWMWINDOWATTRIBUTE(36),
            &color_none as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );

        let border_thickness: u32 = 0;
        let _ = DwmSetWindowAttribute(
            hwnd_win,
            DWMWINDOWATTRIBUTE(37),
            &border_thickness as *const _ as *const _,
            std::mem::size_of::<u32>() as u32,
        );
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn disable_window_shadow(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Set the window class background brush to dark color to avoid white border/flash.
///
/// Any unpainted area of the window (e.g. before WebView2 draws) will use this color
/// instead of the system default white. Uses the same dark as DARK_BACKGROUND (#020617).
///
/// # Arguments
/// * `hwnd` - Handle to the window (its class will get the new background brush)
#[cfg(target_os = "windows")]
pub fn set_window_class_dark_background(hwnd: isize) {
    use std::sync::OnceLock;
    use windows::Win32::Foundation::COLORREF;
    use windows::Win32::Graphics::Gdi::CreateSolidBrush;
    use windows::Win32::UI::WindowsAndMessaging::{SetClassLongPtrW, GET_CLASS_LONG_INDEX};

    static DARK_BACKGROUND_BRUSH: OnceLock<isize> = OnceLock::new();

    // SAFETY: hwnd is a valid window handle. CreateSolidBrush returns a valid GDI brush
    // handle (stored in OnceLock for reuse). SetClassLongPtrW is called with a valid
    // HWND and the brush handle to set GCLP_HBRBACKGROUND (-10).
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);
        // COLORREF uses 0x00bbggrr layout. #020617 => 0x00170602.
        let brush = *DARK_BACKGROUND_BRUSH
            .get_or_init(|| CreateSolidBrush(COLORREF(0x00170602)).0 as isize);
        // GCLP_HBRBACKGROUND = -10
        let _ = SetClassLongPtrW(hwnd_win, GET_CLASS_LONG_INDEX(-10), brush);
        tracing::debug!(
            "Set window class dark background: HWND 0x{:X} (brush #020617)",
            hwnd
        );
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn set_window_class_dark_background(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Set a transparent (NULL) class background brush on the window.
///
/// Used for transparent windows: a solid brush (even the dark theme one) is
/// opaque and would show through where WebView2 has not yet painted, defeating
/// `transparent=True`. NULL_BRUSH paints nothing, letting the desktop show
/// through. The WebView2 content still composites on top normally.
#[cfg(target_os = "windows")]
pub fn set_window_class_null_background(hwnd: isize) {
    use windows::Win32::Graphics::Gdi::{GetStockObject, NULL_BRUSH};
    use windows::Win32::UI::WindowsAndMessaging::{SetClassLongPtrW, GET_CLASS_LONG_INDEX};

    // SAFETY: hwnd is a valid window handle. GetStockObject(NULL_BRUSH) returns a
    // valid stock GDI brush. SetClassLongPtrW sets GCLP_HBRBACKGROUND (-10).
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);
        let brush = GetStockObject(NULL_BRUSH).0 as isize;
        // GCLP_HBRBACKGROUND = -10
        let _ = SetClassLongPtrW(hwnd_win, GET_CLASS_LONG_INDEX(-10), brush);
        tracing::debug!("Set window class NULL background: HWND 0x{:X}", hwnd);
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
#[allow(dead_code)]
pub fn set_window_class_null_background(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Fix all WebView2 child windows to prevent dragging and remove white borders.
///
/// WebView2 creates multiple child windows (Chrome_WidgetWin_0, Intermediate D3D Window, etc.)
/// that may not inherit proper WS_CHILD styles. This function recursively fixes all child
/// windows to ensure they cannot be dragged independently and do not draw visible edges.
///
/// Additionally, this function subclasses Chrome_WidgetWin_0 and Chrome_WidgetWin_1 windows
/// to intercept WM_NCHITTEST messages and force them to return HTCLIENT, preventing any
/// drag behavior from the WebView2's internal window handling.
///
/// This is shared by both the embedded (Qt/DCC) path and the standalone top-level path:
/// stripping `WS_EX_CLIENTEDGE` / `WS_EX_WINDOWEDGE` / `WS_EX_STATICEDGE` plus a dark class
/// background brush is what removes the one-pixel white border around the WebView2 content.
///
/// # Arguments
/// * `hwnd` - The top-level WebView window handle
/// * `transparent` - When true, child windows get a NULL (transparent) class
///   background instead of the opaque dark brush, so `transparent=True` windows
///   actually show through instead of revealing #020617.
#[cfg(target_os = "windows")]
pub fn fix_webview2_child_windows(hwnd: isize, transparent: bool) {
    // Guard against a NULL top-level handle. `EnumChildWindows(NULL, ...)` does
    // NOT no-op: per MSDN it enumerates every *top-level* window on the desktop,
    // and our callback would then strip styles / subclass / repaint every one of
    // them — a process-wide side effect that also hangs for a long time. A real
    // WebView HWND is never 0, so treat 0 as "nothing to fix" and bail out.
    if hwnd == 0 {
        tracing::warn!("fix_webview2_child_windows called with NULL hwnd; skipping");
        return;
    }

    use parking_lot::Mutex;
    use std::collections::HashMap;
    use std::ffi::c_void;
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
    use windows::Win32::UI::WindowsAndMessaging::{
        CallWindowProcW, DefWindowProcW, EnumChildWindows, GetClassNameW, GetWindowLongPtrW,
        GetWindowLongW, SetWindowLongPtrW, SetWindowLongW, SetWindowPos, GWLP_WNDPROC, GWL_EXSTYLE,
        GWL_STYLE, SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, WNDPROC,
        WS_BORDER, WS_CAPTION, WS_CHILD, WS_DLGFRAME, WS_EX_CLIENTEDGE, WS_EX_CONTEXTHELP,
        WS_EX_DLGMODALFRAME, WS_EX_STATICEDGE, WS_EX_WINDOWEDGE, WS_POPUP, WS_THICKFRAME,
    };

    // WM_NCHITTEST message constant
    const WM_NCHITTEST: u32 = 0x0084;
    // WM_NCDESTROY - last message a window receives; used to self-unsubclass so
    // the per-HWND entry in ORIGINAL_WNDPROCS does not outlive the window and a
    // recycled HWND is not mistaken for an already-subclassed one.
    const WM_NCDESTROY: u32 = 0x0082;
    // HTCLIENT - indicates the client area (no dragging)
    const HTCLIENT: isize = 1;

    // Store original window procedures for subclassed windows
    // Using a static HashMap protected by Mutex for thread safety (parking_lot,
    // to match subclass_for_zero_nc_area in this module; no poisoning to handle).
    static ORIGINAL_WNDPROCS: Mutex<Option<HashMap<isize, isize>>> = Mutex::new(None);

    // Initialize the HashMap if needed
    {
        let mut guard = ORIGINAL_WNDPROCS.lock();
        if guard.is_none() {
            *guard = Some(HashMap::new());
        }
    }

    // Custom window procedure that intercepts WM_NCHITTEST
    unsafe extern "system" fn subclass_wndproc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        // Intercept WM_NCHITTEST to prevent dragging
        if msg == WM_NCHITTEST {
            // Always return HTCLIENT to indicate we're in the client area
            // This prevents any part of the window from being treated as a drag handle
            return LRESULT(HTCLIENT);
        }

        // Get the original window procedure
        let original_wndproc = ORIGINAL_WNDPROCS
            .lock()
            .as_ref()
            .and_then(|map| map.get(&(hwnd.0 as isize)).copied());

        // On WM_NCDESTROY (the final message a window receives) restore the
        // original wndproc and drop our map entry. Without this the entry leaks
        // and, since the OS recycles HWND values, a freshly created window can
        // land on a stale HWND key — hitting the `already_subclassed` short
        // circuit (so it never gets fixed) or routing messages to a dangling
        // CallWindowProcW target. We forward the message first, then clean up.
        if msg == WM_NCDESTROY {
            let result = if let Some(original) = original_wndproc {
                let wndproc: WNDPROC = std::mem::transmute(original);
                let r = CallWindowProcW(wndproc, hwnd, msg, wparam, lparam);
                // Best-effort restore so any later messages on a recycled HWND
                // reach the real default proc rather than ours.
                SetWindowLongPtrW(hwnd, GWLP_WNDPROC, original);
                r
            } else {
                DefWindowProcW(hwnd, msg, wparam, lparam)
            };
            if let Some(map) = ORIGINAL_WNDPROCS.lock().as_mut() {
                map.remove(&(hwnd.0 as isize));
            }
            return result;
        }

        if let Some(original) = original_wndproc {
            // Call the original window procedure for all other messages
            let wndproc: WNDPROC = std::mem::transmute(original);
            CallWindowProcW(wndproc, hwnd, msg, wparam, lparam)
        } else {
            // Fallback to DefWindowProc if original not found
            DefWindowProcW(hwnd, msg, wparam, lparam)
        }
    }

    // Per-call counters, threaded through EnumChildWindows' LPARAM as a stack
    // pointer so concurrent calls (e.g. standalone + embedded windows in the same
    // host process) don't clobber each other's tallies.
    #[derive(Default)]
    struct Counters {
        total: u32,
        fixed: u32,
        subclassed: u32,
        transparent: bool,
    }

    // Callback function for EnumChildWindows
    // Returns TRUE (non-zero) to continue enumeration, FALSE (0) to stop
    unsafe extern "system" fn enum_child_proc(
        child_hwnd: HWND,
        lparam: LPARAM,
    ) -> windows::core::BOOL {
        let counters = &mut *(lparam.0 as *mut Counters);
        counters.total += 1;

        // Get window class name for logging
        let mut class_name_buf = [0u16; 256];
        let class_len = GetClassNameW(child_hwnd, &mut class_name_buf);
        let class_name = if class_len > 0 {
            String::from_utf16_lossy(&class_name_buf[..class_len as usize])
        } else {
            String::from("<unknown>")
        };

        // Get current styles
        let style = GetWindowLongW(child_hwnd, GWL_STYLE);
        let ex_style = GetWindowLongW(child_hwnd, GWL_EXSTYLE);

        // Check if this window has problematic styles
        let has_popup = (style & WS_POPUP.0 as i32) != 0;
        let has_caption = (style & WS_CAPTION.0 as i32) != 0;
        let has_thickframe = (style & WS_THICKFRAME.0 as i32) != 0;
        let is_child = (style & WS_CHILD.0 as i32) != 0;

        tracing::debug!(
            "[fix_webview2_child_windows] Checking child HWND 0x{:X} class='{}' style=0x{:08X} (popup={}, caption={}, thickframe={}, is_child={})",
            child_hwnd.0 as isize,
            class_name,
            style,
            has_popup,
            has_caption,
            has_thickframe,
            is_child
        );

        // Subclass Chrome_WidgetWin_0 and Chrome_WidgetWin_1 to intercept WM_NCHITTEST
        // These are the windows that handle mouse input and may cause dragging
        if class_name == "Chrome_WidgetWin_0" || class_name == "Chrome_WidgetWin_1" {
            let already_subclassed = ORIGINAL_WNDPROCS
                .lock()
                .as_ref()
                .map(|map| map.contains_key(&(child_hwnd.0 as isize)))
                .unwrap_or(false);

            if !already_subclassed {
                // Get the current window procedure
                let original_wndproc = GetWindowLongPtrW(child_hwnd, GWLP_WNDPROC);
                if original_wndproc != 0 {
                    // Store the original window procedure
                    if let Some(map) = ORIGINAL_WNDPROCS.lock().as_mut() {
                        map.insert(child_hwnd.0 as isize, original_wndproc);
                    }

                    // Set our custom window procedure
                    SetWindowLongPtrW(
                        child_hwnd,
                        GWLP_WNDPROC,
                        subclass_wndproc as *const () as usize as isize,
                    );

                    counters.subclassed += 1;

                    tracing::debug!(
                        "[OK] [fix_webview2_child_windows] Subclassed HWND 0x{:X} class='{}' to intercept WM_NCHITTEST",
                        child_hwnd.0 as isize,
                        class_name
                    );
                }
            }
        }

        // Set dark background brush on every child window to prevent white
        // edges from appearing when the window is partially painted. For
        // transparent windows an opaque brush would show through, so use a
        // NULL (transparent) brush instead.
        if counters.transparent {
            set_window_class_null_background(child_hwnd.0 as isize);
        } else {
            set_window_class_dark_background(child_hwnd.0 as isize);
        }

        // Only fix windows that aren't already proper child windows
        if has_popup || has_caption || has_thickframe || !is_child {
            // Remove problematic styles and ensure WS_CHILD
            let new_style = (style
                & !(WS_POPUP.0 as i32)
                & !(WS_CAPTION.0 as i32)
                & !(WS_THICKFRAME.0 as i32)
                & !(WS_BORDER.0 as i32)
                & !(WS_DLGFRAME.0 as i32))
                | (WS_CHILD.0 as i32);

            // Remove extended styles that can cause white borders (match apply_child_window_style)
            let new_ex_style = ex_style
                & !(WS_EX_STATICEDGE.0 as i32)
                & !(WS_EX_CLIENTEDGE.0 as i32)
                & !(WS_EX_WINDOWEDGE.0 as i32)
                & !(WS_EX_DLGMODALFRAME.0 as i32)
                & !(WS_EX_CONTEXTHELP.0 as i32);

            if new_style != style || new_ex_style != ex_style {
                SetWindowLongW(child_hwnd, GWL_STYLE, new_style);
                SetWindowLongW(child_hwnd, GWL_EXSTYLE, new_ex_style);

                // Subclass to intercept WM_NCCALCSIZE and force zero NC area
                subclass_for_zero_nc_area(child_hwnd.0 as isize);

                // Apply changes with SWP_FRAMECHANGED
                let _ = SetWindowPos(
                    child_hwnd,
                    None,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                );

                counters.fixed += 1;

                tracing::debug!(
                    "[OK] [fix_webview2_child_windows] Fixed child HWND 0x{:X} class='{}' (style 0x{:08X} -> 0x{:08X})",
                    child_hwnd.0 as isize,
                    class_name,
                    style,
                    new_style
                );
            }
        }

        // Continue enumeration (TRUE = 1)
        windows::core::BOOL::from(true)
    }

    // SAFETY: hwnd is a valid top-level window handle provided by the caller.
    // EnumChildWindows / the Win32 calls inside enum_child_proc operate on live
    // child HWNDs handed back by the OS or stack-local buffers. `counters` lives
    // on this stack frame for the full (synchronous) duration of EnumChildWindows,
    // so the pointer handed through LPARAM stays valid for every callback.
    let mut counters = Counters {
        transparent,
        ..Counters::default()
    };
    unsafe {
        let hwnd_win = HWND(hwnd as *mut c_void);
        let _ = EnumChildWindows(
            Some(hwnd_win),
            Some(enum_child_proc),
            LPARAM(&mut counters as *mut Counters as isize),
        );
    }
    tracing::info!(
        "[OK] Fixed WebView2 child windows for HWND 0x{:X} (total={}, fixed={}, subclassed={})",
        hwnd,
        counters.total,
        counters.fixed,
        counters.subclassed
    );
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn fix_webview2_child_windows(_hwnd: isize, _transparent: bool) {
    // No-op on non-Windows platforms
}

/// Extend DWM frame into client area for transparent windows.
///
/// This function uses `DwmExtendFrameIntoClientArea` to extend the window frame
/// into the entire client area, which is required for proper transparent window
/// rendering with WebView2.
///
/// **CRITICAL**: This fixes the rendering artifacts (black stripes) that appear
/// when dragging transparent WebView2 windows. Without this, the window may show
/// visual glitches during movement.
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
///
/// # Official Documentation
/// - [DwmExtendFrameIntoClientArea](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmextendframeintoclientarea)
#[cfg(target_os = "windows")]
pub fn extend_frame_into_client_area(hwnd: isize) {
    tracing::info!(
        "[extend_frame_into_client_area] Called with HWND 0x{:X}",
        hwnd
    );
    // SAFETY: hwnd is a valid window handle. DwmExtendFrameIntoClientArea is called
    // with this valid HWND and a stack-allocated MARGINS struct with well-defined values.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // Extend frame into entire client area (-1 means extend to entire window)
        // This is required for proper transparent window rendering
        let margins = MARGINS {
            cxLeftWidth: -1,
            cxRightWidth: -1,
            cyTopHeight: -1,
            cyBottomHeight: -1,
        };

        let result = DwmExtendFrameIntoClientArea(hwnd_win, &margins);

        if result.is_ok() {
            tracing::info!(
                "[OK] Extended DWM frame into client area: HWND 0x{:X} (margins: -1 all sides)",
                hwnd
            );
        } else {
            tracing::warn!(
                "[WARN] Failed to extend DWM frame: HWND 0x{:X}, HRESULT: {:?}",
                hwnd,
                result
            );
        }
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn extend_frame_into_client_area(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Apply WS_EX_LAYERED style for transparent windows.
///
/// **Note**: This function is provided for advanced use cases but is typically
/// NOT needed for WebView2 transparent windows. WebView2 handles transparency
/// internally through its own compositor.
///
/// The WS_EX_LAYERED style enables per-pixel alpha blending for traditional
/// GDI-based windows, but may interfere with WebView2's rendering.
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
///
/// # Official Documentation
/// - [WS_EX_LAYERED](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)
///
///   Optimize transparent window for better resize performance.
///
/// This function applies several optimizations to reduce flickering and
/// improve rendering performance during window resize operations:
///
/// 1. Disables WM_ERASEBKGND handling to prevent background flashing
/// 2. Sets CS_HREDRAW and CS_VREDRAW to force full redraws
/// 3. Enables double buffering via WS_EX_COMPOSITED
///
/// **Note**: Call this AFTER the window and WebView are created.
///
/// # Arguments
/// * `hwnd` - Handle to the window to optimize
///
/// # Official Documentation
/// - [Window Class Styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-class-styles)
/// - [Extended Window Styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)
#[cfg(target_os = "windows")]
pub fn optimize_transparent_window_resize(hwnd: isize) {
    use windows::Win32::UI::WindowsAndMessaging::{
        GetClassLongPtrW, SetClassLongPtrW, CS_HREDRAW, CS_VREDRAW, GCL_STYLE,
    };

    tracing::info!(
        "[optimize_transparent_window_resize] Called with HWND 0x{:X}",
        hwnd
    );

    // SAFETY: hwnd is a valid window handle. GetClassLongPtrW, SetClassLongPtrW,
    // GetWindowLongW, SetWindowLongW, and SetWindowPos are called with this valid HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // Get current class style
        let class_style = GetClassLongPtrW(hwnd_win, GCL_STYLE);

        // Add CS_HREDRAW and CS_VREDRAW for better resize handling
        // These cause the entire window to be redrawn when resized
        let new_class_style =
            class_style as isize | (CS_HREDRAW.0 as isize) | (CS_VREDRAW.0 as isize);

        if new_class_style != class_style as isize {
            SetClassLongPtrW(hwnd_win, GCL_STYLE, new_class_style);
            tracing::debug!(
                "Applied CS_HREDRAW|CS_VREDRAW: HWND 0x{:X} (class_style 0x{:X} -> 0x{:X})",
                hwnd,
                class_style,
                new_class_style
            );
        }

        // Get current extended style
        let ex_style = GetWindowLongW(hwnd_win, GWL_EXSTYLE);

        // Add WS_EX_COMPOSITED for double-buffered rendering
        // This reduces flicker during resize by buffering paints
        const WS_EX_COMPOSITED: i32 = 0x02000000;
        let new_ex_style = ex_style | WS_EX_COMPOSITED;

        if new_ex_style != ex_style {
            SetWindowLongW(hwnd_win, GWL_EXSTYLE, new_ex_style);

            // Apply style changes
            let _ = SetWindowPos(
                hwnd_win,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );

            tracing::info!(
                "Applied WS_EX_COMPOSITED for transparent window: HWND 0x{:X} (ex_style 0x{:08X} -> 0x{:08X})",
                hwnd,
                ex_style,
                new_ex_style
            );
        }
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn optimize_transparent_window_resize(_hwnd: isize) {
    // No-op on non-Windows platforms
}

/// Remove WS_CLIPCHILDREN style from a window for proper transparency.
///
/// **CRITICAL for transparent windows on Windows 11!**
///
/// By default, tao/winit adds the `WS_CLIPCHILDREN` style to windows, which prevents
/// child windows (like WebView2) from rendering transparent content correctly.
/// The parent window clips the child window area, causing the transparency to
/// show through to whatever is behind the window instead of showing the WebView content.
///
/// This function removes the `WS_CLIPCHILDREN` style to fix transparency issues.
///
/// # When to use
/// Call this AFTER the window is created but BEFORE showing it, for any window with:
/// - `transparent=True`
/// - `frame=False` (frameless/undecorated)
///
/// # Arguments
/// * `hwnd` - Handle to the window to modify
///
/// # Official Documentation
/// - [WS_CLIPCHILDREN](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-styles)
/// - [wry issue #1212](https://github.com/tauri-apps/wry/issues/1212)
#[cfg(target_os = "windows")]
pub fn remove_clip_children_style(hwnd: isize) {
    // SAFETY: hwnd is a valid window handle. GetWindowLongW, SetWindowLongW,
    // and SetWindowPos are called with this valid HWND.
    unsafe {
        let hwnd_win = HWND(hwnd as *mut _);

        // Get current window style
        let style = GetWindowLongW(hwnd_win, GWL_STYLE);

        // Check if WS_CLIPCHILDREN is set
        if (style & WS_CLIPCHILDREN.0 as i32) != 0 {
            // Remove WS_CLIPCHILDREN
            let new_style = style & !(WS_CLIPCHILDREN.0 as i32);

            SetWindowLongW(hwnd_win, GWL_STYLE, new_style);

            // Apply style changes
            let _ = SetWindowPos(
                hwnd_win,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );

            tracing::info!(
                "[OK] Removed WS_CLIPCHILDREN for transparent window: HWND 0x{:X} (style 0x{:08X} -> 0x{:08X})",
                hwnd,
                style,
                new_style
            );
        } else {
            tracing::debug!(
                "WS_CLIPCHILDREN not set on HWND 0x{:X}, no change needed",
                hwnd
            );
        }
    }
}

/// Stub for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub fn remove_clip_children_style(_hwnd: isize) {
    // No-op on non-Windows platforms
}

// ============================================================================
// Real-window tests (Windows only)
//
// These tests create genuine *hidden* top-level / child windows with
// `CreateWindowExW` and drive every public Win32 styling entry point against
// them. Unlike the pure-helper tests in `tests/window_style_tests.rs`, this
// module lives inside the crate so it can reach the `windows` dependency and
// the `pub(crate)` `drain_thread_messages_for` helper.
//
// All windows are created with `WS_POPUP` and never `WS_VISIBLE`, so nothing
// is ever shown on screen — this is safe to run on a headless CI window
// station. Each window uses a process-unique class name so the per-class
// background-brush mutation in `set_window_class_dark_background` cannot leak
// across tests.
// ============================================================================
#[cfg(all(test, target_os = "windows"))]
mod windows_real_window_tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::HWND;
    use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
    use windows::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DefWindowProcW, DestroyWindow, PostMessageW, RegisterClassW, SendMessageW,
        UnregisterClassW, GWL_EXSTYLE, GWL_STYLE, HMENU, WINDOW_EX_STYLE, WNDCLASSW, WS_CHILD,
        WS_CLIPCHILDREN, WS_OVERLAPPEDWINDOW, WS_POPUP,
    };

    const WM_NULL: u32 = 0x0000;
    const WM_NCHITTEST: u32 = 0x0084;

    /// Install a process-wide TRACE subscriber once. Without an active
    /// subscriber, `tracing::{info,debug,warn}!` skip evaluating their format
    /// arguments, leaving those lines uncovered. A TRACE-level subscriber forces
    /// every log site reached by these tests to actually format, exercising the
    /// diagnostic branches the production paths emit.
    fn init_tracing() {
        use std::sync::Once;
        static ONCE: Once = Once::new();
        ONCE.call_once(|| {
            let _ = tracing_subscriber::fmt()
                .with_max_level(tracing::Level::TRACE)
                .with_test_writer()
                .try_init();
        });
    }

    // `WNDCLASSW::lpfnWndProc` wants an `extern "system"` fn pointer; the
    // `DefWindowProcW` import is a plain Rust fn item, so wrap it.
    // SAFETY: forwards verbatim to DefWindowProcW, the documented default.
    unsafe extern "system" fn test_wndproc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        DefWindowProcW(hwnd, msg, wparam, lparam)
    }

    fn module_instance() -> windows::Win32::Foundation::HINSTANCE {
        // SAFETY: GetModuleHandleW(None) returns the handle of the current
        // process image, which is always valid for the lifetime of the test.
        unsafe { GetModuleHandleW(PCWSTR::null()).unwrap().into() }
    }

    fn to_wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    /// A registered window class + an owned hidden window. Both are released on
    /// drop so tests leave no global state behind.
    struct TestWindow {
        hwnd: HWND,
        class_wide: Vec<u16>,
    }

    impl TestWindow {
        /// Create a hidden top-level popup window with a unique class.
        fn new_popup() -> Self {
            Self::new_with(None, WS_POPUP.0, "AvTestPopup")
        }

        /// Create a hidden window of a specific class name (used to register the
        /// `Chrome_WidgetWin_0/1` classes the WebView2 fix looks for).
        fn new_named_child(parent: HWND, class_base: &str) -> Self {
            Self::new_with(Some(parent), WS_CHILD.0, class_base)
        }

        fn new_with(parent: Option<HWND>, style_bits: u32, class_base: &str) -> Self {
            init_tracing();
            static COUNTER: AtomicUsize = AtomicUsize::new(0);
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            // Chrome_WidgetWin_* must keep its exact name to hit the subclass
            // branch; everything else gets a unique suffix to avoid class-name
            // collisions across parallel tests.
            let class_name = if class_base.starts_with("Chrome_WidgetWin_") {
                class_base.to_string()
            } else {
                format!("{class_base}_{}_{n}", std::process::id())
            };
            let class_wide = to_wide(&class_name);
            let hinstance = module_instance();

            // SAFETY: WNDCLASSW is fully initialized with a valid wndproc and
            // instance; the class-name pointer stays valid because `class_wide`
            // is owned by the returned struct. RegisterClassW returning 0 just
            // means the class already exists (Chrome_WidgetWin_*), which is fine.
            unsafe {
                let wc = WNDCLASSW {
                    lpfnWndProc: Some(test_wndproc),
                    hInstance: hinstance,
                    lpszClassName: PCWSTR(class_wide.as_ptr()),
                    ..Default::default()
                };
                let _ = RegisterClassW(&wc);

                let hwnd = CreateWindowExW(
                    WINDOW_EX_STYLE(0),
                    PCWSTR(class_wide.as_ptr()),
                    PCWSTR::null(),
                    WINDOW_STYLE_FROM_BITS(style_bits),
                    0,
                    0,
                    120,
                    80,
                    parent,
                    None::<HMENU>,
                    Some(hinstance),
                    None,
                )
                .expect("CreateWindowExW failed");

                TestWindow { hwnd, class_wide }
            }
        }

        fn raw(&self) -> isize {
            self.hwnd.0 as isize
        }
    }

    impl Drop for TestWindow {
        fn drop(&mut self) {
            // SAFETY: hwnd was created by this struct and not yet destroyed.
            unsafe {
                let _ = DestroyWindow(self.hwnd);
                let _ = UnregisterClassW(PCWSTR(self.class_wide.as_ptr()), Some(module_instance()));
            }
        }
    }

    // `WS_OVERLAPPEDWINDOW`/`WS_POPUP` etc. are `WINDOW_STYLE(u32)` newtypes;
    // this builds one from raw bits for `CreateWindowExW`.
    #[allow(non_snake_case)]
    fn WINDOW_STYLE_FROM_BITS(bits: u32) -> windows::Win32::UI::WindowsAndMessaging::WINDOW_STYLE {
        windows::Win32::UI::WindowsAndMessaging::WINDOW_STYLE(bits)
    }

    #[test]
    fn subclass_for_zero_nc_area_real_window_and_idempotent() {
        let w = TestWindow::new_popup();
        // First call installs the subclass (claim -> install -> upgrade ->
        // commit, including a synchronous WM_NCCALCSIZE re-entry).
        subclass_for_zero_nc_area(w.raw());
        // Second call hits the AlreadyHandled short-circuit.
        subclass_for_zero_nc_area(w.raw());

        // Drive messages through our installed nc_subclass_wndproc:
        // SAFETY: w.hwnd is a live window we own.
        unsafe {
            const WM_NCCALCSIZE: u32 = 0x0083;
            // wparam != 0 -> early `return LRESULT(0)` (zero NC area) branch.
            let _ = SendMessageW(w.hwnd, WM_NCCALCSIZE, Some(WPARAM(1)), Some(LPARAM(0)));
            // A non-NCCALCSIZE message -> the forward-to-original branch
            // (CallWindowProcW on the real previous wndproc).
            let _ = SendMessageW(w.hwnd, WM_NULL, Some(WPARAM(0)), Some(LPARAM(0)));
        }
    }

    #[test]
    fn subclass_for_zero_nc_area_invalid_hwnd_is_noop() {
        // GetWindowLongPtrW returns 0 for a bogus handle -> InvalidHwnd path.
        subclass_for_zero_nc_area(0xDEAD_BEEF_isize);
    }

    #[test]
    fn apply_child_window_style_reparents_then_skips() {
        let parent = TestWindow::new_popup();
        let child = TestWindow::new_popup(); // top-level popup, no parent yet

        // First call: child is top-level (was_child_originally=false), GetParent
        // is None -> debug branch, needs_set_parent=true -> SetParent runs.
        let r1 = apply_child_window_style(
            child.raw(),
            parent.raw(),
            ChildWindowStyleOptions::for_dcc_embedding(),
        )
        .expect("apply_child_window_style (dcc) failed");
        assert_eq!(r1.new_style & (WS_CHILD.0 as i32), WS_CHILD.0 as i32);
        assert_eq!(r1.new_style & (WS_POPUP.0 as i32), 0);

        // Second call with the same parent: GetParent == parent -> needs_set_parent
        // false -> the skip-SetParent branch. Also exercises the standalone
        // (force_position=false) SetWindowPos branch.
        let r2 = apply_child_window_style(
            child.raw(),
            parent.raw(),
            ChildWindowStyleOptions::for_standalone(),
        )
        .expect("apply_child_window_style (standalone) failed");
        assert_eq!(r2.new_style & (WS_CHILD.0 as i32), WS_CHILD.0 as i32);
    }

    #[test]
    fn apply_owner_window_style_tool_and_plain() {
        let owner = TestWindow::new_popup();
        let owned_tool = TestWindow::new_popup();
        let owned_plain = TestWindow::new_popup();

        let res_tool = apply_owner_window_style(owned_tool.raw(), owner.raw() as u64, true);
        assert!(res_tool.tool_window);
        assert_ne!(res_tool.new_ex_style, res_tool.old_ex_style);

        // tool_window=false leaves ex_style untouched (new == old).
        let res_plain = apply_owner_window_style(owned_plain.raw(), owner.raw() as u64, false);
        assert!(!res_plain.tool_window);
        assert_eq!(res_plain.new_ex_style, res_plain.old_ex_style);
    }

    #[test]
    fn apply_tool_window_style_real_window() {
        let w = TestWindow::new_popup();
        apply_tool_window_style(w.raw());
    }

    #[test]
    fn apply_frameless_window_style_real_window() {
        let w = TestWindow::new_with(None, WS_OVERLAPPEDWINDOW.0, "AvTestFrameless");
        let res =
            apply_frameless_window_style(w.raw()).expect("apply_frameless_window_style failed");
        // WS_CAPTION (0x00C00000) must be cleared from an overlapped window.
        assert_eq!(res.new_style & 0x00C00000, 0);
    }

    #[test]
    fn apply_frameless_popup_window_style_real_window() {
        let w = TestWindow::new_with(None, WS_OVERLAPPEDWINDOW.0, "AvTestFramelessPopup");
        let res = apply_frameless_popup_window_style(w.raw())
            .expect("apply_frameless_popup_window_style failed");
        // Result must be a WS_POPUP window with no caption.
        assert_ne!(res.new_style & (WS_POPUP.0 as i32), 0);
        assert_eq!(res.new_style & 0x00C00000, 0);
    }

    #[test]
    fn disable_window_shadow_real_window() {
        let w = TestWindow::new_popup();
        disable_window_shadow(w.raw());
    }

    #[test]
    fn set_window_class_dark_background_real_window() {
        let w = TestWindow::new_popup();
        set_window_class_dark_background(w.raw());
        // Idempotent: brush is cached in a OnceLock, second call reuses it.
        set_window_class_dark_background(w.raw());
    }

    #[test]
    fn extend_frame_into_client_area_real_window() {
        let w = TestWindow::new_popup();
        extend_frame_into_client_area(w.raw());
    }

    #[test]
    fn optimize_transparent_window_resize_real_window() {
        let w = TestWindow::new_popup();
        optimize_transparent_window_resize(w.raw());
    }

    #[test]
    fn remove_clip_children_style_present_and_absent() {
        // Window WITH WS_CLIPCHILDREN -> the strip branch runs.
        let with_clip = TestWindow::new_with(None, WS_POPUP.0 | WS_CLIPCHILDREN.0, "AvTestClip");
        remove_clip_children_style(with_clip.raw());
        // SAFETY: valid hwnd; reading style back to confirm the bit is gone.
        let style = unsafe {
            windows::Win32::UI::WindowsAndMessaging::GetWindowLongW(with_clip.hwnd, GWL_STYLE)
        };
        assert_eq!(style & (WS_CLIPCHILDREN.0 as i32), 0);

        // Window WITHOUT WS_CLIPCHILDREN -> the "no change needed" branch.
        let no_clip = TestWindow::new_popup();
        remove_clip_children_style(no_clip.raw());
    }

    #[test]
    fn fix_webview2_child_windows_with_real_children() {
        let parent = TestWindow::new_popup();

        // A Chrome_WidgetWin_0 child -> hits the WM_NCHITTEST subclass branch.
        let _chrome0 = TestWindow::new_named_child(parent.hwnd, "Chrome_WidgetWin_0");
        // A Chrome_WidgetWin_1 child -> second subclass class name.
        let _chrome1 = TestWindow::new_named_child(parent.hwnd, "Chrome_WidgetWin_1");
        // A child with frame-ish styles so the style-stripping branch fires.
        let _styled = TestWindow::new_with(
            Some(parent.hwnd),
            WS_CHILD.0 | 0x00800000, /* WS_BORDER */
            "AvTestStyledChild",
        );

        // Enumerates the children above, subclasses the Chrome ones, strips
        // styles + dark background on each, and tallies counters.
        fix_webview2_child_windows(parent.raw(), false);

        // Drive messages through the Chrome subclass (subclass_wndproc):
        // SAFETY: _chrome0.hwnd is a live, now-subclassed child window.
        unsafe {
            // WM_NCHITTEST -> early `return LRESULT(HTCLIENT)` branch.
            let _ = SendMessageW(
                _chrome0.hwnd,
                WM_NCHITTEST,
                Some(WPARAM(0)),
                Some(LPARAM(0)),
            );
            // A non-NCHITTEST message -> forward-to-original branch.
            let _ = SendMessageW(_chrome0.hwnd, WM_NULL, Some(WPARAM(0)), Some(LPARAM(0)));
        }

        // Idempotent: Chrome children are now already subclassed -> the
        // already_subclassed short-circuit runs.
        fix_webview2_child_windows(parent.raw(), false);
    }

    #[test]
    fn fix_webview2_child_windows_no_children_is_clean() {
        // A real top-level window with zero children: EnumChildWindows finds
        // nothing, counters stay at zero, no panic.
        let parent = TestWindow::new_popup();
        fix_webview2_child_windows(parent.raw(), false);
    }

    // Regression: transparent=True must NOT leave an opaque solid brush on the
    // window class, or the #020617 background shows through and defeats
    // transparency. The transparent path sets the NULL stock brush instead.
    #[test]
    fn set_window_class_null_vs_dark_background() {
        use windows::Win32::Graphics::Gdi::{GetStockObject, NULL_BRUSH};
        use windows::Win32::UI::WindowsAndMessaging::{GetClassLongPtrW, GET_CLASS_LONG_INDEX};

        let w = TestWindow::new_popup();
        let null_brush = unsafe { GetStockObject(NULL_BRUSH).0 as usize };

        // Transparent path -> NULL brush.
        set_window_class_null_background(w.raw());
        let after_null = unsafe { GetClassLongPtrW(w.hwnd, GET_CLASS_LONG_INDEX(-10)) }; // GCLP_HBRBACKGROUND
        assert_eq!(
            after_null, null_brush,
            "transparent windows must use NULL_BRUSH so the background shows through"
        );

        // Opaque path -> a non-NULL solid brush.
        set_window_class_dark_background(w.raw());
        let after_dark = unsafe { GetClassLongPtrW(w.hwnd, GET_CLASS_LONG_INDEX(-10)) };
        assert_ne!(
            after_dark, null_brush,
            "opaque windows still get the dark solid brush"
        );
    }

    #[test]
    fn drain_thread_messages_for_empty_and_with_pending() {
        let w = TestWindow::new_popup();

        // Empty queue (filtered to our hwnd): n == 0 path.
        drain_thread_messages_for(Some(w.hwnd), 16, "test-empty");

        // Post a few messages targeted at our hwnd, then drain: 0 < n < cap path.
        // SAFETY: valid hwnd; WM_NULL carries no payload.
        unsafe {
            for _ in 0..3 {
                let _ = PostMessageW(
                    Some(w.hwnd),
                    WM_NULL,
                    windows::Win32::Foundation::WPARAM(0),
                    windows::Win32::Foundation::LPARAM(0),
                );
            }
        }
        drain_thread_messages_for(Some(w.hwnd), 256, "test-pending");

        // cap == 0 forces the loop to never run -> still n == 0, exercises the
        // bound check itself.
        drain_thread_messages_for(Some(w.hwnd), 0, "test-zero-cap");
    }

    #[test]
    fn child_window_style_options_constructors() {
        assert!(ChildWindowStyleOptions::for_dcc_embedding().force_position);
        assert!(!ChildWindowStyleOptions::for_standalone().force_position);
        assert!(!ChildWindowStyleOptions::default().force_position);
    }

    #[test]
    fn suppress_unused_ex_style_import() {
        // Touch GWL_EXSTYLE so the import is always considered used regardless
        // of which assertions are compiled in.
        let _ = GWL_EXSTYLE;
    }
}
