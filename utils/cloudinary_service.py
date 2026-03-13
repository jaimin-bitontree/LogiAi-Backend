import cloudinary
import cloudinary.uploader
from config.settings import settings
import logging
import fitz  # PyMuPDF
import io

logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)


def compress_pdf(file_bytes: bytes) -> bytes:
    """Compress PDF using PyMuPDF (fitz) for files > 5MB"""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # Save with compression settings
        compressed = io.BytesIO()
        doc.save(
            compressed,
            garbage=4,        # Maximum garbage collection
            deflate=True,     # Compress streams
            clean=True,       # Clean up unused objects
            linear=True,      # Linearize (optimize for web)
        )
        doc.close()
        
        return compressed.getvalue()
    except Exception as e:
        logger.error(f"PDF compression failed: {e}")
        return file_bytes  # Return original if compression fails


async def upload_pdf_to_cloudinary(file_bytes: bytes, filename: str) -> dict:
    """Upload PDF to Cloudinary with automatic compression for files > 5MB"""
    try:
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
        # Compress if file > 5MB
        if file_size_mb > 5:
            logger.info(f"PDF size {file_size_mb:.2f}MB > 5MB, compressing with fitz...")
            compressed_bytes = compress_pdf(file_bytes)
            new_size_mb = len(compressed_bytes) / (1024 * 1024)
            logger.info(f"Compressed from {file_size_mb:.2f}MB to {new_size_mb:.2f}MB")
            file_bytes = compressed_bytes
        
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="raw",
            folder="logiai_pdfs",
            public_id=filename.replace(".pdf", ""),
            format="pdf",
        )
        
        logger.info(f"PDF uploaded successfully: {filename}")
        
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
        file_size_mb = len(file_bytes) / (1024 * 1024)
        
       
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
        
        logger.info(f"Excel uploaded: {filename} ({file_size_mb:.2f}MB)")
        
        return {
            "public_id": result["public_id"],
            "url": result["secure_url"]
        }
    except Exception as e:
        logger.error(f"Cloudinary Excel upload failed: {e}")
        return None
