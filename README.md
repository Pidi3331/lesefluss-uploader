# Lesefluss Uploader

Simple Windows GUI to upload `.txt` books and tweak reading settings on a
[Lesefluss](https://github.com/sch-28/lesefluss) ESP32 RSVP reader — drag,
drop, done. Why? I do not own an Android device, so that was helpful. No command line needed.

![screenshot placeholder](https://github.com/Pidi3331/lesefluss-uploader/blob/main/Screenshot%20uploader.png)

## What it does

Drop a `.txt` file onto the window. The uploader will:

1. Auto-detect the ESP32 via its CH340 USB-UART chip.
2. Hard-reset the board and interrupt the running Lesefluss app.
3. Write the file as `book.txt` to the board's flash filesystem.
4. Reset reading position and set the book title from the filename.
5. Write `config_override.py` with the chosen reading settings:
   - **WPM** (words per minute, 100–800)
   - **Brightness** (0–100)
   - **Comma pause** multiplier (1.0–5.0)
   - **Period pause** multiplier (1.0–8.0)
6. Soft-reboot the board so the new book starts immediately.

You can also click **„Einstellungen übernehmen (ohne Buch)"** to change just
the reading settings without re-uploading a book.

## Requirements (target machine)

- Windows 10/11 64-bit
- CH340 USB-UART driver — usually installed automatically by Windows Update,
  otherwise grab it from [WCH](https://www.wch-ic.com/downloads/CH341SER_EXE.html)
- A Lesefluss-flashed ESP32 (see the
  [official build guide](https://lesefluss.app/docs?tab=esp32-build-guide))

Python is **not** required — everything is bundled into the EXE.

## Usage

1. Download `Lesefluss Uploader.exe` from the
   [latest release](../../releases/latest).
2. Plug in the ESP32 via USB.
3. Double-click the EXE. Windows SmartScreen may ask once — click
   *More info → Run anyway*.
4. Adjust WPM / brightness / pauses with the sliders.
5. Drag a `.txt` file into the drop zone (or click it to browse).
6. Wait until you see „Fertig!". The board reboots into the new book.

EPUBs are not supported — convert them to plain text with
[Calibre's `ebook-convert`](https://manual.calibre-ebook.com/generated/en/ebook-convert.html)
first.

## Build from source

```cmd
git clone https://github.com/Pidi3331/lesefluss-uploader
cd lesefluss-uploader
build.bat
```

The resulting EXE lands in `dist\Lesefluss Uploader.exe`.

`build.bat` creates a venv, installs the deps listed in `requirements.txt`
(`pyserial`, `tkinterdnd2`, `pyinstaller`), and packages everything into a
single-file windowed EXE. It also explicitly bundles Tcl/Tk data because
Python 3.13's standard installer has a broken Tcl lookup path that confuses
PyInstaller's auto-detection.

## How it works

The Lesefluss firmware stores books and config as plain files in the
MicroPython filesystem:

| File                | Purpose                                       |
| ------------------- | --------------------------------------------- |
| `book.txt`          | The current book's full text                  |
| `position.txt`      | Current reading position (word index)         |
| `book.title`        | Title shown on the title screen               |
| `config_override.py`| Optional overrides for `WPM`, `BRIGHTNESS`, … |

The uploader speaks the MicroPython raw-REPL protocol over the USB serial
port (no `mpremote` dependency) to write these files. The actual driving
code lives in [`raw_repl.py`](raw_repl.py); the GUI in
[`uploader.py`](uploader.py).

Because the Lesefluss app actively services BLE callbacks and ignores
single `Ctrl-C`s, the uploader hard-resets the board via DTR/RTS and spams
`Ctrl-C` for up to 20 s until `boot.py`'s `except KeyboardInterrupt:` clause
fires and drops back to the REPL.

## Limitations

- Windows only. Linux and macOS should work with minor tweaks
  (`pyserial` is cross-platform), but no build script is provided.
- Only the ST7789 hardware variant is tested. The defaults assume that
  variant; for the AMOLED build you may want a lower brightness default.
- The EXE is **not** code-signed, so SmartScreen warns on first run.

## Credits

- [Lesefluss](https://github.com/sch-28/lesefluss) by sch-28 — the actual
  RSVP reader firmware that does all the interesting work.
- This uploader is just a thin convenience wrapper around its existing
  file-based storage interface.

## License

AGPL-3.0 — see [LICENSE](LICENSE).
