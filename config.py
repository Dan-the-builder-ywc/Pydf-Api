"""
Configuration management for PDF Tool API
Loads all configuration from environment variables
"""
import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables"""
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = os.getenv(
        "ALLOWED_ORIGINS", 
        "http://localhost:3000,http://localhost:5173"
    ).split(",")
    
    # File Upload Configuration
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB default
    ALLOWED_FILE_TYPES: List[str] = os.getenv(
        "ALLOWED_FILE_TYPES",
        "application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ).split(",")
    
    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    
    # Email Configuration (existing)
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    RECIPIENT_EMAIL: str = os.getenv("RECIPIENT_EMAIL", "")
    EMAIL_SUBJECT: str = os.getenv("EMAIL_SUBJECT", "Pydf Suggestion")
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration on startup"""
        errors = []
        
        # Validate CORS origins
        if not cls.ALLOWED_ORIGINS or cls.ALLOWED_ORIGINS == [""]:
            errors.append("ALLOWED_ORIGINS must be set")
        
        # Validate file size limit
        if cls.MAX_FILE_SIZE <= 0:
            errors.append("MAX_FILE_SIZE must be greater than 0")
        
        # Validate rate limit
        if cls.RATE_LIMIT_ENABLED and cls.RATE_LIMIT_PER_MINUTE <= 0:
            errors.append("RATE_LIMIT_PER_MINUTE must be greater than 0")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")


# Create a singleton instance
config = Config()
