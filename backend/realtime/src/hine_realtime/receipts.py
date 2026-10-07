"""W08/W09 receipts: BB commits and determines state; Redis only fans out."""
import logging

from . import protocol as p
from .internal import Fault

LOG = logging.getLogger("hine_realtime")


def committed_result(value, message_id, kind):
    p.obj(value)
    for field in ["message_id", "status", "changed", "updated_at", "status_event_id",
                  "invalidation_position", "observer_ids", "membership_version"]:
        p.check(field in value)
    p.uuid(value["message_id"])
    p.check(value["message_id"] == message_id)
    p.check(value["status"] in {"delivered", "read"})
    p.check(kind != "read" or value["status"] == "read")
    p.boolean(value["changed"])
    p.timestamp(value["updated_at"])
    p.integer(value["invalidation_position"])
    if value["status_event_id"] is not None:
        p.uuid(value["status_event_id"])
    if value["membership_version"] is not None:
        p.integer(value["membership_version"], 1)
        # Group individual receipts exist, but group status projections do not.
        p.check(value["status_event_id"] is None)
    observers = value["observer_ids"]
    p.check(isinstance(observers, list))
    for observer in observers:
        p.string(observer, True)
    p.check(len(set(observers)) == len(observers))
    p.check(value["status_event_id"] is not None or not observers)
    return value


async def handle(runtime, connection, frame):
    p.keys(frame, ["event", "event_id", "timestamp", "payload", "conversation_id"])
    p.check(frame["event"] in {"message.received", "message.read"})
    conversation = p.string(frame["conversation_id"])
    payload = p.keys(frame["payload"], ["message_id"])
    message_id = p.uuid(payload["message_id"])
    kind = "delivered" if frame["event"] == "message.received" else "read"
    body = {**connection.session_binding(), "conversation_id": conversation,
            "message_id": message_id, "kind": kind, "request_event_id": frame["event_id"]}
    result = await runtime.client.call("persistReceipt", body, write=True)
    try:
        committed_result(result, message_id, kind)
    except (p.Invalid, TypeError, KeyError):
        raise Fault("OUTCOME_UNCONFIRMED") from None
    position = result["invalidation_position"]
    if not await runtime.invalidations.gate(position):
        raise Fault()
    connection.enqueue(p.event("receipt.ack", {
        "message_id": result["message_id"], "status": result["status"],
        "changed": result["changed"]}, correlation=frame["event_id"],
        conversation=conversation), position=position,
        membership_version=result["membership_version"])
    if result["status_event_id"] is None or not result["observer_ids"]:
        return
    projection = {"kind": "direct", "message_id": result["message_id"],
                  "recipient_id": connection.binding["user_id"],
                  "status": result["status"], "updated_at": result["updated_at"]}
    envelope = p.event("message.status", projection, conversation=conversation,
                       event_id=result["status_event_id"], time=result["updated_at"])
    value = {"notice_id": result["status_event_id"], "type": "conversation_events",
             "committed_at": result["updated_at"], "invalidation_position": position,
             "conversation_events": {
                 "source": "W08" if kind == "delivered" else "W09",
                 "conversation_id": conversation, "membership_version": None,
                 "deliveries": [{"recipient_user_id": observer, "envelope": envelope}
                                for observer in result["observer_ids"]]}}
    try:
        await runtime.publish(p.notice(value))
    except Fault:
        # A confirmed commit remains confirmed when transient fanout fails.
        # BB's durable feed/history, not Redis, recovers the status projection.
        LOG.warning("committed_receipt_fanout_unavailable")
