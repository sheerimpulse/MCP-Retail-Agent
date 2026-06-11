import os
import subprocess
import sys

venv_dir = "venv"

# Create virtual environment
if not os.path.exists(venv_dir):
    subprocess.check_call([sys.executable, "-m", "venv", venv_dir])

# Pick the correct pip path
if os.name == "nt":  # Windows
    pip = os.path.join(venv_dir, "Scripts", "pip")
else:  # macOS/Linux
    pip = os.path.join(venv_dir, "bin", "pip")

# Install dependencies
subprocess.check_call([
    pip,
    "install",
    "--upgrade",
    "pip"
])

subprocess.check_call([
    pip,
    "install",
    "-r",
    "requirements.txt"
])

print("Setup complete!")