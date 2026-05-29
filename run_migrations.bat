@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment was not found: .venv\Scripts\python.exe
  echo Create it first and install dependencies from requirements.txt.
  exit /b 1
)

if "%~1"=="" (
  ".venv\Scripts\python.exe" -c "from app.migration_runner import run_database_migrations; run_database_migrations(); print('Database migrations applied')"
) else (
  ".venv\Scripts\python.exe" -m alembic %*
)

exit /b %ERRORLEVEL%
