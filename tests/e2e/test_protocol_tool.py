"""Consumer-risk tests for the real protocol tool's evidence checks; no servers/mocks."""
import asyncio
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


def acknowledged():
    return {"event": "message.ack", "event_id": EID,
            "timestamp": "2026-10-01T08:00:04Z", "conversation_id": "room",
            "correlation_id": C1, "payload": {"client_message_id": C1,
            "message_id": MID, "status": "persisted"}}


def sender_created():
    event = created()
    event["payload"]["client_message_id"] = C1
    return event


class GroupEvidenceTests(unittest.TestCase):
    def delivery(self):
        return qa.GroupDelivery("room", "alice", {"alice", "bob", "carol"},
                                C1, "hello", 1.0)

    def test_duplicates_cannot_replace_missing_group_receiver(self):
        evidence = self.delivery()
        evidence.accept_ack(acknowledged())
        evidence.accept_created(sender_created(), "alice", 1.1)
        evidence.accept_created(created(), "bob", 1.2)
        evidence.accept_created(created(), "bob", 1.3)
        self.assertFalse(evidence.complete)
        self.assertEqual(evidence.receiver_counts, {"bob": 2})
        evidence.accept_created(created(), "carol", 1.4)
        self.assertTrue(evidence.complete)
        self.assertAlmostEqual(evidence.latencies_ms["bob"], 200)
        self.assertAlmostEqual(evidence.latencies_ms["carol"], 400)
        self.assertAlmostEqual(evidence.fanout_latency_ms, 400)

    def test_all_receivers_and_ack_without_sender_c1_path_is_incomplete(self):
        evidence = self.delivery()
        evidence.accept_ack(acknowledged())
        evidence.accept_created(created(), "bob", 1.2)
        evidence.accept_created(created(), "carol", 1.4)
        self.assertFalse(evidence.complete)
        evidence.accept_created(sender_created(), "alice", 1.5)
        self.assertTrue(evidence.complete)

    def test_group_rejects_wrong_actor_or_unauthorised_receiver(self):
        for viewer, actor in (("outsider", "alice"), ("bob", "carol")):
            evidence = self.delivery()
            event = created()
            event["sender_id"] = actor
            with self.assertRaises(qa.ProtocolFailure):
                evidence.accept_created(event, viewer, 1.2)
            self.assertFalse(evidence.complete)

    def test_group_each_receiver_must_observe_same_stable_event(self):
        for field, value in (("event_id", "33333333-3333-4333-8333-333333333333"),
                             ("timestamp", "2026-10-01T08:00:05Z")):
            evidence = self.delivery()
            evidence.accept_created(created(), "bob", 1.2)
            changed = created()
            changed[field] = value
            with self.assertRaises(qa.ProtocolFailure):
                evidence.accept_created(changed, "carol", 1.3)
            self.assertNotIn("carol", evidence.receiver_counts)

    def test_group_different_m1_order_or_text_cannot_satisfy_fanout(self):
        for field, value in (("message_id", "33333333-3333-4333-8333-333333333333"),
                             ("order_key", "00000000000000000042"), ("text", "changed")):
            evidence = self.delivery()
            evidence.accept_created(created(), "bob", 1.2)
            changed = created()
            changed["payload"][field] = value
            with self.assertRaises(qa.ProtocolFailure):
                evidence.accept_created(changed, "carol", 1.3)

    def test_group_ack_after_fanout_must_match_every_m1(self):
        evidence = self.delivery()
        evidence.accept_created(created(), "bob", 1.2)
        evidence.accept_created(created(), "carol", 1.3)
        event = acknowledged()
        event["payload"]["message_id"] = "33333333-3333-4333-8333-333333333333"
        with self.assertRaises(qa.ProtocolFailure):
            evidence.accept_ack(event)
        self.assertFalse(evidence.complete)

    def test_group_false_ack_and_receiver_c1_are_never_success(self):
        evidence = self.delivery()
        bad = acknowledged()
        bad["payload"]["status"] = "accepted"
        with self.assertRaises(qa.ProtocolFailure):
            evidence.accept_ack(bad)
        with self.assertRaises(qa.ProtocolFailure):
            evidence.accept_created(sender_created(), "bob", 1.2)
        self.assertFalse(evidence.complete)

    def test_group_invalid_or_private_frame_cannot_add_a_receiver_observation(self):
        private = created()
        private["payload"]["subject_id"] = "internal-identity"
        missing = created()
        missing["payload"].pop("order_key")
        malformed = created()
        malformed["payload"] = None
        for event in (private, missing, malformed):
            evidence = self.delivery()
            with self.assertRaises(qa.ProtocolFailure):
                evidence.accept_created(event, "bob", 1.2)
            self.assertEqual(evidence.receiver_counts, {})
            self.assertFalse(evidence.complete)

    def test_group_history_rejects_receipts_missing_own_c1_and_incomplete_history(self):
        evidence = self.delivery()
        evidence.accept_ack(acknowledged())
        evidence.accept_created(sender_created(), "alice", 1.1)
        evidence.accept_created(created(), "bob", 1.2)
        evidence.accept_created(created(), "carol", 1.3)
        own = view()
        own["client_message_id"] = C1
        qa.check_group_history([own], [evidence], "alice", "room")
        qa.check_group_history([view()], [evidence], "carol", "room")
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_group_history([view()], [evidence], "alice", "room")
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_group_history([], [evidence], "carol", "room")
        bad = view()
        bad["receipt"] = {"kind": "direct", "message_id": MID, "recipient_id": "bob",
                          "status": "delivered", "updated_at": "2026-10-01T08:00:05Z"}
        with self.assertRaises(qa.ProtocolFailure):
            qa.check_group_history([bad], [evidence], "carol", "room")

    def test_group_detail_rejects_duplicate_members_wrong_version_and_nonadmin_creator(self):
        members = ["user-" + str(index) for index in range(50)]
        detail = {"id": "room", "type": "group", "title": "QA group", "unread_count": 0,
                  "membership_version": 1, "created_at": "2026-10-01T08:00:04Z",
                  "members": [{"user_id": user, "role": "admin" if index == 0 else "member"}
                              for index, user in enumerate(members)]}
        qa.check_group_detail(detail, "room", members, members[0], 1)
        for mutation in ("duplicate", "version", "role", "type"):
            bad = copy.deepcopy(detail)
            if mutation == "duplicate":
                bad["members"][-1] = bad["members"][0]
            elif mutation == "version":
                bad["membership_version"] = 2
            elif mutation == "role":
                bad["members"][0]["role"] = "member"
            else:
                bad["type"] = "direct"
            with self.assertRaises(qa.ProtocolFailure):
                qa.check_group_detail(bad, "room", members, members[0], 1)

    def test_group_requires_exactly_fifty_configured_users(self):
        qa.validate_count("group-load", 50, 50)
        for count, available in ((2, 50), (48, 50), (52, 52), (50, 49)):
            with self.assertRaises(qa.InputFailure):
                qa.validate_count("group-load", count, available)

    def test_group_cadence_cannot_be_met_by_duplicate_slot_dispatches(self):
        evidence = qa.LoadEvidence(2, 10, 1, offsets=[0, 0.1])
        for index, times in ((0, [1, 1.2]), (1, [1.1, 6.1])):
            for when in times:
                evidence.record(index, when)
        self.assertFalse(evidence.met)
        with self.assertRaises(qa.ProtocolFailure):
            evidence.require_met()

    def test_group_never_reports_direct_baseline_or_incomplete_fanout_as_measured(self):
        args = SimpleNamespace(mode="group-load", users=50, duration=600,
                               monitor_pid=None, timeout=15)
        exercise = qa.Exercise(args, {"ws_url": "wss://example.test/ws/v1"})
        report = exercise.report("passed")
        self.assertFalse(report["baseline_measured"])
        self.assertFalse(report["group_load_measured"])
        self.assertEqual(report["rooms"], 1)
        self.assertEqual(report["group_receivers_per_intent_requested"], 49)
        self.assertNotIn("hello", str(report))

    def test_group_report_counts_distinct_receivers_and_cannot_hide_one_missing_member(self):
        args = SimpleNamespace(mode="group-load", users=50, duration=10,
                               monitor_pid=None, timeout=15)
        exercise = qa.Exercise(args, {"ws_url": "wss://example.test/ws/v1"})
        members = ["alice"] + ["member-" + str(index) for index in range(49)]
        evidence = qa.GroupDelivery("room", "alice", members, C1, "hello", 1)
        evidence.accept_ack(acknowledged())
        evidence.accept_created(sender_created(), "alice", 1.1)
        for member in members[1:-1]:
            evidence.accept_created(created(), member, 1.2)
        evidence.accept_created(created(), members[1], 1.3)
        exercise.deliveries[("room", "alice", "hello")] = evidence
        exercise.attempted = 1
        report = exercise.report("failed")
        self.assertEqual(report["group_receivers_requested"], 49)
        self.assertEqual(report["group_receivers_observed"], 48)
        self.assertEqual(report["group_intent_receiver_counts"][0]["receiver_frame_observations"], 49)
        self.assertFalse(report["group_load_measured"])
        self.assertFalse(report["group_intent_receiver_counts"][0]["all_receivers_and_sender_ack_verified"])
        for private in members + [C1, EID, MID, "hello"]:
            self.assertNotIn(private, str(report))


class GroupDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_deadline_is_from_dispatch_not_after_ack(self):
        evidence = qa.GroupDelivery("room", "alice", {"alice", "bob", "carol"},
                                    C1, "hello", asyncio.get_running_loop().time() - 2)
        evidence.accept_ack(acknowledged())
        with self.assertRaises(TimeoutError):
            await evidence.wait(1)

    async def test_expired_group_intent_cannot_pass_wait_even_if_fanout_arrived(self):
        started = asyncio.get_running_loop().time() - 2
        evidence = qa.GroupDelivery("room", "alice", {"alice", "bob", "carol"},
                                    C1, "hello", started)
        evidence.accept_ack(acknowledged())
        evidence.accept_created(sender_created(), "alice", started + .1)
        evidence.accept_created(created(), "bob", started + .2)
        evidence.accept_created(created(), "carol", started + .3)
        with self.assertRaises(TimeoutError):
            await evidence.wait(1)

    async def test_client_cleanup_reaps_reader_without_waiting_for_remote_close(self):
        client = qa.Client(None, "wss://example.test/ws/v1", {}, 1,
                           lambda *_: None, lambda *_: None)
        client.reader = asyncio.create_task(asyncio.sleep(100))
        client.heartbeat = asyncio.create_task(asyncio.sleep(100))
        await asyncio.wait_for(client.close(), .2)
        self.assertTrue(client.reader.cancelled())
        self.assertTrue(client.heartbeat.cancelled())


if __name__ == "__main__":
    unittest.main()
