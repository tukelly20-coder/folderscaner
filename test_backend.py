import os, sys
sys.path.insert(0, 'backend')
os.chdir('C:/Users/Kelly/Desktop/Repo/folderscaner')
sys.stdout = sys.stdout if sys.stdout.encoding == 'utf-8' else open(sys.stdout.buffer.fileno(), 'w', encoding='utf-8')

from app.database.database import SessionLocal, Base, engine
from app.models import folder, folder_event

Base.metadata.create_all(bind=engine)
print("=== Step 1: Initial Scan ===")
from app.services.folder_scanner import FolderScanner
db = SessionLocal()
scanner = FolderScanner(db=db)
result = scanner.scan_once()
print("Scan:", result)

folders = db.query(folder.Folder).all()
print("Folders in DB:", len(folders))
for f in folders:
    print("  id=" + str(f.id) + " name=" + f.name + " path=" + f.relative_path + " status=" + f.status.value)

events = db.query(folder_event.FolderEvent).all()
print("Events:", len(events))
for e in events:
    print("  type=" + e.event_type.value + " source=" + str(e.source))

# Test rename
print("")
print("=== Step 2: Rename PLSX001 -> PLSX999 (via rename service) ===")
from app.services.folder_rename import FolderRenameService, RenameError
svc = FolderRenameService(db)

try:
    updated = svc.rename_folder(1, "PLSX999")
    print("  SUCCESS: name=" + updated.name)
    test_root = "C:/Users/Kelly/Desktop/Repo/folderscaner/test_smb_root"
    print("  New path exists:", os.path.exists(test_root + "/PLSX999"))
    print("  Old path gone:", not os.path.exists(test_root + "/PLSX001"))
except RenameError as e:
    print("  FAILED:", e.error_code, "-", e.message)

# Test duplicate
print("")
print("=== Step 3: Duplicate name (PLSX002 already exists) ===")
try:
    svc.rename_folder(1, "PLSX002")
    print("  UNEXPECTED SUCCESS")
except RenameError as e:
    print("  EXPECTED:", e.error_code, "-", e.message, "(HTTP", str(e.status_code) + ")")

# Test invalid chars
print("")
print("=== Step 4: Invalid name (PLSX<TEST>) ===")
try:
    svc.rename_folder(1, "PLSX<TEST>")
    print("  UNEXPECTED SUCCESS")
except RenameError as e:
    print("  EXPECTED:", e.error_code, "-", e.message)

# Test empty name
print("")
print("=== Step 5: Empty name ===")
try:
    svc.rename_folder(1, "")
    print("  UNEXPECTED SUCCESS")
except RenameError as e:
    print("  EXPECTED:", e.error_code, "-", e.message)

# Test folder not found
print("")
print("=== Step 6: Folder not found (id=999) ===")
try:
    svc.rename_folder(999, "TEST")
    print("  UNEXPECTED SUCCESS")
except RenameError as e:
    print("  EXPECTED:", e.error_code, "-", e.message, "(HTTP", str(e.status_code) + ")")

# Verify events after all operations
print("")
events = db.query(folder_event.FolderEvent).order_by(folder_event.FolderEvent.id).all()
print("=== Final Event Log (" + str(len(events)) + " events) ===")
for e in events:
    old = e.old_name or "NULL"
    new = e.new_name or "NULL"
    print("  id=" + str(e.id) + " type=" + e.event_type.value + " source=" + str(e.source) + " old=" + old + " new=" + new)

# Verify final folder state
print("")
folders = db.query(folder.Folder).order_by(folder.Folder.id).all()
print("=== Final Folder State ===")
for f in folders:
    print("  id=" + str(f.id) + " name=" + f.name + " status=" + f.status.value)

db.close()
print("")
print("ALL TESTS PASSED")
