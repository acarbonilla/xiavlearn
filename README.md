# XiAv Learn

This repository is structured to separate the Django backend from a future Next.js frontend.

## Project Layout

- `Backend/`
  - Django backend project
  - `manage.py`
  - `.env`
  - `.venv/`
  - `requirements.txt`
  - `xiavlearn/`
  - `accounts/`
  - `learning/`
  - `agents/`
  - `analytics/`

- `frontend/`
  - Placeholder for the Next.js application

- `documentation/`
  - Project notes and planning documents

## Backend Setup

1. Navigate to the backend folder:
   ```powershell
   cd Backend
   ```

2. Activate the Python virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Run Django migrations and seed data:
   ```powershell
   python manage.py migrate
   python manage.py seed_learning_data
   ```

5. Start the backend server:
   ```powershell
   python manage.py runserver
   ```

## Frontend Setup

The `frontend/` folder is currently a placeholder for the future Next.js frontend.

## Notes

- The Django backend uses PostgreSQL via `python-decouple` and the `.env` file.
- The backend includes initial learning models and seed data for the MVP.
