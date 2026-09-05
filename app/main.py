import logging
import os
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import Base, SessionLocal, engine, get_db
from app.errors import format_pydantic_errors
from app.models import Patient
from app.schemas import CallTranscriptOut, PatientCreate, PatientOut, PatientUpdate
from app.vapi_webhook import router as vapi_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("patient_registration")

app = FastAPI(title="Patient Registration API")
app.include_router(vapi_router)


def envelope(data=None, error=None):
    return {"data": data, "error": error}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=envelope(error=format_pydantic_errors(exc)))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=envelope(error=str(exc.detail)))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=envelope(error="Internal server error"))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    if os.getenv("SEED_DATA", "false").lower() == "true":
        _seed_if_empty()


def _seed_if_empty():
    db: Session = SessionLocal()
    try:
        if db.query(Patient).count() > 0:
            return
        seed_patients = [
            PatientCreate(
                first_name="Jane",
                last_name="Doe",
                date_of_birth=date(1990, 5, 14),
                sex="Female",
                phone_number="5551234567",
                email="jane.doe@example.com",
                address_line_1="123 Main St",
                city="Springfield",
                state="IL",
                zip_code="62704",
                preferred_language="English",
            ),
            PatientCreate(
                first_name="John",
                last_name="Smith",
                date_of_birth=date(1985, 11, 2),
                sex="Male",
                phone_number="5559876543",
                address_line_1="456 Oak Ave",
                city="Austin",
                state="TX",
                zip_code="73301",
            ),
        ]
        for p in seed_patients:
            crud.create_patient(db, p)
        logger.info("Seeded %d demo patient records", len(seed_patients))
    finally:
        db.close()


@app.get("/")
def health():
    return envelope(data={"status": "ok", "service": "patient-registration-api"})


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/dashboard")
def dashboard():
    return FileResponse(os.path.join(_STATIC_DIR, "dashboard.html"))


@app.get("/patients")
def list_patients(
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(db, last_name, date_of_birth, phone_number)
    data = [PatientOut.model_validate(p).model_dump(mode="json") for p in patients]
    return envelope(data=data)


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"))


@app.post("/patients", status_code=201)
def create_patient(patient_in: PatientCreate, db: Session = Depends(get_db)):
    patient = crud.create_patient(db, patient_in)
    payload = PatientOut.model_validate(patient).model_dump(mode="json")
    logger.info("PATIENT_CREATED %s", payload)
    return envelope(data=payload)


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, patient_in: PatientUpdate, db: Session = Depends(get_db)):
    patient = crud.update_patient(db, patient_id, patient_in)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    payload = PatientOut.model_validate(patient).model_dump(mode="json")
    logger.info("PATIENT_UPDATED %s", payload)
    return envelope(data=payload)


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.soft_delete_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    logger.info("PATIENT_DELETED %s", patient_id)
    return envelope(data={"patient_id": patient_id, "deleted_at": patient.deleted_at.isoformat()})


@app.get("/patients/{patient_id}/transcripts")
def list_patient_transcripts(patient_id: str, db: Session = Depends(get_db)):
    """Bonus: call transcripts linked to this patient (see app/vapi_webhook.py)."""
    if crud.get_patient(db, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    rows = crud.list_transcripts_for_patient(db, patient_id)
    data = [CallTranscriptOut.model_validate(r).model_dump(mode="json") for r in rows]
    return envelope(data=data)
