//! Source-level queue contract tests; these do not validate a native WebView.
#![cfg(all(target_os = "linux", feature = "experimental-hosted-gtk"))]

use _core::ipc::{MessageQueue, MessageQueueConfig, WebViewMessage};
use rstest::rstest;

#[rstest]
fn hosted_close_bypasses_a_full_queue() {
    let queue = MessageQueue::with_config(MessageQueueConfig {
        capacity: 1,
        ..Default::default()
    });
    queue.begin_hosted().unwrap();
    queue.push(WebViewMessage::EvalJs("1".into()));
    queue.push(WebViewMessage::Close);
    assert_eq!(queue.hosted_state(), 2);
    assert_eq!(queue.len(), 1);
}

#[rstest]
fn hosted_shutdown_is_single_use() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    queue.finish_hosted();
    assert!(queue.begin_hosted().is_err());
    assert_eq!(queue.hosted_state(), 3);
}

#[rstest]
fn hosted_rejects_blocking_queue_admission() {
    let queue = MessageQueue::with_config(MessageQueueConfig {
        block_on_full: true,
        ..Default::default()
    });
    assert!(queue.begin_hosted().is_err());
}

#[rstest]
fn hosted_close_state_can_be_requested_without_native_objects() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    let sender = queue.clone();
    std::thread::spawn(move || sender.push(WebViewMessage::Close))
        .join()
        .unwrap();
    assert_eq!(queue.hosted_state(), 2);
}

#[rstest]
fn async_admission_reports_full_and_closed_queues() {
    let queue = MessageQueue::with_config(MessageQueueConfig {
        capacity: 1,
        ..Default::default()
    });
    queue.begin_hosted().unwrap();
    assert!(queue
        .try_push(WebViewMessage::EvalJs("first".into()))
        .is_ok());
    assert!(queue
        .try_push(WebViewMessage::EvalJs("overflow".into()))
        .is_err());
    queue.push(WebViewMessage::Close);
    assert!(queue
        .try_push(WebViewMessage::EvalJs("after close".into()))
        .is_err());
    queue.finish_hosted();
    assert!(queue.is_empty());
    assert!(queue
        .try_push(WebViewMessage::EvalJs("after shutdown".into()))
        .is_err());
}

#[rstest]
fn retry_api_cannot_bypass_hosted_close() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    queue.push(WebViewMessage::Close);
    assert!(queue
        .push_with_retry(WebViewMessage::EvalJs("late".into()))
        .is_err());
    assert!(queue.is_empty());
}

#[rstest]
fn producers_cannot_enqueue_after_shutdown_returns() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    let producer = queue.clone();
    let worker = std::thread::spawn(move || {
        for _ in 0..1000 {
            let _ = producer.try_push(WebViewMessage::EvalJs("1".into()));
        }
    });
    queue.finish_hosted();
    worker.join().unwrap();
    assert!(queue.is_empty());
}

#[rstest]
fn hosted_initial_document_seals_before_ipc_admission() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(!queue.hosted_ipc_allowed());
    assert!(queue.hosted_navigation_request(true));
    assert!(!queue.hosted_ipc_allowed());
    assert!(queue.hosted_document_started(true));
    assert!(queue.hosted_ipc_allowed());
    assert!(!queue.hosted_navigation_request(true)); // Same-URL reload is not initial.
    assert_eq!(queue.hosted_state(), 2);
    assert!(!queue.hosted_ipc_allowed());
}

#[rstest]
fn hosted_html_commit_does_not_require_a_policy_callback() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_document_started(true));
    assert!(queue.hosted_ipc_allowed());
    assert!(!queue.hosted_navigation_request(false));
    assert!(!queue.hosted_ipc_allowed());
}

#[rstest]
fn hosted_initial_redirect_closes_before_any_host_call() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_navigation_request(true));
    assert!(!queue.hosted_navigation_request(false));
    assert!(!queue.hosted_document_started(true));
    assert!(!queue.hosted_ipc_allowed());
    assert_eq!(queue.hosted_state(), 2);
}

#[rstest]
fn hosted_unexpected_second_commit_fails_closed() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_document_started(true));
    assert!(!queue.hosted_document_started(true));
    assert!(!queue.hosted_ipc_allowed());
    assert_eq!(queue.hosted_state(), 2);
}

#[rstest]
fn hosted_rejects_navigation_without_relabeling_existing_outbound_work() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_document_started(true));
    queue
        .try_push(WebViewMessage::EmitEvent {
            event_name: "__auroraview_call_result".into(),
            data: serde_json::json!({"id": "old"}),
        })
        .unwrap();
    for command in [
        WebViewMessage::LoadUrl("about:blank".into()),
        WebViewMessage::LoadHtml("<p>new</p>".into()),
        WebViewMessage::Reload,
    ] {
        assert!(MessageQueue::is_navigation(&command));
        assert!(queue
            .try_push(command.clone())
            .unwrap_err()
            .contains("single-document"));
        assert!(queue.push_with_retry(command).is_err());
    }
    assert_eq!(queue.len(), 1);
    assert!(queue.hosted_ipc_allowed()); // Rejected API request never changed the document.
    assert!(!queue.hosted_navigation_request(false));
    assert_eq!(queue.hosted_state(), 2); // Priority retirement precedes the next outbound step.
    assert!(queue
        .try_push(WebViewMessage::EvalJs("late result".into()))
        .is_err());
    queue.finish_hosted();
    assert!(queue.is_empty());
    assert!(!queue.hosted_ipc_allowed());
}

#[rstest]
fn hosted_policy_close_bypasses_full_queue() {
    let queue = MessageQueue::with_config(MessageQueueConfig {
        capacity: 1,
        ..Default::default()
    });
    queue.begin_hosted().unwrap();
    assert!(queue.hosted_document_started(true));
    queue
        .try_push(WebViewMessage::EvalJs("old result".into()))
        .unwrap();
    assert!(!queue.hosted_navigation_request(false));
    assert_eq!(queue.hosted_state(), 2);
    assert!(!queue.hosted_ipc_allowed());
    queue.finish_hosted();
    assert!(queue.is_empty());
}

#[rstest]
fn queued_pre_host_navigation_is_recognized_by_owner_firewall() {
    let queue = MessageQueue::new();
    queue
        .try_push(WebViewMessage::LoadHtml("<p>queued before show</p>".into()))
        .unwrap();
    queue.begin_hosted().unwrap();
    assert!(MessageQueue::is_navigation(&queue.pop().unwrap()));
    assert!(!MessageQueue::is_navigation(&WebViewMessage::EvalJs(
        "1".into()
    )));
}

#[rstest]
fn hosted_unexpected_initial_commit_never_opens_ipc() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    assert!(!queue.hosted_document_started(false));
    assert!(!queue.hosted_ipc_allowed());
    assert_eq!(queue.hosted_state(), 2);
}

#[rstest]
fn hosted_document_gate_cannot_reopen_shutdown_admission() {
    let queue = MessageQueue::new();
    queue.begin_hosted().unwrap();
    queue.shutdown();
    assert!(!queue.hosted_navigation_request(true));
    assert!(!queue.hosted_document_started(true));
    assert!(!queue.hosted_ipc_allowed());
}
