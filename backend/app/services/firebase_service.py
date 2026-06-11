import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from app.core.config import settings

_initialized = False


def init_firebase() -> None:
    global _initialized
    if not _initialized:
        cred = credentials.Certificate(settings.get_firebase_credentials())
        firebase_admin.initialize_app(cred)
        _initialized = True


async def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return the decoded claims."""
    init_firebase()
    decoded = firebase_auth.verify_id_token(id_token)
    return decoded


def get_firebase_user(uid: str) -> firebase_auth.UserRecord:
    init_firebase()
    return firebase_auth.get_user(uid)
