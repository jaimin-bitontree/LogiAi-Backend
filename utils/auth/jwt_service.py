import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
<<<<<<< HEAD
from config.settings import settings

# JWT Configuration from environment
SECRET_KEY = settings.JWT_SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES
=======

# Simple token implementation - no external dependencies
SECRET_KEY = "logiai-super-secret-key-2024"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
>>>>>>> 9534d8fa87fdb9471ed972ac23ff66d2fd34c619


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create simple token"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        **data,
        "exp": int(expire.timestamp())
    }
    
    # Simple base64 encoding with signature
    token_data = json.dumps(payload)
    encoded_token = base64.b64encode(token_data.encode()).decode()
    
    # Add HMAC signature
    signature = hmac.new(
        SECRET_KEY.encode(),
        encoded_token.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return f"{encoded_token}.{signature}"


def verify_token(token: str) -> Optional[dict]:
    """Verify token"""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
            
        encoded_token, signature = parts
        
        # Verify signature
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            encoded_token.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if signature != expected_signature:
            return None
        
        # Decode payload
        token_data = base64.b64decode(encoded_token.encode()).decode()
        payload = json.loads(token_data)
        
        # Check expiration
        if payload.get('exp', 0) < datetime.utcnow().timestamp():
            return None
            
        return payload
    except Exception:
        return None


def get_token_expiry_seconds() -> int:
    """Get token expiry time in seconds"""
    return ACCESS_TOKEN_EXPIRE_MINUTES * 60


from fastapi import Header, HTTPException


async def verify_auth_token(authorization: str = Header(...)):
    """Dependency to verify JWT token from Authorization header"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={
            "success": False,
            "message": "Invalid token format. Use: Bearer <token>"
        })
    
    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail={
            "success": False,
            "message": "Invalid or expired token"
        })
    
    return payload