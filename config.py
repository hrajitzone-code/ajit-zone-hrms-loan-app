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

# Detect PostgreSQL Database URL (e.g. Neon, Supabase, Vercel Postgres)
raw_db_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or os.environ.get('POSTGRES_PRISMA_URL')
is_postgres = False

if raw_db_url and ('postgres' in raw_db_url.lower()):
    # Normalize postgres:// to postgresql:// for SQLAlchemy 1.4+ and 2.0+
    if raw_db_url.startswith('postgres://'):
        active_db_uri = raw_db_url.replace('postgres://', 'postgresql://', 1)
    else:
        active_db_uri = raw_db_url
    is_postgres = True
    upload_dir = '/tmp/uploads' if is_vercel else os.path.join(BASE_DIR, 'uploads')
else:
    # SQLite Fallback Architecture
    if is_vercel:
        upload_dir = '/tmp/uploads'
        active_db_uri = 'sqlite:////tmp/loan_system.db'
    else:
        upload_dir = os.path.join(BASE_DIR, 'uploads')
        db_file_path = os.path.join(BASE_DIR, 'instance', 'loan_system.db').replace('\\', '/')
        active_db_uri = f'sqlite:///{db_file_path}'

# Require SECRET_KEY environment variable with no hardcoded fallback
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    raise ValueError(
        "CRITICAL SECURITY CONFIGURATION ERROR: The 'SECRET_KEY' environment variable is required and must be set. "
        "AJIT ZONE HRMS requires a strong, unique SECRET_KEY configured in your environment variables or .env file."
    )

class Config:
    SECRET_KEY = _secret_key
    SQLALCHEMY_DATABASE_URI = active_db_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    IS_POSTGRES = is_postgres
    
    # Connection Pooling & Health Monitoring for Managed PostgreSQL
    if is_postgres:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'max_overflow': 20,
            'pool_recycle': 300,
            'pool_pre_ping': True
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {'timeout': 20}
        }
        
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
