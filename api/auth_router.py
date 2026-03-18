from fastapi import APIRouter, HTTPException
from db.client import get_db
from models.auth import Admin
from schemas.auth_schema import CreateAdminRequest, LoginRequest, LoginResponse
from utils.auth.password import hash_password, verify_password
from utils.auth.jwt_service import create_access_token, get_token_expiry_seconds
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/create-admin")
async def create_admin(request: CreateAdminRequest):
    """
    Create a new admin user with all fields
    """
    try:
        db = get_db()
        
        # Check if admin already exists
        existing = await db.admins.find_one({"email": request.email})
        if existing:
            return {
                "success": False,
                "message": f"Admin with email {request.email} already exists"
            }
        
        # Create admin data
        admin_data = {
            "user_id": str(uuid.uuid4()),
            "email": request.email,
            "password_hash": hash_password(request.password),
            "full_name": request.full_name,
            "role": request.role,
            "created_at": datetime.utcnow(),
            "last_login": None
        }
        
        # Insert admin
        admin = Admin(**admin_data)
        result = await db.admins.insert_one(admin.model_dump())
        
        if result.inserted_id:
            logger.info(f"Admin user created: {request.email}")
            return {
                "success": True,
                "message": "Admin user created successfully",
                "user_id": admin_data["user_id"],
                "email": request.email,
                "full_name": request.full_name,
                "role": request.role
            }
        else:
            return {
                "success": False,
                "message": "Failed to create admin user"
            }
            
    except Exception as e:
        logger.error(f"Error creating admin: {e}")
        return {
            "success": False,
            "message": "Internal server error"
        }


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Admin login endpoint
    """
    try:
        db = get_db()
        
        # Find admin by email
        admin_doc = await db.admins.find_one({"email": request.email})
        if not admin_doc:
            return {
                "success": False,
                "message": "Invalid email or password"
            }
        
        admin = Admin(**admin_doc)
        
        # Verify password
        if not verify_password(request.password, admin.password_hash):
            return {
                "success": False,
                "message": "Invalid email or password"
            }
        
        # Update last login
        await db.admins.update_one(
            {"user_id": admin.user_id},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        
        # Create JWT token
        token_data = {
            "user_id": admin.user_id,
            "email": admin.email,
            "role": admin.role
        }
        access_token = create_access_token(data=token_data)
        
        logger.info(f"Admin login successful: {request.email}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": get_token_expiry_seconds(),
            "user_info": {
                "user_id": admin.user_id,
                "email": admin.email,
                "full_name": admin.full_name,
                "role": admin.role
            }
        }
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return {
            "success": False,
            "message": "Internal server error"
        }