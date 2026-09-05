from tests.conftest import VALID_PATIENT


def test_health(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"


def test_create_patient_valid(client):
    resp = client.post("/patients", json=VALID_PATIENT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["first_name"] == "Alice"
    assert body["data"]["phone_number"] == "2125550100"  # normalized, punctuation stripped
    assert body["data"]["state"] == "NY"  # uppercased
    assert body["data"]["date_of_birth"] == "1992-03-15"  # MM/DD/YYYY parsed to ISO
    assert body["data"]["patient_id"]


def test_create_patient_future_dob_rejected(client):
    bad = {**VALID_PATIENT, "date_of_birth": "01/01/2099", "phone_number": "2125550101"}
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422
    assert "date_of_birth" in resp.json()["error"]


def test_create_patient_bad_phone_rejected(client):
    bad = {**VALID_PATIENT, "phone_number": "123", "date_of_birth": "01/01/1990"}
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422
    assert resp.json()["data"] is None


def test_create_patient_invalid_state_rejected(client):
    bad = {**VALID_PATIENT, "state": "ZZ", "phone_number": "2125550102"}
    resp = client.post("/patients", json=bad)
    assert resp.status_code == 422


def test_get_patient_by_id(client):
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.get(f"/patients/{created['patient_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["last_name"] == "Nguyen"


def test_get_nonexistent_patient_404(client):
    resp = client.get("/patients/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["data"] is None
    assert resp.json()["error"] == "Patient not found"


def test_list_patients_filter_by_last_name(client):
    client.post("/patients", json=VALID_PATIENT)
    other = {**VALID_PATIENT, "last_name": "Chen", "phone_number": "2125550199"}
    client.post("/patients", json=other)

    resp = client.get("/patients", params={"last_name": "Nguyen"})
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["last_name"] == "Nguyen"


def test_update_patient_partial(client):
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    pid = created["patient_id"]

    resp = client.put(f"/patients/{pid}", json={"city": "Queens"})
    assert resp.status_code == 200
    updated = resp.json()["data"]
    assert updated["city"] == "Queens"
    assert updated["last_name"] == "Nguyen"  # untouched fields survive
    assert updated["updated_at"] != created["updated_at"]


def test_update_nonexistent_patient_404(client):
    resp = client.put("/patients/does-not-exist", json={"city": "Nowhere"})
    assert resp.status_code == 404


def test_soft_delete_hides_but_does_not_destroy(client):
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    pid = created["patient_id"]

    del_resp = client.delete(f"/patients/{pid}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted_at"] is not None

    # Gone from single-get and from list...
    assert client.get(f"/patients/{pid}").status_code == 404
    listed_ids = [p["patient_id"] for p in client.get("/patients").json()["data"]]
    assert pid not in listed_ids


def test_data_persists_across_requests_same_session(client):
    """Simulates 'call back later and the data is still there' at the API level."""
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    pid = created["patient_id"]

    # Separate, later request against the same backing store
    resp = client.get(f"/patients/{pid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["first_name"] == "Alice"
