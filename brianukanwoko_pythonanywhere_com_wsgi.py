import sys
import os

# Add your home folder to Python path
path = '/home/BrianUkanwoko'
if path not in sys.path:
    sys.path.insert(0, path)

# Change working directory
os.chdir(path)

# Import the FastAPI app via Mangum (ASGI → WSGI)
from main import handler as application