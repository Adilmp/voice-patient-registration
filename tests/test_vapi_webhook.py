from tests.conftest import VALID_PATIENT


def _tool_call(name, call_id, arguments):
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [{"id": call_id, "name": name, "arguments": arguments}],
        }
    }


def _result_of(resp):
    return resp.json()["results"][0]


def test_lookup_not_found(client):
    resp = client.post(
        "/vapi/webhook",
        json=_tool_call("lookup_patient_by_phone", "c1", {"phone_number": "9999999999"}),
    )
    result = _result_of(resp)
    assert result["toolCallId"] == "c1"
    assert result["result"]["found"] is False


def test_register_then_lookup_found(client):
    reg = client.post(
        "/vapi/webhook",
        json=_tool_call("register_patient", "c2", VALID_PATIENT),
    )
    reg_result = _result_of(reg)["result"]
    assert reg_result["success"] is True
    assert reg_result["patient"]["phone_number"] == "2125550100"

    lookup = client.post(
        "/vapi/webhook",
        json=_tool_call("lookup_patient_by_phone", "c3", {"phone_number": "(212) 555-0100"}),
    )
    lookup_result = _result_of(lookup)["result"]
    assert lookup_result["found"] is True
    assert lookup_result["patient"]["last_name"] == "Nguyen"


def test_register_invalid_dob_returns_field_specific_error(client):
    bad = {**VALID_PATIENT, "date_of_birth": "01/01/2099", "phone_number": "2125550111"}
    resp = client.post("/vapi/webhook", json=_tool_call("register_patient", "c4", bad))
    result = _result_of(resp)["result"]
    assert result["success"] is False
    assert "date_of_birth" in result["error"]


def test_register_duplicate_phone_offers_existing_patient(client):
    client.post("/vapi/webhook", json=_tool_call("register_patient", "c5", VALID_PATIENT))
    dup = client.post("/vapi/webhook", json=_tool_call("register_patient", "c6", VALID_PATIENT))
    result = _result_of(dup)["result"]
    assert result["success"] is False
    assert result["error"] == "duplicate_phone"
    assert result["existing_patient"]["last_name"] == "Nguyen"


def test_update_patient_via_webhook(client):
    reg = client.post("/vapi/webhook", json=_tool_call("register_patient", "c7", VALID_PATIENT))
    patient_id = _result_of(reg)["result"]["patient"]["patient_id"]

    upd = client.post(
        "/vapi/webhook",
        json=_tool_call("update_patient", "c8", {"patient_id": patient_id, "city": "Manhattan"}),
    )
    result = _result_of(upd)["result"]
    assert result["success"] is True
    assert result["patient"]["city"] == "Manhattan"


def test_update_patient_missing_id_returns_error(client):
    resp = client.post(
        "/vapi/webhook",
        json=_tool_call("update_patient", "c9", {"city": "Nowhere"}),
    )
    result = _result_of(resp)["result"]
    assert result["success"] is False
    assert "patient_id" in result["error"]


def test_unknown_tool_name_handled_gracefully(client):
    resp = client.post(
        "/vapi/webhook",
        json=_tool_call("delete_everything", "c10", {}),
    )
    result = _result_of(resp)["result"]
    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_end_of_call_report_links_to_existing_patient(client):
    reg = client.post("/vapi/webhook", json=_tool_call("register_patient", "c11", VALID_PATIENT))
    patient_id = _result_of(reg)["result"]["patient"]["patient_id"]

    report = {
        "message": {
            "type": "end-of-call-report",
            "endedReason": "hangup",
            "call": {"id": "call-abc", "customer": {"number": "+12125550100"}},
            "artifact": {
                "transcript": "AI: Hi, how can I help? User: I'd like to register."
            },
        }
    }
    resp = client.post("/vapi/webhook", json=report)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] is True
    assert body["linked_patient_id"] == patient_id


def test_end_of_call_report_without_matching_patient_still_stored(client):
    report = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call-xyz", "customer": {"number": "+19998887777"}},
            "artifact": {"transcript": "AI: Hello? User: (hangs up)"},
        }
    }
    resp = client.post("/vapi/webhook", json=report)
    body = resp.json()
    assert body["stored"] is True
    assert body["linked_patient_id"] is None


def test_unhandled_message_type_is_ignored_not_errored(client):
    resp = client.post("/vapi/webhook", json={"message": {"type": "status-update"}})
    assert resp.status_code == 200
    assert resp.json() == {"ignored": "status-update"}
