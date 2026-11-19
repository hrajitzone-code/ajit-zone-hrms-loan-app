from flask import request
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter

csrf = CSRFProtect()

def get_client_ip():
    """Extract client IP respecting standard reverse-proxy headers (e.g. Vercel)."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.headers.get('X-Real-IP') or request.remote_addr or '127.0.0.1'

limiter = Limiter(
    key_func=get_client_ip,
    default_limits=[],
    storage_uri="memory://"
)
