import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load local environment file if present (.env is excluded from git)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except Exception:
    pass

is_vercel = os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') is not None

if is_vercel:
    upload_dir = '/tmp/uploads'
    db_path = 'sqlite:////tmp/loan_system.db'
else:
    upload_dir = os.path.join(BASE_DIR, 'uploads')
    db_file_path = os.path.join(BASE_DIR, 'instance', 'loan_system.db').replace('\\', '/')
    db_path = f'sqlite:///{db_file_path}'

# Require SECRET_KEY environment variable with no hardcoded fallback
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    raise ValueError(
        "CRITICAL SECURITY CONFIGURATION ERROR: The 'SECRET_KEY' environment variable is required and must be set. "
        "AJIT ZONE HRMS requires a strong, unique SECRET_KEY configured in your environment variables or .env file."
    )

class Config:
    SECRET_KEY = _secret_key
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or db_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = upload_dir
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx', 'xls', 'csv'}
    COMPANY_NAME = "AJIT ZONE PVT. LTD."
    DEFAULT_DEDUCTION_DAY = 5
    # Production Session Security
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 28800  # 8 hours matching session lifetime
