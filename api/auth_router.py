from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db.client import get_db
from models.auth import Admin
from schemas.auth_schema import CreateAdminRequest, LoginRequest
from utils.auth.password import hash_password, verify_password
from utils.auth.jwt_service import create_access_token, get_token_expiry_seconds
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/create-admin")
async def create_admin(request: CreateAdminRequest):
    try:
        db = get_db()
        
        existing = await db.admins.find_one({"email": request.email})
        if existing:
            return JSONResponse(status_code=400, content={
                "success": False,
                "message": f"Admin with email {request.email} already exists"
            })
        
        admin_data = {
            "user_id": str(uuid.uuid4()),
            "email": request.email,
            "password_hash": hash_password(request.password),
            "full_name": request.full_name,
            "role": request.role,
            "created_at": datetime.utcnow().isoformat(),
            "last_login": None
        }
        
        result = await db.admins.insert_one(admin_data)
        
        if result.inserted_id:
            logger.info(f"Admin user created: {request.email}")
            return JSONResponse(status_code=201, content={
                "success": True,
                "message": "Admin user created successfully",
                "user_id": admin_data["user_id"],
                "email": request.email,
                "full_name": request.full_name,
                "role": request.role
            })
        else:
            return JSONResponse(status_code=500, content={
                "success": False,
                "message": "Failed to create admin user"
            })
            
    except Exception as e:
        logger.error(f"Error creating admin: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Internal server error"
        })


@router.post("/login")
async def login(request: LoginRequest):
    try:
        db = get_db()
        
        # Find admin by email
        admin_doc = await db.admins.find_one({"email": request.email})
        if not admin_doc:
            return JSONResponse(status_code=404, content={
                "success": False,
                "message": "Email not found"
            })
        
        admin = Admin(**admin_doc)
        
        # Verify password
        if not verify_password(request.password, admin.password_hash):
            return JSONResponse(status_code=401, content={
                "success": False,
                "message": "Incorrect password"
            })
        
        # Update last login
        await db.admins.update_one(
            {"user_id": admin.user_id},
            {"$set": {"last_login": datetime.utcnow().isoformat()}}
        )
        
        # Create token
        token_data = {
            "user_id": admin.user_id,
            "email": admin.email,
            "role": admin.role
        }
        access_token = create_access_token(data=token_data)
        
        logger.info(f"Admin login successful: {request.email}")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": get_token_expiry_seconds(),
            "user_info": {
                "user_id": admin.user_id,
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role
            }
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": "Internal server error"
        })