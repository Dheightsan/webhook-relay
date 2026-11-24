import hmac

from fastapi import Header, HTTPException, Request, status


def require_admin(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected: str = request.app.state.settings.admin_api_key
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
