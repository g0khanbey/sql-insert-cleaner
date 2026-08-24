from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from cleaner import CleanResult, clean_sql_file, scan_insert_tables


class SqlInsertCleanerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SQL Insert Cleaner GUI")
        self.root.geometry("760x560")
        self.root.minsize(680, 500)

        self.source_path: Path | None = None
        self.table_states: dict[str, bool] = {}

        self.file_var = tk.StringVar(value="Henüz SQL dosyası seçilmedi")
        self.status_var = tk.StringVar(value="Bir SQL dosyası seçerek başlayın.")
        self.progress_var = tk.IntVar(value=0)

        self.build_interface()

    def build_interface(self):
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="SQL Insert Cleaner",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            container,
            text="Tablo yapısını korur, seçtiğiniz tabloların INSERT INTO verilerini kaldırır.",
        ).pack(anchor="w", pady=(2, 16))

        file_frame = ttk.Frame(container)
        file_frame.pack(fill="x")

        self.choose_button = ttk.Button(
            file_frame,
            text="SQL Dosyası Seç",
            command=self.choose_file,
        )
        self.choose_button.pack(side="left")

        ttk.Label(file_frame, textvariable=self.file_var).pack(
            side="left",
            padx=12,
            fill="x",
            expand=True,
        )

        action_frame = ttk.Frame(container)
        action_frame.pack(fill="x", pady=(16, 8))

        self.select_all_button = ttk.Button(
            action_frame,
            text="Tümünü Seç",
            command=lambda: self.set_all_tables(True),
            state="disabled",
        )
        self.select_all_button.pack(side="left")

        self.select_none_button = ttk.Button(
            action_frame,
            text="Seçimi Kaldır",
            command=lambda: self.set_all_tables(False),
            state="disabled",
        )
        self.select_none_button.pack(side="left", padx=8)

        self.clean_button = ttk.Button(
            action_frame,
            text="Seçilen Verileri Temizle",
            command=self.start_cleaning,
            state="disabled",
        )
        self.clean_button.pack(side="right")

        table_frame = ttk.Frame(container)
        table_frame.pack(fill="both", expand=True)

        self.table_view = ttk.Treeview(
            table_frame,
            columns=("selected", "table", "count"),
            show="headings",
            height=13,
            selectmode="none",
        )
        self.table_view.heading("selected", text="Temizle")
        self.table_view.heading("table", text="Tablo")
        self.table_view.heading("count", text="INSERT sorgusu")
        self.table_view.column("selected", width=80, anchor="center", stretch=False)
        self.table_view.column("table", width=430, anchor="w")
        self.table_view.column("count", width=120, anchor="center", stretch=False)
        self.table_view.pack(side="left", fill="both", expand=True)
        self.table_view.bind("<Button-1>", self.toggle_table)

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.table_view.yview,
        )
        self.table_view.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.progress = ttk.Progressbar(
            container,
            variable=self.progress_var,
            maximum=100,
        )
        self.progress.pack(fill="x", pady=(14, 8))

        ttk.Label(container, textvariable=self.status_var).pack(anchor="w")

    def choose_file(self):
        selected = filedialog.askopenfilename(
            title="SQL dosyasını seç",
            filetypes=[("SQL dosyaları", "*.sql"), ("Tüm dosyalar", "*.*")],
        )
        if not selected:
            return

        self.source_path = Path(selected)
        self.file_var.set(str(self.source_path))
        self.clear_table_view()
        self.set_busy(True, "INSERT sorguları taranıyor...")
        threading.Thread(target=self.scan_worker, daemon=True).start()

    def scan_worker(self):
        try:
            tables = scan_insert_tables(self.source_path)
            self.root.after(0, self.finish_scan, tables)
        except Exception as error:
            self.root.after(0, self.show_error, str(error))

    def finish_scan(self, tables):
        self.table_states = {table: True for table in tables}

        for table, count in tables.items():
            self.table_view.insert("", "end", iid=table, values=("☑", table, count))

        self.set_busy(False)
        enabled = "normal" if tables else "disabled"
        self.select_all_button.configure(state=enabled)
        self.select_none_button.configure(state=enabled)
        self.clean_button.configure(state=enabled)

        total = sum(tables.values())
        if tables:
            self.status_var.set(
                f"{len(tables)} tabloda toplam {total} INSERT sorgusu bulundu."
            )
        else:
            self.status_var.set("Bu dosyada INSERT INTO sorgusu bulunamadı.")

    def toggle_table(self, event):
        if self.table_view.identify_region(event.x, event.y) != "cell":
            return
        if self.table_view.identify_column(event.x) != "#1":
            return

        item = self.table_view.identify_row(event.y)
        if not item:
            return

        self.table_states[item] = not self.table_states[item]
        values = list(self.table_view.item(item, "values"))
        values[0] = "☑" if self.table_states[item] else "☐"
        self.table_view.item(item, values=values)

    def set_all_tables(self, selected: bool):
        for table in self.table_states:
            self.table_states[table] = selected
            values = list(self.table_view.item(table, "values"))
            values[0] = "☑" if selected else "☐"
            self.table_view.item(table, values=values)

    def start_cleaning(self):
        selected_tables = {
            table for table, selected in self.table_states.items() if selected
        }
        if not selected_tables:
            messagebox.showwarning("Seçim gerekli", "En az bir tablo seçin.")
            return

        default_name = f"{self.source_path.stem}_temiz.sql"
        output = filedialog.asksaveasfilename(
            title="Temiz SQL dosyasını kaydet",
            initialdir=self.source_path.parent,
            initialfile=default_name,
            defaultextension=".sql",
            filetypes=[("SQL dosyaları", "*.sql")],
        )
        if not output:
            return

        output_path = Path(output)
        if output_path.resolve() == self.source_path.resolve():
            messagebox.showerror(
                "Güvenli kayıt",
                "Orijinal dosyanın üzerine yazılamaz. Farklı bir dosya adı seçin.",
            )
            return

        self.set_busy(True, "Seçilen INSERT sorguları temizleniyor...")
        threading.Thread(
            target=self.clean_worker,
            args=(output_path, selected_tables),
            daemon=True,
        ).start()

    def clean_worker(self, output_path: Path, selected_tables: set[str]):
        try:
            result = clean_sql_file(
                self.source_path,
                output_path,
                selected_tables,
                lambda value: self.root.after(0, self.progress_var.set, value),
            )
            self.root.after(0, self.finish_cleaning, result)
        except Exception as error:
            self.root.after(0, self.show_error, str(error))

    def finish_cleaning(self, result: CleanResult):
        self.set_busy(False)
        self.status_var.set(
            f"Tamamlandı: {result.removed_statements} INSERT sorgusu temizlendi."
        )
        details = "\n".join(
            f"{table}: {count}" for table, count in result.removed_by_table.items()
        )
        messagebox.showinfo(
            "Temizleme tamamlandı",
            f"{result.removed_statements} INSERT sorgusu kaldırıldı.\n\n"
            f"{details}\n\nÇıktı:\n{result.output_path}",
        )

    def clear_table_view(self):
        for item in self.table_view.get_children():
            self.table_view.delete(item)
        self.table_states.clear()

    def set_busy(self, busy: bool, status: str | None = None):
        state = "disabled" if busy else "normal"
        self.choose_button.configure(state=state)
        self.clean_button.configure(state="disabled" if busy else state)
        self.select_all_button.configure(state="disabled" if busy else state)
        self.select_none_button.configure(state="disabled" if busy else state)
        if status:
            self.status_var.set(status)
        if busy:
            self.progress_var.set(0)

    def show_error(self, error: str):
        self.set_busy(False)
        self.status_var.set("İşlem sırasında hata oluştu.")
        messagebox.showerror("Hata", error)


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    SqlInsertCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
