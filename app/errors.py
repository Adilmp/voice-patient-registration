def format_pydantic_errors(exc) -> str:
    """Turn a Pydantic/FastAPI validation exception into one human-readable string.

    Both pydantic.ValidationError and fastapi.exceptions.RequestValidationError
    expose the same .errors() shape: a list of {"loc": [...], "msg": "..."}.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
    )
