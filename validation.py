"""
Security and validation utilities for PDF Tool API
Handles file type validation, size validation, and filename sanitization
"""
import os
import re
from fastapi import UploadFile, HTTPException
from typing import List
from config import config

# Try to import python-magic, fall back to basic validation if not available
try:
    import magic
    MAGIC_AVAILABLE = True
except (ImportError, OSError):
    MAGIC_AVAILABLE = False
    print("Warning: python-magic not available, using basic file type validation")


class RequestValidator:
    """Validates and sanitizes incoming requests for security"""
    
    def __init__(self):
        if MAGIC_AVAILABLE:
            try:
                self.magic = magic.Magic(mime=True)
            except Exception as e:
                print(f"Warning: Could not initialize magic: {e}")
                self.magic = None
        else:
            self.magic = None
    
    def _detect_mime_type_basic(self, file_content: bytes) -> str:
        """
        Basic MIME type detection using magic numbers
        Fallback when python-magic is not available
        """
        # PDF magic number
        if file_content.startswith(b'%PDF-'):
            return 'application/pdf'
        
        # JPEG magic numbers
        if file_content.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        
        # PNG magic number
        if file_content.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        
        # DOCX (ZIP-based) magic number
        if file_content.startswith(b'PK\x03\x04'):
            # Check if it's a DOCX by looking for specific content
            if b'word/' in file_content[:2048]:
                return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            # Check if it's an XLSX
            if b'xl/' in file_content[:2048]:
                return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            return 'application/zip'
        
        return 'application/octet-stream'
    
    def validate_file_type(self, file: UploadFile, allowed_types: List[str] = None) -> bool:
        """
        Validate file type using magic numbers (not just extension)
        
        Args:
            file: The uploaded file to validate
            allowed_types: List of allowed MIME types (defaults to config)
        
        Returns:
            True if file type is valid
        
        Raises:
            HTTPException: If file type is invalid
        """
        if allowed_types is None:
            allowed_types = config.ALLOWED_FILE_TYPES
        
        # Read first 2048 bytes to detect file type
        file_content = file.file.read(2048)
        file.file.seek(0)  # Reset file pointer
        
        # Detect MIME type using magic numbers
        if self.magic:
            try:
                detected_mime = self.magic.from_buffer(file_content)
            except Exception:
                # Fall back to basic detection
                detected_mime = self._detect_mime_type_basic(file_content)
        else:
            detected_mime = self._detect_mime_type_basic(file_content)
        
        if detected_mime not in allowed_types:
            raise HTTPException(
                status_code=415,
                detail=f"Invalid file type. Detected: {detected_mime}. Allowed types: {', '.join(allowed_types)}"
            )
        
        return True
    
    def validate_file_size(self, file: UploadFile, max_size: int = None) -> bool:
        """
        Validate file size against maximum limit
        
        Args:
            file: The uploaded file to validate
            max_size: Maximum file size in bytes (defaults to config)
        
        Returns:
            True if file size is valid
        
        Raises:
            HTTPException: If file size exceeds limit
        """
        if max_size is None:
            max_size = config.MAX_FILE_SIZE
        
        # Get file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File size ({file_size / (1024 * 1024):.2f}MB) exceeds maximum allowed size ({max_size_mb:.0f}MB)"
            )
        
        return True
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal attacks
        
        Args:
            filename: The original filename
        
        Returns:
            Sanitized filename safe for use
        """
        # Remove any path components
        filename = os.path.basename(filename)
        
        # Remove or replace dangerous characters
        # Allow only alphanumeric, dots, hyphens, and underscores
        filename = re.sub(r'[^\w\s\-\.]', '', filename)
        
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        
        # Prevent empty filename
        if not filename:
            filename = "unnamed_file"
        
        # Prevent path traversal patterns
        filename = filename.replace('..', '')
        
        # Limit filename length
        max_length = 255
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            filename = name[:max_length - len(ext)] + ext
        
        return filename
    
    def validate_and_sanitize(self, file: UploadFile) -> str:
        """
        Perform all validation and sanitization on an uploaded file
        
        Args:
            file: The uploaded file
        
        Returns:
            Sanitized filename
        
        Raises:
            HTTPException: If validation fails
        """
        # Validate file type
        self.validate_file_type(file)
        
        # Validate file size
        self.validate_file_size(file)
        
        # Sanitize filename
        sanitized_name = self.sanitize_filename(file.filename)
        
        return sanitized_name


# Create a singleton instance
validator = RequestValidator()
