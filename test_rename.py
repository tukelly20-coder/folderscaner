import os, sys
sys.path.insert(0, 'backend')
os.chdir('C:/Users/Kelly/Desktop/Repo/folderscaner')
sys.stdout = sys.stdout if sys.stdout.encoding == 'utf-8' else open(sys.stdout.buffer.fileno(), 'w', encoding='utf-8')

from app.database.database import SessionLocal
from app.services.folder_rename import FolderRenameService, RenameError

db = SessionLocal()
svc = FolderRenameService(db)

def p(*a):
    print(*a)

# Test 1: Valid rename PLSX001 -> PLSX999
p('=== Test 1: Valid rename ===')
try:
    result = svc.rename_folder(1, 'PLSX999')
    p('  SUCCESS: ' + result.name + ' (old: PLSX001)')
    new_path = os.path.join(os.path.dirname('test_smb_root/PLSX001'.replace('/', os.sep)), 'PLSX999')
    test_root = 'C:/Users/Kelly/Desktop/Repo/folderscaner/test_smb_root'
    p('  New path exists: ' + str(os.path.exists(test_root + '/PLSX999')))
    p('  Old path gone: ' + str(not os.path.exists(test_root + '/PLSX001')))
except RenameError as e:
    p('  FAILED: ' + e.error_code + ' - ' + e.message)

# Test 2: Duplicate name
p('=== Test 2: Duplicate name ===')
try:
    svc.rename_folder(1, 'PLSX002')
    p('  UNEXPECTED SUCCESS')
except RenameError as e:
    p('  EXPECTED: ' + e.error_code + ' - ' + e.message + ' (HTTP ' + str(e.status_code) + ')')

# Test 3: Invalid characters
p('=== Test 3: Invalid name ===')
try:
    svc.rename_folder(1, 'PLSX<TEST>')
    p('  UNEXPECTED SUCCESS')
except RenameError as e:
    p('  EXPECTED: ' + e.error_code + ' - ' + e.message)

# Test 4: Empty name
p('=== Test 4: Empty name ===')
try:
    svc.rename_folder(1, '')
    p('  UNEXPECTED SUCCESS')
except RenameError as e:
    p('  EXPECTED: ' + e.error_code + ' - ' + e.message)

# Verify events
from app.models.folder_event import FolderEvent
events = db.query(FolderEvent).all()
p('')
p('Total events: ' + str(events.count()))
for e in events:
    old = e.old_name or 'NULL'
    new = e.new_name or 'NULL'
    p('  type=' + e.event_type.value + ' source=' + str(e.source) + ' old=' + old + ' new=' + new)

db.close()
p('')
p('All rename tests completed.')
