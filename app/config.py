import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).parent.parent

# Settings file path
SETTINGS_FILE = BASE_DIR / "settings.json"


class Config:
    """Application configuration"""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    
    # Backboard.io defaults
    BACKBOARD_API_KEY = os.environ.get("BACKBOARD_API_KEY", "")
    BACKBOARD_BASE_URL = os.environ.get("BACKBOARD_BASE_URL", "https://app.backboard.io/api")
    DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gpt-5-chat-latest")


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
