import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.constants import SEX_VALUES, US_STATE_CODES

NAME_RE = re.compile(r"^[A-Za-z'-]{1,50}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9]+$")


def parse_dob(value):
    """Accept both MM/DD/YYYY (how callers speak it) and YYYY-MM-DD (ISO)."""
    if isinstance(value, str):
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise ValueError("date_of_birth must be in MM/DD/YYYY format")
    return value


def normalize_phone(value: str, field_name: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 10:
        raise ValueError(f"{field_name} must be a valid U.S. 10-digit phone number")
    return digits


def validate_name(value: str) -> str:
    if not NAME_RE.match(value):
        raise ValueError("must be 1-50 alphabetic characters, hyphens, or apostrophes")
    return value


def validate_dob(value: date) -> date:
    if value > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    return value


def validate_sex(value: str) -> str:
    normalized = value.strip().lower()
    for canonical in SEX_VALUES:
        if canonical.lower() == normalized:
            return canonical
    raise ValueError(f"sex must be one of {SEX_VALUES}")


def validate_city(value: str) -> str:
    if not (1 <= len(value) <= 100):
        raise ValueError("city must be 1-100 characters")
    return value


def validate_state(value: str) -> str:
    value = value.upper()
    if value not in US_STATE_CODES:
        raise ValueError("state must be a valid 2-letter U.S. state abbreviation")
    return value


def validate_zip(value: str) -> str:
    if not ZIP_RE.match(value):
        raise ValueError("zip_code must be 5-digit or ZIP+4 U.S. format")
    return value


def validate_member_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if not MEMBER_ID_RE.match(value):
        raise ValueError("insurance_member_id must be alphanumeric")
    return value


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[EmailStr] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_to_none(cls, v):
        # Vapi's LLM sometimes sends "" instead of omitting an optional field
        # the caller never provided a value for -- treat that as "no email".
        return v or None

    @field_validator("first_name", "last_name")
    @classmethod
    def _check_name(cls, v):
        return validate_name(v)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _parse_dob(cls, v):
        return parse_dob(v)

    @field_validator("date_of_birth")
    @classmethod
    def _check_dob(cls, v):
        return validate_dob(v)

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, v):
        return validate_sex(v)

    @field_validator("phone_number")
    @classmethod
    def _check_phone(cls, v):
        return normalize_phone(v, "phone_number")

    @field_validator("emergency_contact_phone")
    @classmethod
    def _check_emergency_phone(cls, v):
        return normalize_phone(v, "emergency_contact_phone") if v else None

    @field_validator("city")
    @classmethod
    def _check_city(cls, v):
        return validate_city(v)

    @field_validator("state")
    @classmethod
    def _check_state(cls, v):
        return validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def _check_zip(cls, v):
        return validate_zip(v)

    @field_validator("insurance_member_id")
    @classmethod
    def _check_member_id(cls, v):
        return validate_member_id(v)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional to support partial updates via PUT."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_to_none(cls, v):
        return v or None

    @field_validator("first_name", "last_name")
    @classmethod
    def _check_name(cls, v):
        return validate_name(v) if v is not None else v

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _parse_dob(cls, v):
        return parse_dob(v) if v is not None else v

    @field_validator("date_of_birth")
    @classmethod
    def _check_dob(cls, v):
        return validate_dob(v) if v is not None else v

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, v):
        return validate_sex(v) if v is not None else v

    @field_validator("phone_number")
    @classmethod
    def _check_phone(cls, v):
        return normalize_phone(v, "phone_number") if v else v

    @field_validator("emergency_contact_phone")
    @classmethod
    def _check_emergency_phone(cls, v):
        return normalize_phone(v, "emergency_contact_phone") if v else v

    @field_validator("city")
    @classmethod
    def _check_city(cls, v):
        return validate_city(v) if v is not None else v

    @field_validator("state")
    @classmethod
    def _check_state(cls, v):
        return validate_state(v) if v is not None else v

    @field_validator("zip_code")
    @classmethod
    def _check_zip(cls, v):
        return validate_zip(v) if v is not None else v

    @field_validator("insurance_member_id")
    @classmethod
    def _check_member_id(cls, v):
        return validate_member_id(v)


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CallTranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: Optional[str] = None
    call_id: Optional[str] = None
    phone_number: Optional[str] = None
    transcript: Optional[str] = None
    ended_reason: Optional[str] = None
    created_at: datetime
