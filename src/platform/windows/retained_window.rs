//! Owner-thread close-source adapter for retained standalone windows.

use std::ffi::c_void;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::UI::Shell::{DefSubclassProc, RemoveWindowSubclass, SetWindowSubclass};
use windows::Win32::UI::WindowsAndMessaging::{
    DestroyWindow, IsWindow, ShowWindow, HTCLOSE, SC_CLOSE, SW_HIDE, WM_CANCELMODE,
    WM_CAPTURECHANGED, WM_CLOSE, WM_LBUTTONUP, WM_NCDESTROY, WM_NCLBUTTONDOWN, WM_NCLBUTTONUP,
    WM_SYSCOMMAND,
};

use crate::webview::window_control::RetainedShared;

const SUBCLASS_ID: usize = 0xA0A0_0E01;

struct Source {
    shared: Arc<RetainedShared>,
    armed: AtomicBool,
    removed: AtomicBool,
}

/// Keeps the subclass and its callback data tied to the native HWND lifetime.
pub struct RetainedWindow {
    hwnd: HWND,
    source: Arc<Source>,
}

impl RetainedWindow {
    pub fn install(hwnd_value: u64, shared: Arc<RetainedShared>) -> Result<Self, String> {
        #[cfg(debug_assertions)]
        if shared.fail_adapter_install.swap(false, Ordering::SeqCst) {
            return Err("injected retained adapter installation failure".into());
        }
        let hwnd = HWND(hwnd_value as *mut c_void);
        let source = Arc::new(Source {
            shared,
            armed: AtomicBool::new(false),
            removed: AtomicBool::new(false),
        });
        let ref_data = Arc::into_raw(source.clone()) as usize;
        // SAFETY: installation and removal both run on the HWND owner thread.
        if unsafe { SetWindowSubclass(hwnd, Some(subclass_proc), SUBCLASS_ID, ref_data) }.as_bool()
        {
            Ok(Self { hwnd, source })
        } else {
            // SAFETY: SetWindowSubclass failed, so the raw strong reference was not installed.
            unsafe { drop(Arc::from_raw(ref_data as *const Source)) };
            Err("could not install retained window close adapter".into())
        }
    }

    /// Confirm that the parent HWND is gone before publishing native release.
    pub fn destroy(&self) -> Result<(), String> {
        Self::destroy_hwnd(self.hwnd.0 as u64)
    }

    pub fn is_hwnd_alive(hwnd_value: u64) -> bool {
        // SAFETY: IsWindow validates an opaque OS handle without dereferencing it.
        unsafe { IsWindow(Some(HWND(hwnd_value as *mut c_void))).as_bool() }
    }

    pub fn destroy_hwnd(hwnd_value: u64) -> Result<(), String> {
        let hwnd = HWND(hwnd_value as *mut c_void);
        // SAFETY: the retained owner is the only thread that calls this method.
        unsafe {
            if IsWindow(Some(hwnd)).as_bool() {
                DestroyWindow(hwnd).map_err(|error| error.to_string())?;
            }
            if IsWindow(Some(hwnd)).as_bool() {
                return Err("retained HWND survived native destruction".into());
            }
        }
        Ok(())
    }
}

impl Drop for RetainedWindow {
    fn drop(&mut self) {
        if !self.source.removed.swap(true, Ordering::SeqCst) {
            // SAFETY: the owner drops this adapter before leaving its native scope.
            unsafe {
                let _ = RemoveWindowSubclass(self.hwnd, Some(subclass_proc), SUBCLASS_ID);
                drop(Arc::from_raw(Arc::as_ptr(&self.source)));
            }
        }
    }
}

unsafe extern "system" fn subclass_proc(
    hwnd: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
    _id: usize,
    ref_data: usize,
) -> LRESULT {
    // SAFETY: the installed subclass holds a raw strong Arc reference until removal.
    let source = unsafe { &*(ref_data as *const Source) };
    if message == WM_NCLBUTTONUP {
        source.shared.note_native_event("nc_up");
    }
    if message == WM_LBUTTONUP {
        source.shared.note_native_event("client_up");
    }
    if message == WM_CAPTURECHANGED {
        source.shared.note_native_event("capture_changed");
    }
    if message == WM_CANCELMODE {
        source.shared.note_native_event("cancel_mode");
    }
    if message == WM_NCLBUTTONDOWN && wparam.0 as u32 == HTCLOSE {
        source.shared.note_native_event("x_down");
        source.armed.store(true, Ordering::SeqCst);
        // The default procedure completes the mouse tracking loop synchronously.
        // Only a close command produced inside that loop proves an X activation.
        let result = unsafe { DefSubclassProc(hwnd, message, wparam, lparam) };
        source.armed.store(false, Ordering::SeqCst);
        return result;
    }
    if message == WM_SYSCOMMAND && ((wparam.0 & 0xFFF0) as u32) == SC_CLOSE {
        if source.armed.swap(false, Ordering::SeqCst) {
            source.shared.note_native_event("x_activated");
            source.shared.control.hide();
            // SAFETY: this callback runs on the native window owner thread.
            let _ = unsafe { ShowWindow(hwnd, SW_HIDE) };
            let _ = source.shared.signal();
            return LRESULT(0);
        }
        source.shared.note_native_event("system_close");
        source.shared.control.close();
    }
    if message == WM_CLOSE {
        source.shared.note_native_event("wm_close");
        source.shared.control.close();
    }
    if message == WM_NCDESTROY {
        source.shared.note_native_event("nc_destroy");
        source.shared.control.close();
        if !source.removed.swap(true, Ordering::SeqCst) {
            // SAFETY: remove the installed reference once, after forwarding the final message.
            let result = unsafe { DefSubclassProc(hwnd, message, wparam, lparam) };
            unsafe {
                let _ = RemoveWindowSubclass(hwnd, Some(subclass_proc), SUBCLASS_ID);
                drop(Arc::from_raw(ref_data as *const Source));
            }
            return result;
        }
    }
    unsafe { DefSubclassProc(hwnd, message, wparam, lparam) }
}
