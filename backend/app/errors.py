from fastapi import HTTPException


def api_error(status: int, code: str, **params) -> HTTPException:
    """An error the frontend shows in the person's language: `detail` is a code (errors.<code> in the locales),
    with the values the text needs as extra fields."""
    return HTTPException(status, {"code": code, **params} if params else code)
