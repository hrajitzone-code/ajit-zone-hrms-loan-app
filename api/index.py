import sys
import os

# Add parent directory to sys.path so app module can be imported on Vercel
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()
