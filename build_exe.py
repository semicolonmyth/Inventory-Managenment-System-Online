"""
Build script for creating Windows executable using PyInstaller.
"""
import subprocess
import sys
from pathlib import Path

def build_executable():
    """Build the executable using PyInstaller."""
    project_root = Path(__file__).parent
    
    print("=" * 60)
    print("Building Store Management System Executable")
    print("=" * 60)
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"✓ PyInstaller found: {PyInstaller.__version__}")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller installed successfully")
    
    # Check if icon exists
    icon_path = project_root / "Icons" / "appico.ico"
    if not icon_path.exists():
        print(f"⚠ Warning: Icon not found at {icon_path}")
    else:
        print(f"✓ Icon found: {icon_path}")
    
    # Build using spec file
    spec_file = project_root / "build.spec"
    if spec_file.exists():
        print(f"\nBuilding with spec file: {spec_file}")
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            str(spec_file)
        ]
    else:
        print("\nBuilding without spec file (using command line options)")
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=StoreManagementSystem",
            "--onefile",
            "--windowed",
            "--icon=" + str(icon_path),
            "--add-data=Icons;Icons",
            "--add-data=themes;themes",
            "--add-data=utils/config.json;utils",
            "--hidden-import=customtkinter",
            "--hidden-import=PIL._tkinter_finder",
            "--hidden-import=sqlalchemy.dialects.sqlite",
            "main.py"
        ]
    
    print("\nRunning PyInstaller...")
    print(" ".join(cmd))
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, check=True, cwd=project_root)
        print("-" * 60)
        print("✓ Build completed successfully!")
        print(f"\nExecutable location: {project_root / 'dist' / 'StoreManagementSystem.exe'}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Build failed with error code: {e.returncode}")
        return False

if __name__ == "__main__":
    success = build_executable()
    sys.exit(0 if success else 1)

