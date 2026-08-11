# Folder Sync & Excel-like Data Management System

## 1. Objective

Two-way folder synchronization: **Local PC -> SMB Share -> Server Scanner -> Database -> Web DataGrid**

## 2. Architecture

```
LOCAL PC -> SMB Share -> Folder Scanner -> Database -> FastAPI -> WebSocket -> Web App
                                              ^                       |
                                              |     Edit              |
                                              v                       |
                                          Folder Rename Service ----->|
```

## 3. Data Flow

### Local -> Web
1. User changes folder in Windows Explorer
2. Scanner detects change on next poll
3. Database updated with new name/path/status
4. Event logged in folder_events
5. WebSocket notification pushed to Web
6. Web grid updates in realtime

### Web -> Local
1. User edits folder name in Web DataGrid
2. PUT /api/folders/{id} received
3. Server validates name, checks duplicates
4. Server checks folder exists (concurrent mod check)
5. Server performs os.rename() on SMB filesystem
6. ONLY on success: update database, create event, notify web
7. On failure: error returned, database untouched

## 4. Database Schema

### folders
| Column          | Type    | Description                    |
|-----------------|---------|--------------------------------|
| id              | Integer | Fixed ID (never changes)       |
| parent_id       | Integer | Foreign key to folders.id      |
| name            | String  | Current folder name            |
| relative_path   | String  | Path relative to SMB_ROOT      |
| absolute_path   | String  | Full SMB/UNC path              |
| status          | Enum    | active / deleted / pending     |
| first_seen      | DateTime| First discovery timestamp      |
| last_seen       | DateTime| Last scan timestamp            |
| created_at      | DateTime| Record creation time           |
| updated_at      | DateTime| Last update time               |

### folder_events (append-only, never deleted)
| Column          | Type    | Description                              |
|-----------------|---------|------------------------------------------|
| id              | Integer | Primary key                              |
| folder_id       | Integer | Foreign key to folders.id                |
| event_type      | Enum    | created / deleted / modified / renamed / moved |
| old_name        | String  | Previous name (nullable)                 |
| new_name        | String  | New name (nullable)                      |
| old_path        | String  | Previous path (nullable)                 |
| new_path        | String  | New path (nullable)                      |
| detected_at     | DateTime| When event was detected                  |
| source          | String  | SCANNER / WEB / API                      |

## 5. Fixed Folder IDs

Folder IDs are fixed integers assigned by the database on first discovery.
Renaming only changes the `name` column.

## 6. Folder Name Validation

Forbidden: `< > : " / \ | ? *` and reserved Windows names (CON, PRN, AUX, NUL, COM1-9, LPT1-9).

## 7. REST API

| Method | Path                        | Description                  |
|--------|----------------------------|------------------------------|
| GET    | /api/folders               | List folders                 |
| GET    | /api/folders/{id}          | Get single folder            |
| PUT    | /api/folders/{id}          | Update/rename folder         |
| DELETE | /api/folders/{id}          | Soft-delete folder           |
| GET    | /api/folders/export/excel  | Export to XLSX               |
| GET    | /api/folder-events         | List events (filtered)       |
| GET    | /api/folder-events/{id}    | Get single event             |
| GET    | /api/scanner/status        | Scanner status               |
| POST   | /api/scanner/scan          | Manual scan trigger          |
| WS     | /ws/folders                | Realtime updates             |

## 8. Error Handling

```json
{
    "error": "FOLDER_ALREADY_EXISTS",
    "message": "Folder PLSX002 already exists."
}
```

## 9. Concurrency

Before rename, server verifies folder still exists at expected path.
If not, returns HTTP 409 Conflict.

## 10. Technology Stack

- **Backend**: Python 3.10, FastAPI, SQLAlchemy, Pydantic, pandas, openpyxl
- **Frontend**: React 18, TypeScript, Vite, ag-grid-community
- **Database**: SQLite (dev), PostgreSQL (prod)
- **Infrastructure**: Docker Compose, Nginx
