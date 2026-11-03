# WSGI entry point for PythonAnywhere
# Place this file at: /home/yourusername/chemist_crm_wsgi.py

import sys
import os

# Add your project path to sys.path
path = '/home/yourusername/Hermes-Chemist-CRM/backend'
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables (or use PythonAnywhere env vars)
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://user:pass@host:5432/dbname')
os.environ.setdefault('REDIS_URL', 'redis://host:6379/0')
os.environ.setdefault('SECRET_KEY', 'your-secret-key')
os.environ.setdefault('DEBUG', 'false')
os.environ.setdefault('BACKEND_CORS_ORIGINS', 'https://your-vercel-app.vercel.app')

from app.main import app as application
