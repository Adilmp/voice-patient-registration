"""Adapter between Vapi's tool-calling webhook contract and our patient service layer.

Vapi POSTs here whenever the voice assistant decides to call one of its
configured tools (see vapi/tools.json). This module speaks Vapi's request/
response shape on the outside, but underneath it calls the exact same
crud.py functions the REST API uses -- there is only one place that knows
how to read, write, or validate a patient record.
"""

import logging
import re

from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.database import SessionLocal
from app.errors import format_pydantic_errors
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
        return {"success": False, "error": format_pydantic_errors(exc)}

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
        return {"success": False, "error": format_pydantic_errors(exc)}

    patient = crud.update_patient(db, patient_id, patient_in)
    if patient is None:
        return {"success": False, "error": "No patient found with that patient_id"}
    payload = PatientOut.model_validate(patient).model_dump(mode="json")
    logger.info("VAPI_PATIENT_UPDATED %s", payload)
    return {"success": True, "patient": payload}


TOOL_HANDLERS = {
    "lookup_patient_by_phone": _lookup_patient_by_phone,
    "register_patient": _register_patient,
    "update_patient": _update_patient,
}


@router.post("/vapi/tool-calls")
async def handle_tool_calls(request: Request):
    body = await request.json()
    tool_calls = body.get("message", {}).get("toolCallList", [])

    results = []
    db = SessionLocal()
    try:
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
    finally:
        db.close()

    return {"results": results}
