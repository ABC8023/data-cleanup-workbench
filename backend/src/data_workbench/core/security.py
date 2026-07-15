import secrets


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
