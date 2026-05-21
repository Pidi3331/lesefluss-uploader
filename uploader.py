"""Lesefluss Uploader - GUI zum Drag&Drop einer .txt aufs ESP32-Board."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

from raw_repl import RawRepl, find_ch340_port, list_serial_ports


APP_TITLE = "Lesefluss Uploader"
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
DROP_BG = "#313244"
DROP_BG_HOVER = "#45475a"
OK_COL = "#a6e3a1"
ERR_COL = "#f38ba8"


# Defaults aus Lesefluss config.py (ST7789-Hardware)
DEFAULTS = {
    "WPM": 350,
    "BRIGHTNESS": 100,
    "DELAY_COMMA": 2.0,
    "DELAY_PERIOD": 3.0,
}

SETTING_SPECS = [
    # (key, label, min, max, step, is_float)
    ("WPM",          "Wörter/Minute",  100, 800, 10,  False),
    ("BRIGHTNESS",   "Helligkeit",       0, 100,  5,  False),
    ("DELAY_COMMA",  "Komma-Pause",    1.0, 5.0, 0.5, True),
    ("DELAY_PERIOD", "Punkt-Pause",    1.0, 8.0, 0.5, True),
]


class SettingRow:
    """Slider + Spinbox kombiniert, geteilte Variable."""

    def __init__(self, parent, key, label, vmin, vmax, step, is_float, default):
        self.key = key
        self.is_float = is_float
        self.var = tk.DoubleVar(value=default)

        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=24, pady=2)

        tk.Label(frame, text=label, font=("Segoe UI", 9),
                 fg=FG, bg=BG, width=14, anchor="w").pack(side="left")

        scale = ttk.Scale(
            frame, from_=vmin, to=vmax, orient="horizontal",
            variable=self.var, command=self._on_scale,
        )
        scale.pack(side="left", fill="x", expand=True, padx=(4, 8))

        self.spin = ttk.Spinbox(
            frame, from_=vmin, to=vmax, increment=step,
            width=6, textvariable=self.var,
            command=self._on_spin,
        )
        self.spin.pack(side="left")
        self.spin.bind("<Return>", lambda e: self._on_spin())
        self.spin.bind("<FocusOut>", lambda e: self._on_spin())

    def _on_scale(self, _val):
        # Auf Step runden
        v = self.var.get()
        if not self.is_float:
            self.var.set(int(round(v)))

    def _on_spin(self):
        try:
            self.var.get()
        except tk.TclError:
            self.var.set(DEFAULTS[self.key])

    def value(self):
        v = self.var.get()
        return v if self.is_float else int(round(v))


class UploaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("560x560")
        root.configure(bg=BG)
        root.resizable(False, False)

        tk.Label(
            root, text="Lesefluss Uploader",
            font=("Segoe UI", 18, "bold"), fg=ACCENT, bg=BG,
        ).pack(pady=(18, 2))

        tk.Label(
            root, text="Zieh eine .txt-Datei in das Feld unten",
            font=("Segoe UI", 9), fg=FG, bg=BG,
        ).pack()

        self.drop = tk.Label(
            root,
            text="\nDrop .txt hier\n\n(oder klicken zum Auswählen)\n",
            font=("Segoe UI", 11), fg=FG, bg=DROP_BG,
            relief="ridge", bd=2, cursor="hand2",
        )
        self.drop.pack(fill="x", padx=24, pady=(8, 12), ipady=8)
        self.drop.bind("<Button-1>", lambda e: self.pick_file())

        if DND_AVAILABLE:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

        # Settings-Bereich
        tk.Label(
            root, text="Einstellungen",
            font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=BG, anchor="w",
        ).pack(fill="x", padx=24, pady=(6, 2))

        self.rows: dict[str, SettingRow] = {}
        for key, label, vmin, vmax, step, is_float in SETTING_SPECS:
            self.rows[key] = SettingRow(
                root, key, label, vmin, vmax, step, is_float, DEFAULTS[key],
            )

        # Action-Buttons
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=(10, 6))
        self.apply_btn = ttk.Button(
            btn_frame, text="Einstellungen übernehmen (ohne Buch)",
            command=self.start_settings_only,
        )
        self.apply_btn.pack(side="left", padx=(0, 6))
        self.reset_btn = ttk.Button(
            btn_frame, text="Defaults", command=self.reset_defaults,
        )
        self.reset_btn.pack(side="left")

        # Status + Progress
        self.status = tk.Label(
            root, text="Bereit. Board per USB anschließen.",
            font=("Segoe UI", 9), fg=FG, bg=BG, wraplength=520, justify="left",
        )
        self.status.pack(pady=(8, 4), padx=24, anchor="w")

        self.progress = ttk.Progressbar(
            root, mode="determinate", length=510,
        )
        self.progress.pack(pady=(0, 12))

        self.busy = False

    # ---------- UI helpers ----------

    def set_status(self, text: str, color: str = FG) -> None:
        self.status.config(text=text, fg=color)

    def set_drop_color(self, color: str) -> None:
        self.drop.config(bg=color)

    def reset_defaults(self) -> None:
        for key, row in self.rows.items():
            row.var.set(DEFAULTS[key])

    def collect_settings(self) -> dict:
        return {k: row.value() for k, row in self.rows.items()}

    def config_override_source(self, settings: dict) -> str:
        lines = ["# auto-generated by Lesefluss Uploader"]
        for k, v in settings.items():
            lines.append(f"{k} = {v!r}")
        return "\n".join(lines) + "\n"

    # ---------- File handling ----------

    def pick_file(self) -> None:
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title="Buch wählen",
            filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.start_upload(path)

    def on_drop(self, event) -> None:
        if self.busy:
            return
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0].strip("{}")
        self.start_upload(path)

    # ---------- Actions ----------

    def start_upload(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            messagebox.showerror(APP_TITLE, f"Datei nicht gefunden:\n{path}")
            return
        if p.suffix.lower() != ".txt":
            if not messagebox.askyesno(
                APP_TITLE,
                f"Datei hat keine .txt-Endung ({p.suffix}).\nTrotzdem hochladen?",
            ):
                return

        self.busy = True
        self.set_drop_color(DROP_BG_HOVER)
        self.progress["value"] = 0
        threading.Thread(
            target=self._worker, args=(p, self.collect_settings()), daemon=True,
        ).start()

    def start_settings_only(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.set_drop_color(DROP_BG_HOVER)
        self.progress["value"] = 0
        threading.Thread(
            target=self._worker, args=(None, self.collect_settings()), daemon=True,
        ).start()

    # ---------- Worker ----------

    def _worker(self, p: Path | None, settings: dict) -> None:
        try:
            self.set_status("Suche ESP32 (CH340)...")
            port = find_ch340_port()
            if not port:
                ports = list_serial_ports()
                hint = f"\nVerfügbare Ports: {', '.join(ports) or 'keine'}"
                raise RuntimeError(
                    "Kein ESP32 (CH340) gefunden. Board per USB anschließen."
                    + hint
                )

            self.set_status(f"Verbinde mit {port}...")
            data = p.read_bytes() if p else None
            title = p.stem if p else None

            repl = RawRepl(port)
            try:
                self.set_status("Unterbreche Lesefluss-App (kann bis 20s dauern)...")
                repl.enter_raw()

                # Settings immer schreiben
                self.set_status("Schreibe Einstellungen...")
                override = self.config_override_source(settings).encode("utf-8")
                repl.write_file("config_override.py", override)

                if data is not None:
                    self.set_status(f"Übertrage {p.name} ({len(data)} Bytes)...")

                    def progress(sent: int, total: int) -> None:
                        pct = sent / total * 100
                        self.progress["value"] = pct
                        self.set_status(
                            f"Übertrage {p.name}: {sent}/{total} Bytes ({pct:.0f}%)"
                        )

                    repl.write_file("book.txt", data, progress=progress)

                    self.set_status("Setze Position und Titel...")
                    repl.exec("f=open('position.txt','w');f.write('0');f.close()")
                    title_bytes = title.encode("utf-8")
                    repl.exec(
                        "f=open('book.title','wb');f.write("
                        + repr(title_bytes) + ");f.close()"
                    )

                self.set_status("Starte Board neu...")
                repl.ser.write(b"\x02")
                time.sleep(0.1)
                repl.ser.write(b"\x04")
            finally:
                repl.close()

            if p:
                self.set_status(
                    f"Fertig! ‘{title}’ geladen, WPM={settings['WPM']}.",
                    color=OK_COL,
                )
            else:
                self.set_status(
                    f"Einstellungen übernommen (WPM={settings['WPM']}).",
                    color=OK_COL,
                )
            self.progress["value"] = 100
        except Exception as e:
            self.set_status(f"Fehler: {e}", color=ERR_COL)
            messagebox.showerror(APP_TITLE, str(e))
            self.progress["value"] = 0
        finally:
            self.busy = False
            self.set_drop_color(DROP_BG)


def main() -> None:
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        messagebox.showwarning(
            APP_TITLE,
            "tkinterdnd2 nicht installiert - Drag&Drop deaktiviert.\n"
            "Klick aufs Feld zum Datei-Wählen funktioniert weiterhin.",
        )
    UploaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
