# Folder Sync & Excel-like Data Management System

## Overview

A two-way folder synchronization system that monitors SMB/UNC shares, stores
folder metadata in a database, and provides a real-time Excel-like web interface
for viewing and editing folder structures.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 20+
- Docker & Docker Compose (optional)

### 1. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` to set your `SMB_ROOT` (e.g. `C:/shared/project` or `\\LOCAL-PC\PROJECT`).

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
Web UI: http://localhost:5173

### 4. Docker (Production)
```bash
docker-compose up -d
```

## Configuration

| Variable       | Default              | Description                        |
|----------------|---------------------|------------------------------------|
| DATABASE_URL  | sqlite:///./folders.db | Database connection string  |
| SMB_ROOT       | *(required)*        | Path to the shared folder         |
| SCAN_INTERVAL  | 5                  | Scanner polling interval (seconds) |
| SERVER_HOST    | 0.0.0.0            | FastAPI host                       |
| SERVER_PORT    | 8000               | FastAPI port                       |
| SMB_USERNAME   | *(optional)*       | SMB username                       |
| SMB_PASSWORD   | *(optional)*       | SMB password                       |
| EXPORT_DIR     | ./exports         | Export directory                   |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document.

## License

MIT
