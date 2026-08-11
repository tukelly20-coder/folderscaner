import os

path1 = r'C:\Users\Kelly\Desktop\Repo\folderscaner\backend\app\services\folder_rename.py'
with open(path1, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """        asyncio.create_task(
            ws_manager.broadcast(
                {
                    "event": "folder_renamed",
                    "folder_id": folder.id,
                    "name": folder.name,
                    "old_name": old_name,
                    "relative_path": folder.relative_path,
                    "absolute_path": folder.absolute_path,
                    "status": folder.status.value,
                }
            )
        )"""

new_block = """        ws_data = {
            "event": "folder_renamed",
            "folder_id": folder.id,
            "name": folder.name,
            "old_name": old_name,
            "relative_path": folder.relative_path,
            "absolute_path": folder.absolute_path,
            "status": folder.status.value,
        }
        try:
            asyncio.get_running_loop().create_task(
                ws_manager.broadcast(ws_data)
            )
        except RuntimeError:
            try:
                asyncio.run(ws_manager.broadcast(ws_data))
            except RuntimeError:
                pass"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path1, 'w', encoding='utf-8') as f:
        f.write(content)
    print('folder_rename.py FIXED')
else:
    print('OLD BLOCK NOT FOUND - showing context:')
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'create_task' in line or 'broadcast' in line.lower():
            start = max(0, i-2)
            end = min(len(lines), i+3)
            for j in range(start, end):
                print(f'  {j}: {lines[j]}')
            print('---')

# Fix folder_scanner.py
path2 = r'C:\Users\Kelly\Desktop\Repo\folderscaner\backend\app\services\folder_scanner.py'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()

old_notify = """        try:
            loop = asyncio.get_event_loop()
            loop.create_task(ws_manager.broadcast(data))
        except RuntimeError:
            asyncio.run(ws_manager.broadcast(data))"""

new_notify = """        try:
            asyncio.get_running_loop().create_task(
                ws_manager.broadcast(data)
            )
        except RuntimeError:
            try:
                asyncio.run(ws_manager.broadcast(data))
            except RuntimeError:
                pass"""

if old_notify in content2:
    content2 = content2.replace(old_notify, new_notify)
    with open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)
    print('folder_scanner.py FIXED')
else:
    print('scanner old_notify NOT FOUND - showing context:')
    lines = content2.split('\n')
    for i, line in enumerate(lines):
        if 'create_task' in line or 'get_event_loop' in line:
            start = max(0, i-2)
            end = min(len(lines), i+3)
            for j in range(start, end):
                print(f'  {j}: {lines[j]}')
            print('---')
