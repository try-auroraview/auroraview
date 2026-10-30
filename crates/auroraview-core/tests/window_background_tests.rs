//! Verify the actual native background brush, including COLORREF channel order.

#![cfg(target_os = "windows")]

use auroraview_core::builder::set_window_class_dark_background;
use rstest::rstest;
use windows::core::PCWSTR;
use windows::Win32::Foundation::{HINSTANCE, HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::Graphics::Gdi::{GetObjectW, HGDIOBJ, LOGBRUSH};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, GetClassLongPtrW, RegisterClassW,
    UnregisterClassW, GET_CLASS_LONG_INDEX, WINDOW_EX_STYLE, WNDCLASSW, WS_POPUP,
};

struct Window {
    hwnd: HWND,
    instance: HINSTANCE,
    class: Vec<u16>,
}

// SAFETY: forward the original Win32 message parameters to the default handler.
unsafe extern "system" fn wndproc(
    hwnd: HWND,
    message: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    DefWindowProcW(hwnd, message, wparam, lparam)
}

impl Window {
    fn new() -> Self {
        let class: Vec<u16> = format!("AuroraViewBackgroundTest_{}", std::process::id())
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect();
        // SAFETY: the process module is valid, the class name remains owned by
        // this struct, and the hidden popup uses the default window procedure.
        unsafe {
            let instance = GetModuleHandleW(PCWSTR::null()).unwrap().into();
            let descriptor = WNDCLASSW {
                lpfnWndProc: Some(wndproc),
                hInstance: instance,
                lpszClassName: PCWSTR(class.as_ptr()),
                ..Default::default()
            };
            assert_ne!(RegisterClassW(&descriptor), 0);
            let hwnd = CreateWindowExW(
                WINDOW_EX_STYLE(0),
                PCWSTR(class.as_ptr()),
                PCWSTR::null(),
                WS_POPUP,
                0,
                0,
                100,
                100,
                None,
                None,
                Some(instance),
                None,
            )
            .expect("create hidden test window");
            Self {
                hwnd,
                instance,
                class,
            }
        }
    }
}

impl Drop for Window {
    fn drop(&mut self) {
        // SAFETY: this struct owns the window and its process-local class.
        unsafe {
            let _ = DestroyWindow(self.hwnd);
            let _ = UnregisterClassW(PCWSTR(self.class.as_ptr()), Some(self.instance));
        }
    }
}

#[rstest]
fn unpainted_window_uses_dark_theme_background() {
    let window = Window::new();
    set_window_class_dark_background(window.hwnd.0 as isize);

    // SAFETY: the window is alive and its background is a real GDI brush.
    let brush = unsafe { GetClassLongPtrW(window.hwnd, GET_CLASS_LONG_INDEX(-10)) };
    let mut description = LOGBRUSH::default();
    // SAFETY: the writable buffer has the size of the requested LOGBRUSH object.
    let bytes = unsafe {
        GetObjectW(
            HGDIOBJ(brush as *mut _),
            std::mem::size_of::<LOGBRUSH>() as i32,
            Some((&mut description as *mut LOGBRUSH).cast()),
        )
    };
    assert_eq!(bytes as usize, std::mem::size_of::<LOGBRUSH>());
    let color = description.lbColor.0;
    // The shared dark theme is #020617, independent of COLORREF's BGR layout.
    assert_eq!(
        (color & 0xff, (color >> 8) & 0xff, (color >> 16) & 0xff),
        (2, 6, 23),
        "the native backing must use the dark theme, not a red tint"
    );
}
