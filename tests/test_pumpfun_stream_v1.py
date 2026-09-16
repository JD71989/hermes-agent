from research.pumpfun_stream import (
    PUMP_PROGRAM_ID,
    decode_log_notification,
    event_record,
    subscription_message,
)


def test_subscription_targets_pump_program():
    message = subscription_message()
    assert message["method"] == "logsSubscribe"
    assert message["params"][0]["mentions"] == [PUMP_PROGRAM_ID]
    assert message["params"][1]["commitment"] == "confirmed"


def test_decode_log_notification():
    payload = {
        "method": "logsNotification",
        "params": {"result": {"context": {"slot": 42}, "value": {
            "signature": "abc", "err": None, "logs": ["Program log: create"]
        }}},
    }
    item = decode_log_notification(payload)
    assert item is not None
    assert item.signature == "abc"
    assert item.slot == 42
    assert item.logs == ("Program log: create",)


def test_decode_ignores_other_messages():
    assert decode_log_notification({"method": "slotNotification"}) is None


def test_event_record_is_json_ready():
    item = decode_log_notification({
        "method": "logsNotification",
        "params": {"result": {"context": {"slot": 7}, "value": {
            "signature": "sig", "err": None, "logs": []
        }}},
    })
    assert event_record(item)["program"] == PUMP_PROGRAM_ID
