from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate


def _active(query):
    """Exclude soft-deleted rows from a query."""
    return query.filter(Patient.deleted_at.is_(None))


def list_patients(
    db: Session,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> list[Patient]:
    query = _active(db.query(Patient))
    if last_name:
        query = query.filter(Patient.last_name.ilike(last_name))
    if date_of_birth:
        query = query.filter(Patient.date_of_birth == date_of_birth)
    if phone_number:
        query = query.filter(Patient.phone_number == phone_number)
    return query.order_by(Patient.created_at.desc()).all()


def get_patient(db: Session, patient_id: str) -> Optional[Patient]:
    return _active(db.query(Patient)).filter(Patient.patient_id == patient_id).first()


def get_patient_by_phone(db: Session, phone_number: str) -> Optional[Patient]:
    """Used for the returning-caller / duplicate-detection flow."""
    return _active(db.query(Patient)).filter(Patient.phone_number == phone_number).first()


def create_patient(db: Session, patient_in: PatientCreate) -> Patient:
    patient = Patient(**patient_in.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient_id: str, patient_in: PatientUpdate) -> Optional[Patient]:
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    updates = patient_in.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(patient, field, value)
    patient.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient_id: str) -> Optional[Patient]:
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient
