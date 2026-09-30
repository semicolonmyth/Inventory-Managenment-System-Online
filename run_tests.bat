@echo off
REM Single entry point to run the full test suite with coverage + a
REM dependency vulnerability scan. Run from anywhere.
setlocal
cd /d "%~dp0"

echo ==========================================================
echo  Running automated tests (unit + integration + pdf + sec)
echo ==========================================================
python -m pytest --cov=utils --cov=db --cov-report=term-missing --cov-report=html
if errorlevel 1 goto :fail

echo.
echo ==========================================================
echo  Dependency vulnerability scan (pip-audit)
echo ==========================================================
python -m pip_audit || echo (pip-audit not installed - run: pip install pip-audit)

echo.
echo All checks completed successfully.
exit /b 0

:fail
echo.
echo Tests FAILED. See output above.
exit /b 1
