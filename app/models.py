import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, String, Text

from app.constants import SEX_VALUES
from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String(36), primary_key=True, default=_uuid)

    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String(20), nullable=False)
    phone_number = Column(String(10), nullable=False, index=True)
    email = Column(String(255), nullable=True)

    address_line_1 = Column(String(255), nullable=False)
    address_line_2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)

    insurance_provider = Column(String(255), nullable=True)
    insurance_member_id = Column(String(64), nullable=True)
    preferred_language = Column(String(50), nullable=False, default="English")
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"sex IN {SEX_VALUES}", name="ck_patients_sex_valid"),
    )


class CallTranscript(Base):
    """A record of one phone call, linked to a patient when we can match one by phone number.

    patient_id is nullable on purpose: a call can end (e.g. caller hangs up
    early) before any patient record exists to link it to.
    """

    __tablename__ = "call_transcripts"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), nullable=True, index=True)
    call_id = Column(String(255), nullable=True)
    phone_number = Column(String(10), nullable=True, index=True)
    transcript = Column(Text, nullable=True)
    ended_reason = Column(String(100), nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
