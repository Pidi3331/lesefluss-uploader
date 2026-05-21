"""Minimaler MicroPython Raw-REPL Client ueber pyserial.

Reicht aus, um eine Datei aufs Board zu schreiben und kleine
Python-Snippets auszufuehren - kein mpremote-Subprocess noetig.
"""

from __future__ import annotations

import time
import serial
from serial.tools import list_ports


CH340_VID = 0x1A86  # QinHeng Electronics (CH340 / CH341)


def find_ch340_port() -> str | None:
    """Sucht den ersten COM-Port mit CH340-USB-UART-Chip."""
    for p in list_ports.comports():
        if p.vid == CH340_VID:
            return p.device
    return None


def list_serial_ports() -> list[str]:
    return [p.device for p in list_ports.comports()]


class RawRepl:
    """Spricht das MicroPython Raw-REPL Protokoll."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 2.0):
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def close(self) -> None:
        try:
            # Zurueck zum normalen REPL, damit main.py wieder laeuft
            self.ser.write(b"\r\x02")  # Ctrl-B
            time.sleep(0.05)
        except Exception:
            pass
        self.ser.close()

    def _read_until(self, marker: bytes, timeout: float = 5.0) -> bytes:
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if marker in buf:
                    return buf
            else:
                time.sleep(0.01)
        raise TimeoutError(f"Marker {marker!r} nicht gefunden. Buffer: {buf!r}")

    def _hard_reset(self) -> None:
        """ESP32 via CH340 hard-reseten (DTR=EN, RTS=IO0)."""
        # EN low halten -> Chip resettet
        self.ser.dtr = False
        self.ser.rts = True
        time.sleep(0.1)
        # EN high -> Chip startet normal (kein Boot-Mode)
        self.ser.rts = False
        time.sleep(0.05)

    def enter_raw(self) -> None:
        # 1) Versuch ohne Reset: vielleicht ist Board schon in REPL
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\x03\x03")
        time.sleep(0.2)
        self.ser.write(b"\r\x01")
        try:
            self._read_until(b"raw REPL; CTRL-B to exit\r\n>", timeout=1.5)
            return
        except TimeoutError:
            pass

        # 2) Hard-Reset und Ctrl-C spammen, bis REPL-Prompt erscheint.
        # Lesefluss-boot.py faengt KeyboardInterrupt -> "Startup cancelled" -> REPL.
        # Da BLE-Init Ctrl-C kurzzeitig blockt, kann es bis ~15s dauern.
        self._hard_reset()
        time.sleep(0.3)  # USB-Wiederverbindung abwarten
        self.ser.reset_input_buffer()

        buf = b""
        deadline = time.time() + 20.0
        repl_ready = False
        while time.time() < deadline:
            self.ser.write(b"\r\x03")
            time.sleep(0.15)
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                # Erfolg: Boot.py hat unsere Interrupt eingefangen
                if b"Startup cancelled" in buf or b"KeyboardInterrupt" in buf:
                    repl_ready = True
                    break
                # Fallback: regulaerer REPL-Prompt sichtbar
                if buf.endswith(b">>> ") or buf.endswith(b">>>"):
                    repl_ready = True
                    break

        if not repl_ready:
            raise RuntimeError(
                "Board reagiert nicht auf Strg-C. "
                "Bitte USB-Kabel ab und wieder anstecken, dann nochmal versuchen.\n"
                f"Letzte Ausgabe: {buf[-200:]!r}"
            )

        # 3) Restausgabe drainen (BLE IRQ Callbacks koennen noch nachhallen)
        drain_deadline = time.time() + 1.0
        while time.time() < drain_deadline:
            extra = self.ser.read(self.ser.in_waiting)
            if extra:
                drain_deadline = time.time() + 0.3
            else:
                time.sleep(0.05)

        # 4) Raw-REPL aktivieren - mit Retries, falls Output dazwischenfunkt
        last_err = None
        for attempt in range(4):
            self.ser.reset_input_buffer()
            self.ser.write(b"\r\x03")  # nochmal Ctrl-C falls REPL beschaeftigt
            time.sleep(0.1)
            self.ser.write(b"\r\x01")
            try:
                self._read_until(b"raw REPL; CTRL-B to exit\r\n>", timeout=2.5)
                return
            except TimeoutError as e:
                last_err = e
                # Zurueck zu friendly REPL und nochmal probieren
                self.ser.write(b"\r\x02")
                time.sleep(0.3)
        raise RuntimeError(
            "Raw-REPL konnte nicht aktiviert werden "
            "(REPL beschaeftigt durch BLE-Callbacks). "
            "Bitte USB-Kabel ab und wieder anstecken."
        ) from last_err

    def exec(self, code: str, timeout: float = 10.0) -> str:
        self.ser.write(code.encode("utf-8") + b"\x04")
        # Antwort: OK<stdout>\x04<stderr>\x04>
        data = self._read_until(b"\x04>", timeout=timeout)
        if not data.startswith(b"OK"):
            raise RuntimeError(f"Raw-REPL Fehler: {data!r}")
        body = data[2:-2]  # strip OK ... \x04>
        try:
            stdout, stderr = body.split(b"\x04", 1)
        except ValueError:
            stdout, stderr = body, b""
        if stderr.strip():
            raise RuntimeError(stderr.decode("utf-8", "replace"))
        return stdout.decode("utf-8", "replace")

    def write_file(self, remote_path: str, data: bytes,
                   progress=None, chunk_size: int = 512) -> None:
        """Schreibt data nach remote_path auf dem Board."""
        # Datei oeffnen
        self.exec(f"f=open({remote_path!r},'wb')")
        total = len(data)
        sent = 0
        for i in range(0, total, chunk_size):
            chunk = data[i:i + chunk_size]
            # repr() erzeugt safe-bytes-Literal fuer alle Bytes
            self.exec("f.write(" + repr(chunk) + ")")
            sent += len(chunk)
            if progress:
                progress(sent, total)
        self.exec("f.close()")
