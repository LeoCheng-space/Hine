"""Consumer-risk tests for the real protocol tool's evidence checks; no servers/mocks."""
import copy
import importlib.util
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

PATH = pathlib.Path(__file__).resolve().parents[1] / "load" / "protocol.py"
spec = importlib.util.spec_from_file_location("hine_protocol_tool", PATH)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)

MID = "22222222-2222-4222-8222-222222222222"
EID = "00000000-0000-4000-8000-000000000007"
C1 = "11111111-1111-4111-8111-111111111111"


def created():
    return {"event": "message.created", "event_id": EID,
            "timestamp": "2026-10-01T08:00:04Z", "conversation_id": "room",
            "sender_id": "alice", "payload": {"message_id": MID,
            "type": "text", "text": "hello", "order_key": "00000000000000000041"}}


def view():
    return {"id": MID, "event_id": EID, "conversation_id": "room",
            "sender_id": "alice", "created_at": "2026-10-01T08:00:04Z",
            "order_key": "00000000000000000041", "type": "text", "text": "hello",
            "receipt": None}


class EvidenceTests(unittest.TestCase):
    def test_receiver_c1_leak_is_not_success(self):
        event = created()
        event["payload"]["client_message_id"] = C1
        with self.assertRaises(qa.ProtocolFailure):
            qa.message_event(event, "bob")

    def test_ack_alone_does_not_count_receiver_success(self):
        evidence = qa.Delivery("room", "alice", "bob", C1, "hello", 1.0)
        evidence.accept_ack({"event": "message.ack", "event_id": EID,
            "timestamp": "2026-10-01T08:00:04Z", "conversation_id": "room",
            "correlation_id": C1, "payload": {"client_message_id": C1,
            "message_id": MID, "status": "persisted"}})
        self.assertFalse(evidence.complete)
        evidence.accept_created(created(), "bob", 1.25)
        self.assertTrue(evidence.complete)
        self.assertEqual(evidence.latency_ms, 250)

    def test_w07_before_ack_is_supported_but_different_m1_fails(self):
        evidence = qa.Delivery("room", "alice", "bob", C1, "hello", 1.0)
        evidence.accept_created(created(), "bob", 1.25)
        event = {"event": "message.ack", "event_id": EID,
            "timestamp": "2026-10-01T08:00:04Z", "conversation_id": "room",
            "correlation_id": C1, "payload": {"client_message_id": C1,
            "message_id": "33333333-3333-4333-8333-333333333333", "status": "persisted"}}
        with self.assertRaises(qa.ProtocolFailure):
            evidence.accept_ack(event)

    def test_a19_content_change_and_duplicate_are_rejected(self):
        expected = {MID: qa.message_event(created(), "bob")}
        qa.check_history([view()], expected, "bob", "room")
        wrong = view()
        wrong["text"] = "changed"
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_history([wrong], expected, "bob", "room")
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_history([view(), view()], expected, "bob", "room")

    def test_a19_uuid_tiebreak_order_is_checked(self):
        first = view()
        second = view()
        second["id"] = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_history([first, second], {}, "bob", "room")

    def test_sync_hidden_page_can_advance_and_replay_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = qa.ProjectionStore(pathlib.Path(directory) / "state.sqlite", "bob")
            store.install_bootstrap([], "saved")
            store.apply_batch({"snapshot_boundary": "end", "events": [],
                               "next_cursor": "hidden", "has_more": True})
            self.assertEqual(store.cursor, "hidden")
            batch = {"snapshot_boundary": "end", "events": [created()],
                     "next_cursor": "end", "has_more": False}
            store.apply_batch(batch, "end")
            store.apply_batch(batch, "end")
            self.assertEqual(len(store.messages), 1)
            reopened = qa.ProjectionStore(pathlib.Path(directory) / "state.sqlite", "bob")
            self.assertEqual(reopened.cursor, "end")
            self.assertEqual(reopened.messages[MID]["text"], "hello")
            store.close()
            reopened.close()

    def test_sync_boundary_change_or_invalid_event_never_saves_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            store = qa.ProjectionStore(pathlib.Path(directory) / "state.sqlite", "bob")
            store.install_bootstrap([], "saved")
            with self.assertRaises(qa.ProtocolFailure):
                store.apply_batch({"snapshot_boundary": "changed", "events": [],
                                   "next_cursor": "unsafe", "has_more": False}, "fixed")
            invalid = created()
            invalid["payload"]["client_message_id"] = C1
            with self.assertRaises(qa.ProtocolFailure):
                store.apply_batch({"snapshot_boundary": "end", "events": [invalid],
                                   "next_cursor": "unsafe", "has_more": False})
            self.assertEqual(store.cursor, "saved")
            self.assertEqual(store.messages, {})
            store.close()

    def test_config_rejects_odd_load_and_secret_url(self):
        with self.assertRaises(qa.InputFailure):
            qa.validate_target("https://example.test/?token=secret", "http")
        with self.assertRaises(qa.InputFailure):
            qa.validate_count("load", 3, 50)

    def test_retry_different_m1_in_history_cannot_hide_behind_original_ack(self):
        event = created()
        event["payload"]["text"] = "hine-qa-generated-intent"
        first = view()
        first["text"] = "hine-qa-generated-intent"
        duplicate = copy.deepcopy(first)
        duplicate["id"] = "33333333-3333-4333-8333-333333333333"
        duplicate["order_key"] = "00000000000000000042"
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_history([duplicate, first], {MID: qa.message_event(event, "bob")},
                             "bob", "room")

    def test_sync_replay_uses_requested_cursor_not_newer_saved_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = qa.ProjectionStore(pathlib.Path(directory) / "state.sqlite", "bob")
            store.install_bootstrap([], "newer")
            store.apply_batch({"snapshot_boundary": "end", "events": [],
                               "next_cursor": "newer", "has_more": True},
                              requested_cursor="older")
            self.assertEqual(store.cursor, "newer")
            store.close()

    def test_public_errors_reject_internal_auth_metadata_without_echoing_value(self):
        for extra in ({"auth_layer": "private-secret"},
                      {"details": {"auth_layer": "private-secret"}}):
            payload = {"code": "UNAUTHENTICATED", "message": "denied", "retryable": False}
            payload.update(extra)
            with self.assertRaisesRegex(qa.ProtocolFailure, "^PUBLIC_INTERNAL_METADATA_LEAK$"):
                qa.remote_error(payload)
        self.assertEqual(qa.remote_error({"code": "UNAUTHENTICATED", "message": "denied",
                                         "retryable": False}), "UNAUTHENTICATED")

    def test_pending_receipt_survives_reopen_and_merges_without_read_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "state.sqlite"
            store = qa.ProjectionStore(path, "bob")
            store.install_bootstrap([], "saved")
            receipt = {"event": "message.status",
                       "event_id": "55555555-5555-4555-8555-555555555555",
                       "timestamp": "2026-10-01T08:00:06Z", "conversation_id": "room",
                       "payload": {"kind": "direct", "message_id": MID, "recipient_id": "bob",
                                   "status": "read", "updated_at": "2026-10-01T08:00:06Z"}}
            store.apply_batch({"snapshot_boundary": "end", "events": [receipt],
                               "next_cursor": "end", "has_more": False})
            store.close()
            reopened = qa.ProjectionStore(path, "bob")
            self.assertEqual(reopened.pending_receipts[MID]["receipt"]["status"], "read")
            reopened.apply_batch({"snapshot_boundary": "end", "events": [receipt],
                                  "next_cursor": "end", "has_more": False})
            historical = view()
            historical["receipt"] = {"kind": "direct", "message_id": MID, "recipient_id": "bob",
                                     "status": "delivered", "updated_at": "2026-10-01T08:00:05Z"}
            reopened.load_messages([historical])
            self.assertEqual(reopened.messages[MID]["receipt"]["status"], "read")
            self.assertEqual(reopened.pending_receipts, {})
            reopened.close()
            final = qa.ProjectionStore(path, "bob")
            self.assertEqual(final.messages[MID]["receipt"]["status"], "read")
            self.assertEqual(final.cursor, "end")
            final.close()

    def test_invalid_pending_receipt_batch_does_not_commit_cursor_or_partial_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            store = qa.ProjectionStore(pathlib.Path(directory) / "state.sqlite", "bob")
            store.install_bootstrap([], "saved")
            event = created()
            event["event"] = "message.status"
            event["payload"] = {"kind": "direct", "message_id": MID, "recipient_id": "bob",
                                "status": "read", "updated_at": "invalid"}
            with self.assertRaises(qa.ProtocolFailure):
                store.apply_batch({"snapshot_boundary": "end", "events": [event],
                                   "next_cursor": "unsafe", "has_more": False})
            self.assertEqual(store.pending_receipts, {})
            self.assertEqual(store.cursor, "saved")
            store.close()

    def test_six_second_completions_cannot_certify_five_second_baseline(self):
        load = qa.LoadEvidence(2, 600, 0)
        for index in range(2):
            for number in range(100):
                load.record(index, index * 2.5 + number * 6)
        self.assertFalse(load.met)
        self.assertEqual(load.report()["missed_slots"], [20, 20])
        self.assertEqual(load.report()["attempts"], [100, 100])
        self.assertAlmostEqual(load.report()["achieved_messages_per_second"][0], 1 / 6)
        with self.assertRaisesRegex(qa.ProtocolFailure, "^LOAD_REQUESTED_CADENCE_NOT_MET$"):
            load.require_met()

    def test_baseline_report_refuses_configured_scale_without_observed_cadence(self):
        args = SimpleNamespace(mode="load", users=50, duration=600, monitor_pid=None)
        exercise = qa.Exercise(args, {"ws_url": "wss://example.test/ws/v1"})
        exercise.load_evidence = qa.LoadEvidence(50, 600, 0)
        for index in range(50):
            exercise.connections.update(index, "wss", True)
            for number in range(100):
                exercise.load_evidence.record(index, (index % 2) * 2.5 + number * 6)
        exercise.connections.begin_window()
        exercise.connections.end_window()
        self.assertTrue(exercise.report("passed")["baseline_requested"])
        self.assertFalse(exercise.report("passed")["baseline_measured"])

    def test_full_cadence_is_measured_and_small_window_is_not_overcounted(self):
        load = qa.LoadEvidence(2, 10, 0)
        for index, times in enumerate(([0, 5], [2.5, 7.5])):
            for started in times:
                load.record(index, started)
        self.assertTrue(load.met)
        self.assertEqual(load.report()["expected_attempts"], [2, 2])
        self.assertEqual(load.report()["missed_slots"], [0, 0])

    def test_connection_metrics_count_only_authenticated_live_transport_kind(self):
        evidence = qa.ConnectionEvidence()
        evidence.update("rejected", "wss", False)
        evidence.update("plain", "ws", True)
        evidence.update("secure", "wss", True)
        evidence.begin_window()
        self.assertEqual(evidence.report()["window_initial"], {"ws": 1, "wss": 1})
        evidence.update("secure", "wss", False)
        evidence.end_window()
        self.assertEqual(evidence.report()["window_minimum"], {"ws": 1, "wss": 0})
        self.assertEqual(evidence.report()["peak"], {"ws": 1, "wss": 1})
        self.assertFalse(evidence.window_met(2, "wss"))

    def test_recovery_timer_excludes_deliberate_cursor_replay(self):
        measurement = qa.RecoveryEvidence(10)
        measurement.recovered(12)
        measurement.replay_started(13)
        measurement.replayed(43)
        self.assertEqual(measurement.report()["protocol_recovery_ms"], 2000)
        self.assertEqual(measurement.report()["saved_cursor_replay_ms"], 30000)

    def test_existing_saved_state_keeps_cursor_and_messages_when_projection_expands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "state.sqlite"
            store = qa.ProjectionStore(path, "bob")
            store.commit({"cursor": "saved", "messages": {MID: view()},
                          "conversations": {}, "events": {EID: created()}})
            store.close()
            reopened = qa.ProjectionStore(path, "bob")
            try:
                reopened.load_messages([view()])
                self.assertEqual(reopened.cursor, "saved")
                new = created()
                new["event_id"] = "77777777-7777-4777-8777-777777777777"
                new["payload"]["message_id"] = "88888888-8888-4888-8888-888888888888"
                new["payload"]["order_key"] = "00000000000000000042"
                reopened.apply_batch({"snapshot_boundary": "end", "events": [new],
                                      "next_cursor": "end", "has_more": False})
                self.assertEqual(set(reopened.messages), {MID, new["payload"]["message_id"]})
                self.assertEqual(reopened.messages[MID]["text"], "hello")
                self.assertEqual(reopened.cursor, "end")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
