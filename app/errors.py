def format_pydantic_errors(exc) -> str:
    """Turn a Pydantic/FastAPI validation exception into one human-readable string.

    Both pydantic.ValidationError and fastapi.exceptions.RequestValidationError
    expose the same .errors() shape: a list of {"loc": [...], "msg": "..."}.
    """
    return "; ".join(
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
    )


def structured_pydantic_errors(exc) -> list[dict]:
    """Same data as format_pydantic_errors, but as a [{field, message}] list.

    A voice agent's LLM needs to know exactly *which* field to re-prompt for;
    handing it a single semicolon-joined string for a multi-field error
    (e.g. bad state AND bad phone in one call) makes that harder than it
    needs to be. This gives it a field name to key off directly.
    """
    return [
        {"field": ".".join(str(part) for part in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
