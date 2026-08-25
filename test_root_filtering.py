import datetime
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, "backend")
os.chdir("C:/Users/Kelly/Desktop/Repo/folderscaner")

from app.api.folders import list_folders


class FakeQuery:
    def __init__(self, folders):
        self._folders = folders

    def order_by(self, *args):
        return self

    def filter(self, *args):
        return self

    def all(self):
        return self._folders


class FakeDb:
    def __init__(self, folders):
        self._folders = folders

    def query(self, *args):
        return FakeQuery(self._folders)


def make_folder(folder_id, name, relative_path, absolute_path, has_metadata=False):
    now = datetime.datetime(2026, 8, 17, 9, 0, folder_id)
    return SimpleNamespace(
        id=folder_id,
        name=name,
        relative_path=relative_path,
        absolute_path=absolute_path,
        last_seen=now,
        updated_at=now,
        document_signature="sig" if has_metadata else None,
        customer_name="Customer" if has_metadata else None,
        salesperson_name=None,
        drawing_codes=["PLSX001"] if has_metadata else [],
        document_scanned_at=now if has_metadata else None,
    )


def main():
    root = r"\\server\share\P002-root"
    in_root = make_folder(
        1,
        "P002-2608-001-A0 current",
        "2026/8/P002-2608-001-A0 current",
        r"\\server\share\P002-root\2026\8\P002-2608-001-A0 current",
    )
    stale_with_metadata = make_folder(
        2,
        "P002-2608-001-A0 stale",
        "2026/8/P002-2608-001-A0 stale",
        r"D:\old-root\2026\8\P002-2608-001-A0 stale",
        has_metadata=True,
    )
    other_relative_only = make_folder(
        3,
        "P003-2608-001-A0 other",
        "2026/8/P003-2608-001-A0 other",
        r"D:\other-root\2026\8\P003-2608-001-A0 other",
        has_metadata=True,
    )

    rows = list_folders(
        limit=500,
        root=root,
        db=FakeDb([stale_with_metadata, other_relative_only, in_root]),
    )

    assert [row.id for row in rows] == [1], [row.id for row in rows]
    assert rows[0].absolute_path == in_root.absolute_path

    rows_without_matching_absolute_path = list_folders(
        limit=500,
        root=root,
        db=FakeDb([stale_with_metadata]),
    )

    assert rows_without_matching_absolute_path == [], [
        row.id for row in rows_without_matching_absolute_path
    ]
    print("root filtering tests passed")


if __name__ == "__main__":
    main()
