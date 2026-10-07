//! Count-bounded hosted scheduling policy, independent of GTK and Python.

use std::time::Duration;

/// Operations remain on the caller's owner thread; implementations retire close
/// intent before further work. Returning false means no work was available.
pub trait PumpTarget {
    fn is_running(&self) -> bool;
    fn native_step(&mut self) -> bool;
    fn outbound_step(&mut self) -> bool;
}

/// Work actually serviced by a single slice.
#[derive(Default)]
pub struct PumpReport {
    pub native_iterations: usize,
    pub messages: usize,
}

/// Reserve one opportunity per direction even when one callback overruns time.
/// Count limits are hard. A callback cannot be preempted, so elapsed time is soft.
pub fn run_slice(
    target: &mut impl PumpTarget,
    mut elapsed: impl FnMut() -> Duration,
    budget: Duration,
    max_native: usize,
    max_messages: usize,
) -> PumpReport {
    let mut report = PumpReport::default();
    let mut first_round = true;
    while target.is_running() && (first_round || elapsed() < budget) {
        let native = report.native_iterations < max_native && target.native_step();
        report.native_iterations += usize::from(native);
        // Always offer outbound service after an overrun, unless native work
        // closed the runtime. The target must retire individual closed views.
        let outbound = target.is_running()
            && report.messages < max_messages && target.outbound_step();
        report.messages += usize::from(outbound);
        first_round = false;
        if !native && !outbound { break; }
    }
    report
}
