@echo off
REM Batch script to build executable and create Windows installer
REM This script automates the entire build process

echo ========================================
echo Store Management System - Build Script
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo Step 1: Installing/Updating dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Building executable with PyInstaller...
python build_exe.py
if errorlevel 1 (
    echo ERROR: Failed to build executable
    pause
    exit /b 1
)
echo.

REM Check if Inno Setup is available
where "iscc.exe" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Inno Setup Compiler (iscc.exe) not found in PATH
    echo.
    echo To create the installer:
    echo 1. Download and install Inno Setup from: https://jrsoftware.org/isinfo.php
    echo 2. Add Inno Setup bin directory to your system PATH, OR
    echo 3. Manually compile installer.iss using Inno Setup Compiler GUI
    echo.
    echo The executable is ready at: dist\StoreManagementSystem.exe
    echo.
    pause
    exit /b 0
)

echo Step 3: Creating Windows Installer...
iscc installer.iss
if errorlevel 1 (
    echo ERROR: Failed to create installer
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Executable: dist\StoreManagementSystem.exe
echo Installer: installer\StoreManagementSystem_Setup.exe
echo.
pause

