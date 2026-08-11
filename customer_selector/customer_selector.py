import os
import json
import tkinter as tk
from tkinter import ttk, messagebox


# ============================================================
# CUSTOMER SELECTOR
# Windows utility:
# - Auto-detect project/customer folder in the same directory
# - Search and select customer from a dropdown
# - Rename the detected folder by appending customer name
#
# Example:
#   03 客户资料_Dữ liệu khách hàng
# becomes:
#   03 客户资料_Dữ liệu khách hàng_华勤
#
# Edit CUSTOMER_LIST below to add/remove customers.
# ============================================================

os.makedirs(r"D:\XQT SW", exist_ok=True)
CUSTOMER_LIST_FILE = os.path.join(r"D:\XQT SW", "customer_list.json")
SALESPERSON_LIST_FILE = os.path.join(r"D:\XQT SW", "salesperson_list.json")

DEFAULT_CUSTOMER_LIST = [
    {"zh": "歌尔 南山", "en": "Goertek", "usage_count": 0},
    {"zh": "万中阳", "en": "Wanzhongyang", "usage_count": 0},
    {"zh": "比亚迪", "en": "BYD", "usage_count": 0},
    {"zh": "富士康", "en": "Foxconn", "usage_count": 0},
    {"zh": "京东方", "en": "BOE", "usage_count": 0},
    {"zh": "立讯精密", "en": "Luxshare", "usage_count": 0},
    {"zh": "海尔 南山", "en": "Haier", "usage_count": 0},
    {"zh": "海信", "en": "Hisense", "usage_count": 0},
    {"zh": "美的", "en": "Midea", "usage_count": 0},
    {"zh": "格力博", "en": "Greebo", "usage_count": 0},
    {"zh": "义安立讯", "en": "Yian Luxshare", "usage_count": 0},
]

DEFAULT_SALESPERSON_LIST = [
    "万中阳",
    "崔永杰",
    "张建",
    "刘明",
    "刘颖",
    "张立刚",
]


def load_salesperson_list():
    if os.path.exists(SALESPERSON_LIST_FILE):
        try:
            with open(SALESPERSON_LIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [str(x) for x in data]
        except Exception:
            pass
    return list(DEFAULT_SALESPERSON_LIST)


def save_salesperson_list(names):
    with open(SALESPERSON_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)


SALESPERSON_LIST = load_salesperson_list()


def load_customer_list():
    if os.path.exists(CUSTOMER_LIST_FILE):
        try:
            with open(CUSTOMER_LIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                if isinstance(data[0], dict):
                    for item in data:
                        item.setdefault("usage_count", 0)
                    return data
                return [{"zh": str(x), "en": "", "usage_count": 0} for x in data]
        except Exception:
            pass
    return list(DEFAULT_CUSTOMER_LIST)


def save_customer_list(names):
    with open(CUSTOMER_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)


CUSTOMER_LIST = load_customer_list()


class CustomerSelector(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Customer Selector")

        self.selected_folder = tk.StringVar()
        self.search_text = tk.StringVar()
        self.customer = tk.StringVar()
        self.salesperson = tk.StringVar()

        self._build_ui()
        self._auto_detect_folder()
        self._refresh_customers()
        self.search_entry.focus_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F2>", lambda e: self._edit_customer())
        self.bind("<Delete>", lambda e: self._delete_customer())

        self.update_idletasks()
        w = 640
        h = 500
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(600, 460)

    def _build_ui(self):
        # Main container
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        # Header
        ttk.Label(
            frame,
            text="Customer Selector",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")

        # Search
        ttk.Label(frame, text="搜索客户：", font=("Segoe UI", 9)).pack(anchor="w")

        self.search_entry = ttk.Entry(
            frame,
            textvariable=self.search_text,
            font=("Segoe UI", 10)
        )
        self.search_entry.pack(fill="x", pady=(4, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search)
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_entry.bind("<Up>", self._on_search_up_down)
        self.search_entry.bind("<Down>", self._on_search_up_down)

        # Customer list
        ttk.Label(frame, text="客户名称：", font=("Segoe UI", 9)).pack(anchor="w")

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=(4, 8))

        columns = ("zh", "en")
        self.customer_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=7,
            selectmode="browse"
        )
        self.customer_tree.heading("zh", text="客户名称（中文）")
        self.customer_tree.heading("en", text="客户名称（英文）")
        self.customer_tree.column("zh", width=220, anchor="w")
        self.customer_tree.column("en", width=160, anchor="w")
        self.customer_tree.pack(
            side="left",
            fill="both",
            expand=True
        )
        self.customer_tree.bind(
            "<<TreeviewSelect>>",
            self._on_customer_select
        )
        self.customer_tree.bind(
            "<Double-Button-1>",
            lambda e: self.rename_folder()
        )

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.customer_tree.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.customer_tree.config(yscrollcommand=scrollbar.set)

        # Selected customer
        selected_frame = ttk.Frame(frame)
        selected_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            selected_frame,
            text="当前选择：",
            font=("Segoe UI", 9)
        ).pack(side="left")

        ttk.Label(
            selected_frame,
            textvariable=self.customer,
            font=("Microsoft YaHei UI", 10, "bold")
        ).pack(side="left", padx=(6, 0))

        # Salesperson
        ttk.Label(frame, text="业务员：", font=("Segoe UI", 9)).pack(anchor="w")

        self.salesperson_combo = ttk.Combobox(
            frame,
            textvariable=self.salesperson,
            values=SALESPERSON_LIST,
            state="readonly",
            font=("Segoe UI", 10)
        )
        self.salesperson_combo.pack(fill="x", pady=(4, 2))
        self.salesperson_combo.bind(
            "<<ComboboxSelected>>",
            self._on_salesperson_select
        )

        # Buttons
        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", pady=(0, 8))

        ttk.Button(
            button_row,
            text="确定",
            command=self.rename_folder,
            width=6
        ).pack(side="right", padx=(0, 6))

        ttk.Button(
            button_row,
            text="删除",
            command=self._delete_customer,
            width=6
        ).pack(side="right", padx=(0, 6))

        ttk.Button(
            button_row,
            text="编辑",
            command=self._edit_customer,
            width=6
        ).pack(side="right", padx=(0, 6))

        ttk.Button(
            button_row,
            text="添加",
            command=self._add_customer,
            width=6
        ).pack(side="right", padx=(0, 6))

        # Status
        self.status = ttk.Label(
            frame,
            text="正在检测文件夹...",
            foreground="gray",
            font=("Segoe UI", 9)
        )
        self.status.pack(anchor="w", pady=(0, 4))

    def _auto_detect_folder(self):
        cwd = os.path.dirname(os.path.abspath(__file__))
        BASE_FOLDER = "03 客户资料_Dữ liệu khách hàng"
        folder_path = os.path.join(cwd, BASE_FOLDER)

        if os.path.isdir(folder_path):
            self.selected_folder.set(BASE_FOLDER)
            self.status.config(
                text=f"已检测到：{BASE_FOLDER}",
                foreground="gray"
            )
            return

        existing = None
        for entry in os.listdir(cwd):
            if entry.startswith(BASE_FOLDER) and os.path.isdir(os.path.join(cwd, entry)):
                existing = entry
                break

        if existing:
            self.selected_folder.set(existing)
            self.status.config(
                text=f"已检测到：{existing}",
                foreground="gray"
            )
        else:
            self.selected_folder.set("")
            self.status.config(
                text=f"未检测到文件夹 03，请点击下方按钮创建",
                foreground="orange"
            )

    def _get_customer_folder_path(self):
        cwd = os.path.dirname(os.path.abspath(__file__))
        BASE_FOLDER = "03 客户资料_Dữ liệu khách hàng"
        folder_path = os.path.join(cwd, BASE_FOLDER)

        if os.path.isdir(folder_path):
            return folder_path

        for entry in os.listdir(cwd):
            if entry.startswith(BASE_FOLDER) and os.path.isdir(os.path.join(cwd, entry)):
                return os.path.join(cwd, entry)

        return None

    def _on_salesperson_select(self, event=None):
        name = self.salesperson.get().strip()

        if not name:
            return

        folder_path = self._get_customer_folder_path()

        if not folder_path:
            self.status.config(
                text="未检测到文件夹 03，无法创建业务员文件",
                foreground="orange"
            )
            return

        file_path = os.path.join(folder_path, f"业务员：{name}.txt")

        if os.path.exists(file_path):
            self.status.config(
                text=f"已选择：业务员：{name}.txt",
                foreground="gray"
            )
            return

        existing_file = None
        for entry in os.listdir(folder_path):
            if entry.startswith("业务员：") and entry.endswith(".txt"):
                existing_file = os.path.join(folder_path, entry)
                break

        if existing_file:
            try:
                os.rename(existing_file, file_path)
                self.status.config(
                    text=f"已切换：业务员：{name}.txt",
                    foreground="green"
                )
                return
            except Exception as e:
                self.status.config(
                    text=f"重命名文件失败：{e}",
                    foreground="red"
                )
                return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("")
            self.status.config(
                text=f"已创建：业务员：{name}.txt",
                foreground="green"
            )
        except Exception as e:
            self.status.config(
                text=f"创建文件失败：{e}",
                foreground="red"
            )

    def _increment_usage(self, customer_name):
        for item in CUSTOMER_LIST:
            if item.get("zh") == customer_name:
                item["usage_count"] = item.get("usage_count", 0) + 1
                save_customer_list(CUSTOMER_LIST)
                break

    def _refresh_customers(self):
        global CUSTOMER_LIST
        keyword = self.search_text.get().strip().lower()

        for item in self.customer_tree.get_children():
            self.customer_tree.delete(item)

        sorted_customers = sorted(
            CUSTOMER_LIST,
            key=lambda x: x.get("usage_count", 0),
            reverse=True
        )

        for item in sorted_customers:
            zh = item.get("zh", "")
            en = item.get("en", "")
            if not keyword or keyword in zh.lower() or keyword in en.lower():
                self.customer_tree.insert("", tk.END, values=(zh, en))

    def _on_search(self, event=None):
        self._refresh_customers()

    def _on_search_enter(self, event=None):
        self._refresh_customers()
        children = self.customer_tree.get_children()
        if not children:
            messagebox.showwarning("提示", "未找到匹配的客户。")
            return
        first = children[0]
        self.customer_tree.selection_set(first)
        self.customer_tree.see(first)
        values = self.customer_tree.item(first)["values"]
        self.customer.set(values[0] if values else "")
        self.rename_folder()

    def _on_search_up_down(self, event=None):
        children = self.customer_tree.get_children()
        if not children:
            return

        selection = self.customer_tree.selection()
        if selection:
            current = selection[0]
            try:
                idx = children.index(current)
            except ValueError:
                idx = -1
        else:
            idx = -1

        if event.keysym == "Down":
            new_idx = min(idx + 1, len(children) - 1)
        else:
            new_idx = max(idx - 1, 0)

        new_item = children[new_idx]
        self.customer_tree.selection_set(new_item)
        self.customer_tree.see(new_item)
        values = self.customer_tree.item(new_item)["values"]
        self.customer.set(values[0] if values else "")

    def _on_customer_select(self, event=None):
        selection = self.customer_tree.selection()

        if not selection:
            return

        values = self.customer_tree.item(selection[0])["values"]
        zh = values[0] if values else ""
        self.customer.set(zh)

    def _add_customer(self):
        dialog = tk.Toplevel(self)
        dialog.title("添加客户")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="客户名称：").pack(anchor="w", padx=12, pady=(12, 4))

        name_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=name_var, font=("Microsoft YaHei UI", 10))
        entry.pack(fill="x", padx=12, pady=(0, 8))
        entry.focus_set()

        ttk.Label(dialog, text="客户英文名称：").pack(anchor="w", padx=12, pady=(0, 4))

        en_var = tk.StringVar()
        en_entry = ttk.Entry(dialog, textvariable=en_var, font=("Microsoft YaHei UI", 10))
        en_entry.pack(fill="x", padx=12, pady=(0, 12))

        def confirm():
            name = name_var.get().strip()
            en = en_var.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入客户名称。", parent=dialog)
                return
            if any(item.get("zh") == name for item in CUSTOMER_LIST):
                messagebox.showwarning("提示", "该客户已存在。", parent=dialog)
                return
            CUSTOMER_LIST.append({"zh": name, "en": en, "usage_count": 0})
            save_customer_list(CUSTOMER_LIST)
            self.search_text.set("")
            self._refresh_customers()
            for item in self.customer_tree.get_children():
                values = self.customer_tree.item(item)["values"]
                if values and values[0] == name:
                    self.customer_tree.selection_set(item)
                    self.customer_tree.see(item)
                    break
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm, width=8).pack(side="right", padx=12, pady=(0, 12))
        ttk.Button(dialog, text="取消", command=dialog.destroy, width=8).pack(side="right", padx=(0, 6), pady=(0, 12))

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.winfo_x() + (self.winfo_width() // 2) - (width // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

    def _edit_customer(self):
        selection = self.customer_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要编辑的客户。")
            return

        values = self.customer_tree.item(selection[0])["values"]
        old_zh = values[0] if values else ""
        old_en = values[1] if values and len(values) > 1 else ""
        old_item = next((item for item in CUSTOMER_LIST if item.get("zh") == old_zh), None)

        if old_item is None:
            return

        dialog = tk.Toplevel(self)
        dialog.title("编辑客户")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="客户名称：").pack(anchor="w", padx=12, pady=(12, 4))

        name_var = tk.StringVar(value=old_item.get("zh", ""))
        entry = ttk.Entry(dialog, textvariable=name_var, font=("Microsoft YaHei UI", 10))
        entry.pack(fill="x", padx=12, pady=(0, 8))
        entry.focus_set()
        entry.icursor(tk.END)

        ttk.Label(dialog, text="客户英文名称：").pack(anchor="w", padx=12, pady=(0, 4))

        en_var = tk.StringVar(value=old_item.get("en", ""))
        en_entry = ttk.Entry(dialog, textvariable=en_var, font=("Microsoft YaHei UI", 10))
        en_entry.pack(fill="x", padx=12, pady=(0, 12))

        def confirm():
            new_zh = name_var.get().strip()
            new_en = en_var.get().strip()
            if not new_zh:
                messagebox.showwarning("提示", "请输入客户名称。", parent=dialog)
                return
            if new_zh != old_item.get("zh") and any(
                item.get("zh") == new_zh for item in CUSTOMER_LIST
            ):
                messagebox.showwarning("提示", "该客户已存在。", parent=dialog)
                return
            old_item["zh"] = new_zh
            old_item["en"] = new_en
            if self.customer.get() == old_item.get("zh"):
                self.customer.set(new_zh)
            save_customer_list(CUSTOMER_LIST)
            self.search_text.set("")
            self._refresh_customers()
            for item in self.customer_tree.get_children():
                values = self.customer_tree.item(item)["values"]
                if values and values[0] == new_zh:
                    self.customer_tree.selection_set(item)
                    self.customer_tree.see(item)
                    break
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm, width=8).pack(side="right", padx=12, pady=(0, 12))
        ttk.Button(dialog, text="取消", command=dialog.destroy, width=8).pack(side="right", padx=(0, 6), pady=(0, 12))

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.winfo_x() + (self.winfo_width() // 2) - (width // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (height // 2)
        dialog.geometry(f"+{x}+{y}")

    def _delete_customer(self):
        selection = self.customer_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的客户。")
            return

        values = self.customer_tree.item(selection[0])["values"]
        name = values[0] if values else ""
        target_item = next((item for item in CUSTOMER_LIST if item.get("zh") == name), None)

        if target_item is None:
            return

        name = target_item.get("zh", "")
        if not messagebox.askyesno("确认删除", f"确定要删除客户「{name}」吗？"):
            return

        CUSTOMER_LIST.remove(target_item)
        if self.customer.get() == name:
            self.customer.set("")
        save_customer_list(CUSTOMER_LIST)
        self.search_text.set("")
        self._refresh_customers()

    def rename_folder(self):
        customer = self.customer.get().strip()

        if not customer:
            messagebox.showwarning(
                "提示",
                "请先选择客户。"
            )
            return

        cwd = os.path.dirname(os.path.abspath(__file__))
        BASE_FOLDER = "03 客户资料_Dữ liệu khách hàng"
        new_name = f"{BASE_FOLDER}_{customer}"
        new_path = os.path.join(cwd, new_name)

        if os.path.isdir(new_path):
            self.selected_folder.set(new_name)
            self.status.config(text=f"已选择：{new_name}")
            self._increment_usage(customer)
            return

        existing = None
        for entry in os.listdir(cwd):
            if entry.startswith(BASE_FOLDER) and os.path.isdir(os.path.join(cwd, entry)):
                existing = entry
                break

        if existing:
            old_path = os.path.join(cwd, existing)
            if os.path.normcase(old_path) == os.path.normcase(new_path):
                self.selected_folder.set(new_name)
                self.status.config(text=f"已选择：{new_name}")
                self._increment_usage(customer)
                return
            try:
                os.rename(old_path, new_path)
                self.selected_folder.set(new_name)
                self.status.config(text=f"修改成功：{new_name}")
                self._increment_usage(customer)
                return
            except Exception as e:
                messagebox.showerror(
                    "错误",
                    f"无法重命名文件夹：\n{e}"
                )
                return

        try:
            os.makedirs(new_path)
            self.selected_folder.set(new_name)
            self.status.config(text=f"创建成功：{new_name}")
            self._increment_usage(customer)
        except Exception as e:
            messagebox.showerror(
                "错误",
                f"无法创建文件夹：\n{e}"
            )


if __name__ == "__main__":
    app = CustomerSelector()
    app.mainloop()
