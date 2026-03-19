import hashlib


def hash_password(password: str) -> str:
    """Hash a password using SHA256 (simple implementation)"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(plain_password) == hashed_password