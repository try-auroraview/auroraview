//! Checked boundary between legacy native parent handles and the adapter contract.

use auroraview_core::contract::{
    EmbedMode, HostAdapter, HostJob, HostResult, SurfaceSpec, ThreadModel, UiFramework,
};
use auroraview_core::parent_ipc::{parse_hwnd, ChildInfo};
use rstest::rstest;

/// An adapter stores the already-checked contract representation.
struct ParentHost(Option<u64>);

impl HostAdapter for ParentHost {
    fn id(&self) -> &'static str {
        "parent"
    }

    fn display_name(&self) -> &'static str {
        "Parent host"
    }

    fn ui_framework(&self) -> UiFramework {
        UiFramework::Win32
    }

    fn thread_model(&self) -> ThreadModel {
        ThreadModel::Any
    }

    fn embed_mode(&self) -> EmbedMode {
        EmbedMode::OutOfProcess
    }

    fn detect(&self) -> bool {
        true
    }

    fn parent_handle(&self) -> Option<u64> {
        self.0
    }

    fn run_deferred(&self, job: HostJob) -> HostResult<()> {
        job();
        Ok(())
    }
}

#[rstest]
#[case(None, None)]
#[case(Some(0), Some(0))]
#[case(Some(1), Some(1))]
#[case(Some(0x1A2B), Some(0x1A2B))]
fn native_parent_handle_enters_the_contract(
    #[case] native: Option<isize>,
    #[case] expected: Option<u64>,
) {
    assert_contract_handle(native, expected);
}

fn assert_contract_handle(native: Option<isize>, expected: Option<u64>) {
    let child = ChildInfo {
        parent_hwnd: native,
        ..ChildInfo::default()
    };
    let adapter = ParentHost(child.parent_handle().expect("nonnegative handle"));
    let host: &dyn HostAdapter = &adapter;
    let surface = SurfaceSpec {
        parent_handle: host.parent_handle(),
        ..SurfaceSpec::default()
    };

    assert_eq!(host.parent_handle(), expected);
    assert_eq!(host.info().parent_handle, expected);
    assert_eq!(surface.parent_handle, expected);
    assert_eq!(child.parent_hwnd, native, "the legacy field is unchanged");
}

#[rstest]
#[case(-1)]
#[case(isize::MIN)]
fn negative_native_handles_are_errors_not_missing(#[case] native: isize) {
    let child = ChildInfo {
        parent_hwnd: Some(native),
        ..ChildInfo::default()
    };

    assert!(child.parent_handle().is_err());
    assert_eq!(parse_hwnd(&native.to_string()), Some(native));
    assert_eq!(child.parent_hwnd, Some(native));
}

#[rstest]
#[case(10)]
#[case(16)]
fn parser_rejects_native_width_overflow(#[case] radix: u32) {
    let maximum = u64::try_from(isize::MAX).expect("positive native limit");
    let overflow = maximum + 1;
    let literal = if radix == 16 {
        format!("0x{overflow:X}")
    } else {
        overflow.to_string()
    };

    assert_eq!(parse_hwnd(&literal), None);
}

#[cfg(target_pointer_width = "64")]
#[rstest]
#[case("4294967296", 0x1_0000_0000)]
#[case("0x123456789ABC", 0x1234_5678_9ABC)]
#[case("9223372036854775807", 0x7FFF_FFFF_FFFF_FFFF)]
#[case("0x7FFFFFFFFFFFFFFF", 0x7FFF_FFFF_FFFF_FFFF)]
fn wide_native_handles_reach_the_surface_without_narrowing(
    #[case] literal: &str,
    #[case] expected: u64,
) {
    let native = parse_hwnd(literal).expect("valid 64-bit native handle");
    assert_contract_handle(Some(native), Some(expected));
}

#[rstest]
#[case(0x8000_0000_0000_0000)]
#[case(u64::MAX)]
fn existing_unsigned_contract_does_not_round_trip_through_isize(#[case] handle: u64) {
    let adapter = ParentHost(Some(handle));
    let host: &dyn HostAdapter = &adapter;
    let info = host.info();
    let surface = SurfaceSpec::default().with_parent_handle(info.parent_handle.unwrap());

    assert_eq!(host.parent_handle(), Some(handle));
    assert_eq!(surface.parent_handle, Some(handle));
    // A native backend must check this separately, never use `as isize`.
    assert!(isize::try_from(handle).is_err());
}
