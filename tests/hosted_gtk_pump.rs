//! Scheduling policy tests use a fake target, never a native GTK success claim.
#![cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]

use std::cell::Cell;
use std::time::Duration;
use _core::webview::hosted_pump::{run_slice, PumpTarget};
use rstest::rstest;

struct Traffic<'a> {
    clock: &'a Cell<u64>,
    native_cost: u64,
    outbound_cost: u64,
    running: bool,
    close_on_native: bool,
    native: usize,
    outbound: usize,
}

impl PumpTarget for Traffic<'_> {
    fn is_running(&self) -> bool { self.running }
    fn native_step(&mut self) -> bool {
        self.native += 1;
        self.clock.set(self.clock.get() + self.native_cost);
        if self.close_on_native { self.running = false; }
        true
    }
    fn outbound_step(&mut self) -> bool {
        self.outbound += 1;
        self.clock.set(self.clock.get() + self.outbound_cost);
        true
    }
}

#[rstest]
#[case(10, 0)]
#[case(0, 10)]
fn sustained_overruns_service_both_directions_on_every_poll(
    #[case] native_cost: u64, #[case] outbound_cost: u64,
) {
    let clock = Cell::new(0);
    let mut traffic = Traffic { clock: &clock, native_cost, outbound_cost,
        running: true, close_on_native: false, native: 0, outbound: 0 };
    for expected in 1..=1000 {
        clock.set(0);
        let report = run_slice(&mut traffic, || Duration::from_millis(clock.get()),
            Duration::from_millis(2), 64, 64);
        assert_eq!(report.native_iterations, 1);
        assert_eq!(report.messages, 1);
        assert_eq!(traffic.native, expected);
        assert_eq!(traffic.outbound, expected);
    }
}

#[rstest]
fn close_observed_by_native_step_preempts_queued_work() {
    let clock = Cell::new(0);
    let mut traffic = Traffic { clock: &clock, native_cost: 10, outbound_cost: 0,
        running: true, close_on_native: true, native: 0, outbound: 0 };
    let report = run_slice(&mut traffic, || Duration::from_millis(clock.get()),
        Duration::from_millis(2), 64, 64);
    assert_eq!(report.native_iterations, 1);
    assert_eq!(report.messages, 0);
}

#[rstest]
fn count_limits_hold_even_when_no_time_elapses() {
    let clock = Cell::new(0);
    let mut traffic = Traffic { clock: &clock, native_cost: 0, outbound_cost: 0,
        running: true, close_on_native: false, native: 0, outbound: 0 };
    let report = run_slice(&mut traffic, || Duration::ZERO,
        Duration::from_millis(2), 3, 5);
    assert_eq!(report.native_iterations, 3);
    assert_eq!(report.messages, 5);
}

#[rstest]
fn navigation_close_retires_the_old_queue_before_an_outbound_opportunity() {
    use _core::ipc::{MessageQueue, WebViewMessage};
    struct Navigation {
        queue: MessageQueue,
        owner: std::thread::ThreadId,
        delivered: usize,
    }
    impl PumpTarget for Navigation {
        fn is_running(&self) -> bool { self.queue.hosted_state() == 1 }
        fn native_step(&mut self) -> bool {
            assert_eq!(self.owner, std::thread::current().id());
            assert!(!self.queue.hosted_navigation_request(false));
            // Model NativePump's close_requested() after GTK returns. The real
            // native objects cannot be created in this source policy test.
            self.queue.finish_hosted();
            true
        }
        fn outbound_step(&mut self) -> bool {
            assert_eq!(self.owner, std::thread::current().id());
            self.delivered += usize::from(self.queue.pop().is_some());
            true
        }
    }
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_document_started(true));
    queue.try_push(WebViewMessage::EmitEvent {
        event_name: "__auroraview_call_result".into(), data: serde_json::json!({"id": "old"}),
    }).unwrap();
    let mut target = Navigation { queue, owner: std::thread::current().id(), delivered: 0 };
    let report = run_slice(&mut target, || Duration::ZERO, Duration::from_millis(2), 64, 64);
    assert_eq!(report.messages, 0);
    assert_eq!(target.delivered, 0);
    assert!(target.queue.is_empty());
    assert!(!target.queue.hosted_ipc_allowed());
}
