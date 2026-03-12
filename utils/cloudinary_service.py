import cloudinary
import cloudinary.uploader
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

async def upload_pdf_to_cloudinary(file_bytes: bytes, filename: str) -> dict:
    """Upload PDF to Cloudinary and return public_id + url"""
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="raw",
            folder="logiai_pdfs",
            public_id=filename.replace(".pdf", ""),
            format="pdf",  
            
        )
        return {
            "public_id": result["public_id"],
            "url": result["secure_url"]
        }
    except Exception as e:
        logger.error(f"Cloudinary PDF upload failed: {e}")
        return None


async def upload_excel_to_cloudinary(file_bytes: bytes, filename: str) -> dict:
    """Upload Excel file to Cloudinary and return public_id + url"""
    try:
        # Remove Excel extensions for clean public_id
        clean_filename = filename.replace(".xlsx", "").replace(".xls", "")
        
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="raw",
            folder="logiai_excel",
            public_id=clean_filename,
            format="xls",  
            flags="attachment"
        )
        return {
            "public_id": result["public_id"],
            "url": result["secure_url"]
        }
    except Exception as e:
        logger.error(f"Cloudinary Excel upload failed: {e}")
        return None
