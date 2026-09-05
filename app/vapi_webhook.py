"""Single webhook that speaks Vapi's server-message contract.

Vapi is configured to POST every server message -- both tool-calls and the
end-of-call-report -- to one "Server URL" per assistant. We branch on
message.type here rather than using separate endpoints, matching how Vapi
actually calls out. Underneath, everything goes through the exact same
crud.py functions the REST API uses -- there is only one place that knows
how to read, write, or validate a patient record.
"""

import json
import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.errors import format_pydantic_errors, structured_pydantic_errors
from app.schemas import PatientCreate, PatientOut, PatientUpdate

logger = logging.getLogger("patient_registration")
router = APIRouter()


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _lookup_patient_by_phone(db: Session, args: dict) -> dict:
    phone = _digits_only(args.get("phone_number", ""))
    patient = crud.get_patient_by_phone(db, phone)
    if patient is None:
        return {"found": False}
    return {"found": True, "patient": PatientOut.model_validate(patient).model_dump(mode="json")}


def _register_patient(db: Session, args: dict) -> dict:
    try:
        patient_in = PatientCreate(**args)
    except ValidationError as exc:
        return {
            "success": False,
            "error": format_pydantic_errors(exc),
            "invalid_fields": structured_pydantic_errors(exc),
        }

    existing = crud.get_patient_by_phone(db, patient_in.phone_number)
    if existing is not None:
        return {
            "success": False,
            "error": "duplicate_phone",
            "existing_patient": PatientOut.model_validate(existing).model_dump(mode="json"),
        }

    patient = crud.create_patient(db, patient_in)
    payload = PatientOut.model_validate(patient).model_dump(mode="json")
    logger.info("VAPI_PATIENT_CREATED %s", payload)
    return {"success": True, "patient": payload}


def _update_patient(db: Session, args: dict) -> dict:
    args = dict(args)
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "error": "patient_id is required to update a record"}
    try:
        patient_in = PatientUpdate(**args)
    except ValidationError as exc:
        return {
            "success": False,
            "error": format_pydantic_errors(exc),
            "invalid_fields": structured_pydantic_errors(exc),
        }

    patient = crud.update_patient(db, patient_id, patient_in)
    if patient is None:
        return {"success": False, "error": "No patient found with that patient_id"}
    payload = PatientOut.model_validate(patient).model_dump(mode="json")
    logger.info("VAPI_PATIENT_UPDATED %s", payload)
    return {"success": True, "patient": payload}


def _next_available_slot() -> str:
    """Bonus: mock appointment scheduling -- no real calendar integration.

    Always offers the next weekday at a fixed time. Good enough to
    demonstrate the flow; a real system would query provider availability.
    """
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d += timedelta(days=1)
    return d.strftime("%A, %B %d, %Y") + " at 10:00 AM"


def _schedule_appointment(db: Session, args: dict) -> dict:
    patient_id = args.get("patient_id")
    if not patient_id:
        return {"success": False, "error": "patient_id is required to schedule an appointment"}

    patient = crud.get_patient(db, patient_id)
    if patient is None:
        return {"success": False, "error": "No patient found with that patient_id"}

    appointment = {
        "patient_id": patient_id,
        "date_time": _next_available_slot(),
        "provider": "Dr. Patel",
        "location": "Main Street Clinic",
    }
    logger.info("VAPI_APPOINTMENT_SCHEDULED %s", appointment)
    return {"success": True, "appointment": appointment}


TOOL_HANDLERS = {
    "lookup_patient_by_phone": _lookup_patient_by_phone,
    "register_patient": _register_patient,
    "update_patient": _update_patient,
    "schedule_appointment": _schedule_appointment,
}


def _handle_tool_calls(db: Session, message: dict) -> dict:
    tool_calls = message.get("toolCallList", [])
    results = []
    for call in tool_calls:
        call_id = call.get("id")
        name = call.get("name")
        args = call.get("arguments") or {}

        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            result = {"success": False, "error": f"Unknown tool: {name}"}
        else:
            try:
                result = handler(db, args)
            except Exception:
                logger.exception("Error handling Vapi tool call '%s'", name)
                result = {"success": False, "error": "Internal error while processing this request"}

        results.append({"toolCallId": call_id, "result": result})

    return {"results": results}


def _extract_transcript_fields(message: dict) -> dict:
    """Best-effort extraction -- Vapi's exact payload shape has shifted across
    versions, so every lookup here is defensive and the raw payload is always
    kept as a fallback so a call is never silently lost."""
    call = message.get("call") or {}
    artifact = message.get("artifact") or {}
    customer = call.get("customer") or {}

    phone_raw = customer.get("number") or call.get("phoneNumber") or ""
    phone = re.sub(r"\D", "", phone_raw)[-10:] or None

    transcript = artifact.get("transcript")
    if not transcript and artifact.get("messages"):
        transcript = "\n".join(
            f"{m.get('role', '?')}: {m.get('message', '')}" for m in artifact["messages"]
        )

    return {
        "call_id": call.get("id"),
        "phone_number": phone,
        "transcript": transcript,
        "ended_reason": message.get("endedReason"),
    }


def _handle_end_of_call_report(db: Session, message: dict) -> dict:
    fields = _extract_transcript_fields(message)

    patient_id = None
    if fields["phone_number"]:
        patient = crud.get_patient_by_phone(db, fields["phone_number"])
        if patient:
            patient_id = patient.patient_id

    row = crud.create_call_transcript(
        db,
        patient_id=patient_id,
        raw_payload=json.dumps(message)[:20000],  # cap size defensively
        **fields,
    )
    logger.info(
        "CALL_TRANSCRIPT_SAVED call_id=%s patient_id=%s", row.call_id, row.patient_id
    )
    return {"stored": True, "transcript_id": row.id, "linked_patient_id": patient_id}


@router.post("/vapi/webhook")
async def handle_vapi_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message", {})
    message_type = message.get("type")

    if message_type == "tool-calls":
        return _handle_tool_calls(db, message)
    if message_type == "end-of-call-report":
        return _handle_end_of_call_report(db, message)

    # Vapi sends several other lifecycle message types (status-update,
    # transcript, etc.) that we don't act on -- ack quietly rather than error.
    return {"ignored": message_type}
