//! Child-mode detection and environment parsing.
//!
//! Mirrors the semantics of `auroraview.child.ChildInfo` on the Python side so
//! a Rust child process and a Python child process read the very same
//! environment contract.

use std::env;
use std::num::TryFromIntError;

use super::protocol::{
    ENV_CHILD_ID, ENV_EXAMPLE_NAME, ENV_PARENT_HWND, ENV_PARENT_ID, ENV_PARENT_PORT,
};

/// Snapshot of the `AURORAVIEW_*` environment a child process was launched with.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ChildInfo {
    /// `true` when `AURORAVIEW_PARENT_ID` is present.
    pub is_child: bool,
    /// `AURORAVIEW_PARENT_ID`
    pub parent_id: Option<String>,
    /// `AURORAVIEW_CHILD_ID`
    pub child_id: Option<String>,
    /// `AURORAVIEW_EXAMPLE_NAME`
    pub example_name: Option<String>,
    /// `AURORAVIEW_PARENT_PORT`, parsed as a TCP port.
    pub parent_port: Option<u16>,
    /// `AURORAVIEW_PARENT_HWND`, parsed as a native window handle.
    /// Use [`Self::parent_handle`] when passing it to the adapter contract.
    pub parent_hwnd: Option<isize>,
}

impl ChildInfo {
    /// Read the child context from the current process environment.
    pub fn from_env() -> Self {
        let parent_id = env::var(ENV_PARENT_ID).ok().filter(|v| !v.is_empty());
        let is_child = parent_id.is_some();

        let parent_port = env::var(ENV_PARENT_PORT)
            .ok()
            .and_then(|value| value.trim().parse::<u16>().ok());

        let parent_hwnd = env::var(ENV_PARENT_HWND)
            .ok()
            .and_then(|value| parse_hwnd(&value));

        Self {
            is_child,
            parent_id,
            child_id: env::var(ENV_CHILD_ID).ok().filter(|v| !v.is_empty()),
            example_name: env::var(ENV_EXAMPLE_NAME).ok().filter(|v| !v.is_empty()),
            parent_port,
            parent_hwnd,
        }
    }

    /// `true` when enough environment is present to open an IPC channel.
    pub fn can_connect(&self) -> bool {
        self.is_child && self.parent_port.is_some()
    }

    /// Convert the parent handle to the adapter contract's canonical `u64`.
    ///
    /// Use this boundary before assigning the handle to
    /// [`crate::contract::SurfaceSpec`] or a host adapter. The legacy native
    /// field stays `isize`; absent handles stay absent and nonnegative values
    /// (including zero) are preserved. This only checks the representation,
    /// not whether the handle names a live window.
    ///
    /// # Errors
    ///
    /// Negative native values cannot be represented by the contract. They are
    /// rejected rather than reinterpreted as large unsigned handles or silently
    /// treated as absent. Callers must surface the error before embedding.
    pub fn parent_handle(&self) -> Result<Option<u64>, TryFromIntError> {
        self.parent_hwnd.map(u64::try_from).transpose()
    }
}

/// `true` when this process was launched as an AuroraView child window.
pub fn is_child_mode() -> bool {
    env::var(ENV_PARENT_ID)
        .map(|value| !value.is_empty())
        .unwrap_or(false)
}

/// Parse a native window handle from decimal or `0x`-prefixed hexadecimal.
///
/// Returns `None` for anything that is not a valid integer literal, so callers
/// can log and continue instead of aborting startup.
/// Values outside the current platform's `isize` range are rejected, never
/// truncated. Signed input is retained for compatibility; use
/// [`ChildInfo::parent_handle`] to reject negative values at the `u64` contract
/// boundary.
pub fn parse_hwnd(raw: &str) -> Option<isize> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return None;
    }

    let (digits, radix) = match trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
    {
        Some(hex) => (hex, 16),
        None => (trimmed, 10),
    };

    isize::from_str_radix(digits, radix).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    /// Environment variables are process-global; serialise tests that touch them.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn with_env<F: FnOnce()>(vars: &[(&str, Option<&str>)], f: F) {
        let _guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let keys: [&str; 5] = [
            ENV_PARENT_ID,
            ENV_PARENT_PORT,
            ENV_CHILD_ID,
            ENV_EXAMPLE_NAME,
            ENV_PARENT_HWND,
        ];
        let saved: Vec<(String, Option<String>)> = keys
            .iter()
            .map(|k| (k.to_string(), env::var(k).ok()))
            .collect();

        for (key, value) in vars {
            match value {
                Some(v) => env::set_var(key, v),
                None => env::remove_var(key),
            }
        }

        f();

        for (key, value) in saved {
            match value {
                Some(v) => env::set_var(key, v),
                None => env::remove_var(key),
            }
        }
    }

    #[test]
    fn standalone_process_is_not_a_child() {
        with_env(
            &[
                (ENV_PARENT_ID, None),
                (ENV_PARENT_PORT, None),
                (ENV_CHILD_ID, None),
                (ENV_EXAMPLE_NAME, None),
                (ENV_PARENT_HWND, None),
            ],
            || {
                let info = ChildInfo::from_env();
                assert!(!info.is_child);
                assert!(!info.can_connect());
                assert!(!is_child_mode());
            },
        );
    }

    #[test]
    fn child_environment_is_parsed() {
        with_env(
            &[
                (ENV_PARENT_ID, Some("gallery")),
                (ENV_PARENT_PORT, Some("9123")),
                (ENV_CHILD_ID, Some("child-1")),
                (ENV_EXAMPLE_NAME, Some("demo")),
                (ENV_PARENT_HWND, Some("0x1A2B")),
            ],
            || {
                let info = ChildInfo::from_env();
                assert!(info.is_child);
                assert_eq!(info.parent_id.as_deref(), Some("gallery"));
                assert_eq!(info.parent_port, Some(9123));
                assert_eq!(info.child_id.as_deref(), Some("child-1"));
                assert_eq!(info.example_name.as_deref(), Some("demo"));
                assert_eq!(info.parent_hwnd, Some(0x1A2B));
                assert!(info.can_connect());
                assert!(is_child_mode());
            },
        );
    }

    #[test]
    fn empty_parent_id_is_standalone() {
        with_env(&[(ENV_PARENT_ID, Some(""))], || {
            assert!(!ChildInfo::from_env().is_child);
        });
    }

    #[test]
    fn invalid_port_disables_connection_but_keeps_child_mode() {
        with_env(
            &[
                (ENV_PARENT_ID, Some("gallery")),
                (ENV_PARENT_PORT, Some("not-a-port")),
            ],
            || {
                let info = ChildInfo::from_env();
                assert!(info.is_child);
                assert_eq!(info.parent_port, None);
                assert!(!info.can_connect());
            },
        );
    }

    #[test]
    fn hwnd_parsing_accepts_decimal_and_hex() {
        assert_eq!(parse_hwnd("12345"), Some(12345));
        assert_eq!(parse_hwnd("0x1A2B"), Some(0x1A2B));
        assert_eq!(parse_hwnd(" 0X10 "), Some(16));
        assert_eq!(parse_hwnd(""), None);
        assert_eq!(parse_hwnd("zzz"), None);
        assert_eq!(parse_hwnd("99999999999999999999"), None);
    }
}
