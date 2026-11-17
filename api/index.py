import sys
import os

# Add parent directory to sys.path so app module can be imported on Vercel
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        print("ENVIRON KEYS:", list(environ.keys()), flush=True)
        for k in ['HTTP_X_MATCHED_PATH', 'x-matched-path', 'HTTP_X_FORWARDED_URI', 'REQUEST_URI', 'RAW_URI', 'PATH_INFO']:
            if k in environ:
                print(f"ENVIRON {k} = {environ[k]}", flush=True)
        matched_path = environ.get('HTTP_X_MATCHED_PATH')
        if matched_path:
            environ['PATH_INFO'] = matched_path
        return self.wsgi_app(environ, start_response)

app = create_app()
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
