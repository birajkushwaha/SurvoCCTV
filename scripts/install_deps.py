import subprocess
import sys

dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "ultralytics",
    "opencv-python",
    "jinja2"
]

print("Starting dependency installation...")
for dep in dependencies:
    print(f"Installing {dep}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
        print(f"Successfully installed {dep}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {dep}. Error: {e}")
        sys.exit(1)

print("All dependencies installed successfully!")
