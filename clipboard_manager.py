#!/usr/bin/env python3
"""
Clipboard Manager — clean rewrite matching the reference UI.
"""

import sys, json, os, time, base64, csv, io, re, hashlib, shutil
from collections import OrderedDict
from pathlib import Path
from datetime import datetime

# ── Hide console on Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    import ctypes
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        # Uruchomiono przez python.exe (z konsolą) — restart przez pythonw.exe
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        if "pythonw" not in sys.executable.lower() and os.path.exists(pythonw):
            import subprocess
            subprocess.Popen([pythonw] + sys.argv, creationflags=0x08000000)
            sys.exit(0)
        else:
            ctypes.windll.user32.ShowWindow(hwnd, 0)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QLineEdit, QSystemTrayIcon, QMenu, QDialog,
    QMessageBox, QInputDialog, QFrame, QSizePolicy, QTextEdit, QSpinBox,
    QLayout, QCheckBox, QRadioButton, QButtonGroup, QGraphicsOpacityEffect,
    QAbstractButton,
)
# DODANO QMimeData DO IMPORTÓW PONIŻEJ
from PySide6.QtCore import Qt, QTimer, Signal, QByteArray, QEvent, QBuffer, QSize, QRect, QRectF, QPoint, QPointF, QMimeData, QUrl, QObject
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPixmap, QPainter, QImage,
    QGuiApplication, QKeySequence, QShortcut, QDrag,
    QMovie, QImageReader, QPolygonF,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

# ─── Config ───────────────────────────────────────────────────────────────────

APP_NAME    = "Clipboard Manager"
CONFIG_FILE = Path.home() / ".clipboard_manager_config.json"

# Dane: ~/.clipboard_manager/data.json (same metadane) + img/ i gif/ (pliki nazwane hashem zawartości)
DATA_DIR    = Path.home() / ".clipboard_manager"
DATA_FILE   = DATA_DIR / "data.json"
LEGACY_DATA_FILE = Path.home() / ".clipboard_manager_data.json"   # stary format (obrazy jako base64 w JSON)
MAX_GIF_BYTES = 20 * 1024 * 1024                         # większe GIFy zapisujemy tylko jako statyczny obraz

DEFAULT_CONFIG = {
    "hotkey":       "`",
    "layout_mode":  "panel",
    "panel_height": 560,
    "bar_height":   300,
    "panel_width":  820,
    "excel_dependent": False,
    "show_at_cursor": True,
    "new_card_position": "top",
    "cards_per_row": 0,          # 0 = automatycznie
}

# ─── Palette ──────────────────────────────────────────────────────────────────

C = {
    "bg":       "#13151f",
    "panel":    "#181c2a",
    "card":     "#1e2333",
    "card_h":   "#252d42",
    "sel":      "#2a3555",
    "acc":      "#7c5cfc",
    "acc_dim":  "#3d2e80",
    "acc_glow": "#a48cff",
    "pin":      "#f0a020",
    "danger":   "#e05060",
    "success":  "#2ecc71", 
    "t1":       "#e8eaf6",
    "t2":       "#9aa0b8",
    "t3":       "#525878",
    "border":   "#252d42",
    "border_a": "#3d2e80",
}

# ─── Strzałki do QSpinBox (generowane do plików PNG, bo QSS potrzebuje obrazków) ──
def _make_spin_arrows():
    from PySide6.QtGui import QImage, QPolygonF
    from PySide6.QtCore import QPointF
    d = Path.home() / ".clipboard_manager_icons"
    out = {}
    try:
        d.mkdir(exist_ok=True)
        for name, col in (("n", C["t2"]), ("h", C["t1"]), ("d", C["border"])):
            for direction in ("up", "down"):
                f = d / f"spin_{direction}_{name}.png"
                img = QImage(12, 8, QImage.Format_ARGB32); img.fill(0)
                pt = QPainter(img); pt.setRenderHint(QPainter.Antialiasing)
                pt.setPen(Qt.NoPen); pt.setBrush(QColor(col))
                if direction == "up": pts = [QPointF(2,6), QPointF(10,6), QPointF(6,2)]
                else:                 pts = [QPointF(2,2), QPointF(10,2), QPointF(6,6)]
                pt.drawPolygon(QPolygonF(pts)); pt.end()
                img.save(str(f), "PNG")
                out[f"{direction}_{name}"] = f.as_posix()
    except Exception:
        pass
    return out

_ARW = _make_spin_arrows()
def _arw(key): return f"url({_ARW[key]})" if key in _ARW else "none"

SS = f"""
* {{ font-family: 'Segoe UI', Ubuntu, sans-serif; font-size: 13px; color: {C['t1']}; }}
QWidget {{ background: transparent; }}

QWidget#Panel {{
    background: {C['panel']};
    border: 1px solid {C['border_a']};
    border-radius: 10px;
}}
QWidget#Toolbar {{
    background: {C['panel']};
    border-bottom: 1px solid {C['border']};
    border-radius: 10px 10px 0 0;
}}
QWidget#Body {{ background: {C['panel']}; }}

QLineEdit#Search {{
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 16px;
    padding: 4px 14px;
    color: {C['t1']};
    min-width: 150px;
}}
QLineEdit#Search:focus {{ border-color: {C['acc']}; }}

QPushButton#BtnNewCard {{
    background: rgba(124, 92, 252, 0.15);
    color: {C['acc_glow']};
    border: 1px solid rgba(124, 92, 252, 0.4);
    border-radius: 7px;
    padding: 5px 12px;
    font-weight: 600;
}}
QPushButton#BtnNewCard:hover {{ background: {C['acc']}; color: white; border-color: {C['acc']}; }}

QPushButton#BtnRemove {{
    background: {C['card']};
    color: {C['t2']};
    border: 1px solid {C['border']};
    border-radius: 7px;
    padding: 5px 10px;
}}
QPushButton#BtnRemove:hover {{ background: {C['danger']}; color: white; border-color: {C['danger']}; }}

QPushButton#BtnPause {{
    background: rgba(46, 204, 113, 0.15);
    color: {C['success']};
    border: 1px solid rgba(46, 204, 113, 0.4);
    border-radius: 7px;
    padding: 5px 12px;
}}
QPushButton#BtnPause:hover {{ background: rgba(46, 204, 113, 0.25); }}
QPushButton#BtnPause:checked {{
    background: rgba(224, 80, 96, 0.15);
    color: {C['danger']};
    border-color: rgba(224, 80, 96, 0.4);
}}
QPushButton#BtnPause:checked:hover {{ background: rgba(224, 80, 96, 0.25); }}

QPushButton#BtnIcon {{
    background: transparent; color: {C['t3']}; border: none;
    border-radius: 5px; padding: 4px 7px; font-size: 15px;
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
}}
QPushButton#BtnIcon:hover {{ background: {C['card_h']}; color: {C['t1']}; }}
QPushButton#BtnQuit {{ background: transparent; color: {C['t3']}; border: none;
    border-radius: 5px; padding: 4px 7px; font-size: 15px;
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; }}
QPushButton#BtnQuit:hover {{ background: {C['danger']}; color: white; }}

QPushButton#Tab {{
    background: transparent; color: {C['t2']}; border: none;
    border-bottom: 2px solid transparent;
    padding: 4px 14px 5px 14px; font-size: 13px;
    min-height: 28px;
}}
QPushButton#Tab:hover {{ color: {C['t1']}; background: {C['card_h']};
    border-radius: 6px 6px 0 0; }}
QPushButton#Tab[active="true"] {{
    color: {C['t1']}; border-bottom: 2px solid {C['acc']}; font-weight: 600;
}}
QPushButton#TabAdd {{
    background: transparent; color: {C['t3']};
    border: 1px solid {C['border']}; border-radius: 6px;
    padding: 1px 8px; font-size: 18px;
    min-height: 26px; max-height: 26px; min-width: 26px; max-width: 26px;
}}
QPushButton#TabAdd:hover {{ color: {C['acc_glow']}; border-color: {C['acc']}; background: {C['card']}; }}
QPushButton#TabClose {{
    background: transparent; color: {C['t3']}; border: none;
    border-radius: 4px; padding: 0 3px; font-size: 11px;
    min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;
}}
QPushButton#TabClose:hover {{ color: {C['danger']}; background: rgba(224,80,96,0.15); }}

QFrame#Card {{
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 8px;
}}
QFrame#CardPin {{
    background: {C['card']};
    border: 1px solid {C['border']};
    border-left: 3px solid {C['pin']};
    border-radius: 8px;
}}

QPushButton#CardBtn {{
    background: transparent; color: {C['t3']}; border: none;
    border-radius: 4px; padding: 2px 4px; font-size: 13px;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
}}
QPushButton#CardBtn:hover {{ background: {C['card_h']}; color: {C['t1']}; }}
QPushButton#CardBtnDel:hover {{ color: {C['danger']}; background: rgba(224,80,96,0.12); }}
QPushButton#CardBtnPin {{ color: {C['t3']}; }}
QPushButton#CardBtnPin[on="true"] {{ color: {C['pin']}; }}
QPushButton#CardBtnPin:hover {{ color: {C['pin']}; background: rgba(240,160,32,0.15); }}

QScrollArea {{ border: none; background: transparent; }}

/* --- Stylized Scrollbars --- */
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {C['t3']}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {C['acc']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: transparent; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollBar:horizontal {{
    background: transparent; height: 8px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {C['t3']}; border-radius: 4px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C['acc']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: transparent; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
/* -------------------------- */

QDialog {{
    background: {C['panel']};
    border: 1px solid {C['border_a']};
    border-radius: 10px;
}}
QTextEdit {{
    background: {C['card']}; border: 1px solid {C['border']};
    border-radius: 6px; padding: 6px; color: {C['t1']};
}}
QTextEdit:focus {{ border-color: {C['acc']}; }}
QLineEdit {{
    background: {C['card']}; border: 1px solid {C['border']};
    border-radius: 6px; padding: 5px 9px; color: {C['t1']};
}}
QLineEdit:focus {{ border-color: {C['acc']}; }}
QPushButton#DlgOk {{
    background: {C['acc']}; color: white; border: none;
    border-radius: 6px; padding: 6px 20px;
}}
QPushButton#DlgOk:hover {{ background: {C['acc_glow']}; color: {C['bg']}; }}
QPushButton#DlgCancel {{
    background: {C['card']}; color: {C['t2']};
    border: 1px solid {C['border']}; border-radius: 6px; padding: 6px 20px;
}}
QPushButton#DlgCancel:hover {{ background: {C['card_h']}; color: {C['t1']}; }}
QSpinBox {{
    background: {C['card']}; border: 1px solid {C['border']};
    border-radius: 6px; padding: 4px 8px; min-width: 80px; color: {C['t1']};
}}
QSpinBox:focus {{ border-color: {C['acc']}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {C['card_h']}; border: none; width: 16px; border-radius: 3px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {C['acc_dim']}; }}
QSpinBox::up-arrow   {{ image: {_arw('up_n')};   width: 10px; height: 7px; }}
QSpinBox::down-arrow {{ image: {_arw('down_n')}; width: 10px; height: 7px; }}
QSpinBox::up-arrow:hover   {{ image: {_arw('up_h')}; }}
QSpinBox::down-arrow:hover {{ image: {_arw('down_h')}; }}
QSpinBox:disabled {{ background: {C['panel']}; color: {C['t3']}; border-color: {C['border']}; }}
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {{ background: transparent; }}
QSpinBox::up-arrow:disabled   {{ image: {_arw('up_d')}; }}
QSpinBox::down-arrow:disabled {{ image: {_arw('down_d')}; }}
QPushButton#ModeBtn {{
    background: {C['card']}; color: {C['t2']};
    border: 1px solid {C['border']}; border-radius: 7px;
    padding: 8px 14px; font-size: 12px;
}}
QPushButton#ModeBtn:checked {{
    background: {C['acc_dim']}; color: {C['acc_glow']}; border-color: {C['acc']};
}}
QPushButton#ModeBtn:hover:!checked {{ background: {C['card_h']}; color: {C['t1']}; }}
QMenu {{
    background: {C['panel']}; border: 1px solid {C['border_a']};
    border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['card_h']}; color: {C['acc_glow']}; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 8px; }}

QCheckBox {{
    color: {C['t1']};
    spacing: 8px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 4px;
}}
QCheckBox::indicator:hover {{
    border-color: {C['acc']};
}}
QCheckBox::indicator:checked {{
    background: {C['acc']};
    border-color: {C['acc']};
}}
QCheckBox::indicator:checked:hover {{
    background: {C['acc_glow']};
    border-color: {C['acc_glow']};
}}
QRadioButton {{
    color: {C['t1']};
    spacing: 8px;
    font-size: 13px;
}}
QRadioButton::indicator {{
    width: 16px; height: 16px;
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 9px;
}}
QRadioButton::indicator:hover {{
    border-color: {C['acc']};
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 {C['acc']}, stop:0.45 {C['acc']},
                stop:0.55 {C['card']}, stop:1 {C['card']});
    border-color: {C['acc']};
}}
"""

# ─── Excel clipboard cleaner ─────────────────────────────────────────────────

def _excel_clean(text: str) -> str:
    """
    Usuwa cudzysłowy dodawane przez Excela do komórek zawierających nowe linie.

    Excel koduje skopiowany zakres jako TSV (tabulatory między kolumnami,
    nowe linie między wierszami). Komórki zawierające znak nowej linii lub
    tabulatora są dodatkowo opakowane w cudzysłowy, a wewnętrzne cudzysłowy
    są podwajane (""). Przykład dla jednej komórki z nową linią:
        "linia 1\nlinia 2"
    Dla zakresu:
        "kom A1\nnowa linia"\tkom B1\n"kom A2\nnowa"\tkom B2

    Strategia:
    1. Spróbuj sparsować jako TSV przez csv.reader (obsługuje RFC-4180).
    2. Jeśli jest tylko jedna komórka — zwróć jej wartość (cudzysłowy znikają).
    3. Jeśli jest wiele komórek — złóż z powrotem tabulatorami i nowym liniami,
       ale już bez zewnętrznych cudzysłowów wokół każdej komórki.
    4. Fallback: jeśli csv.reader zawiedzie, użyj starego strip('"').
    """
    try:
        reader = csv.reader(io.StringIO(text), delimiter='\t', quotechar='"',
                            quoting=csv.QUOTE_MINIMAL, skipinitialspace=False)
        rows = list(reader)
        # Odrzuć ostatni pusty wiersz który csv dodaje gdy tekst kończy się \n
        if rows and rows[-1] == []:
            rows = rows[:-1]
        if not rows:
            return text.strip('"')
        if len(rows) == 1 and len(rows[0]) == 1:
            # Pojedyncza komórka
            return rows[0][0]
        # Wiele komórek — złóż z powrotem jako TSV bez cudzysłowów
        return "\n".join("\t".join(cell for cell in row) for row in rows)
    except Exception:
        # Fallback — stare zachowanie
        return text.strip('"')


# ─── GIF helpers ─────────────────────────────────────────────────────────────

def _gif_frame_count(data: bytes) -> int:
    """Liczba klatek GIFa (>1 = animowany)."""
    try:
        ba = QByteArray(data); buf = QBuffer(ba); buf.open(QBuffer.ReadOnly)
        return QImageReader(buf, QByteArray(b"gif")).imageCount()
    except Exception:
        return 0

def _is_animated_gif(data: bytes) -> bool:
    return (data[:4] == b"GIF8" and len(data) <= MAX_GIF_BYTES
            and _gif_frame_count(data) > 1)

def _gif_from_mime(mime) -> bytes | None:
    """Szuka surowych bajtów GIFa w schowku (image/gif albo format Windows 'GIF')."""
    for fmt in mime.formats():
        if "gif" in fmt.lower():
            data = bytes(mime.data(fmt))
            if data[:4] == b"GIF8":
                return data
    return None

def _gif_src_from_html(html: str) -> str | None:
    """Jeśli schowek zawiera <img src=...gif> (kopiowanie z przeglądarki), zwraca src."""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if not m: return None
    src = m.group(1).replace("&amp;", "&")
    low = src.lower()
    if low.startswith("data:image/gif"): return src
    if re.match(r"https?://", low) and ".gif" in low: return src
    return None

# ─── Media storage (img/ i gif/) ─────────────────────────────────────────────

def _media_dir(ctype: str) -> Path:
    return DATA_DIR / ("gif" if ctype == "gif" else "img")

def _store_media(ctype: str, data: bytes) -> str:
    """Zapisuje bajty jako <sha1>.png / <sha1>.gif i zwraca nazwę pliku.
    Nazwa = hash zawartości, więc identyczne obrazy współdzielą jeden plik."""
    name = hashlib.sha1(data).hexdigest() + (".gif" if ctype == "gif" else ".png")
    p = _media_dir(ctype) / name
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)            # atomowo — nie zostanie połowicznie zapisany plik
    return name

# Cache przeskalowanych podglądów (plik, szerokość) → QPixmap; dekodowanie oryginału tylko raz.
_PIX_CACHE: "OrderedDict[tuple, QPixmap]" = OrderedDict()
_PIX_CACHE_MAX = 64

def _scaled_pixmap(item, tw: int):
    key = (item.file or id(item), tw)
    pm = _PIX_CACHE.get(key)
    if pm is not None:
        _PIX_CACHE.move_to_end(key)
        return pm
    img = QImage.fromData(QByteArray(item.raw()))
    if img.isNull():
        return None
    pm = QPixmap.fromImage(img.scaledToWidth(tw, Qt.SmoothTransformation))
    _PIX_CACHE[key] = pm
    while len(_PIX_CACHE) > _PIX_CACHE_MAX:
        _PIX_CACHE.popitem(last=False)
    return pm


# ─── Data model ───────────────────────────────────────────────────────────────

class ClipItem:
    def __init__(self, ctype="text", text="", img_b64="",
                 ts=None, pinned=False, label="", file=""):
        self.ctype   = ctype
        self.text    = text
        self.img_b64 = img_b64     # tylko fallback (stary format / nieudany zapis pliku)
        self.file    = file        # nazwa pliku w img/ lub gif/
        self.ts      = ts or time.time()
        self.pinned  = pinned
        self.label   = label

    @classmethod
    def media(cls, ctype, data: bytes):
        """Tworzy kartę obrazu/GIFa i zapisuje bajty do pliku (przy błędzie dysku — fallback do base64)."""
        try:
            return cls(ctype, file=_store_media(ctype, data))
        except OSError as e:
            print("media:", e)
            return cls(ctype, img_b64=base64.b64encode(data).decode())

    def key(self):
        """Klucz do wykrywania duplikatów obrazów."""
        return self.file or self.img_b64

    def path(self) -> Path:
        return _media_dir(self.ctype) / self.file

    def raw(self) -> bytes:
        """Surowe bajty obrazu/GIFa (z pliku, a w razie braku — z base64)."""
        if self.file:
            try: return self.path().read_bytes()
            except OSError: return b""
        if self.img_b64:
            try: return base64.b64decode(self.img_b64)
            except Exception: return b""
        return b""

    def display(self):
        if self.label: return self.label
        if self.ctype == "text": return self.text[:200].replace("\n", " ")
        if self.ctype == "gif": return "[GIF]"
        return "[Image]"

    def to_dict(self):
        d = dict(ctype=self.ctype, text=self.text, ts=self.ts,
                 pinned=self.pinned, label=self.label)
        if self.file:          d["file"] = self.file
        elif self.img_b64:     d["img_b64"] = self.img_b64
        return d

    @classmethod
    def from_dict(cls, d):
        it = cls(d.get("ctype","text"), d.get("text",""), d.get("img_b64",""),
                 d.get("ts", time.time()), d.get("pinned",False), d.get("label",""),
                 d.get("file",""))
        if it.img_b64 and not it.file:           # migracja ze starego formatu (base64 w JSON)
            try:
                it.file = _store_media(it.ctype, base64.b64decode(it.img_b64))
                it.img_b64 = ""
            except Exception as e:
                print("migrate:", e)               # zostaje base64 jako fallback
        return it


# ─── Flow layout (wrapping grid) ─────────────────────────────────────────────

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=10, h_sp=8, v_sp=8):
        super().__init__(parent)
        self._items = []
        self._h = h_sp; self._v = v_sp
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):          self._items.append(item)
    def count(self):                  return len(self._items)
    def itemAt(self, i):              return self._items[i] if 0 <= i < len(self._items) else None
    def takeAt(self, i):              return self._items.pop(i) if 0 <= i < len(self._items) else None
    def hasHeightForWidth(self):      return True
    def heightForWidth(self, w):      return self._layout(QRect(0,0,w,0), dry=True)
    def sizeHint(self):               return self.minimumSize()
    def minimumSize(self):
        s = QSize()
        for it in self._items: s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left()+m.right(), m.top()+m.bottom())

    def setGeometry(self, rect):
        super().setGeometry(rect); self._layout(rect)

    def _layout(self, rect, dry=False):
        m   = self.contentsMargins()
        x0  = rect.x() + m.left()
        y   = rect.y() + m.top()
        avail = rect.width() - m.left() - m.right()
        # Ile kolumn: ustawione ręcznie albo wyliczone z preferowanej szerokości karty.
        auto_cols = max(1, (avail + self._h) // (CARD_W + self._h))
        max_cols  = max(1, (avail + self._h) // (CARD_MIN_W + self._h))   # nie zmniejszaj kart poniżej minimum
        cols = min(CARDS_PER_ROW, max_cols) if CARDS_PER_ROW > 0 else auto_cols
        cw   = (avail - (cols - 1) * self._h) // cols if avail > 0 else CARD_W
        cw   = max(CARD_MIN_W, cw)
        x, col, rh = x0, 0, 0
        for it in self._items:
            w = it.widget()
            if w is None: continue
            if col >= cols:
                col = 0; x = x0; y += rh + self._v; rh = 0
            if hasattr(w, "set_card_width"):
                w.set_card_width(cw)          # skaluje kartę i zawartość (też obrazek)
            ih = it.sizeHint().height()
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), QSize(cw, ih)))
            x += cw + self._h; col += 1; rh = max(rh, ih)
        return y + rh - rect.y() + m.bottom()

    def clear(self):
        while self._items:
            it = self._items.pop()
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()


# ─── Przewijanie: przeciąganie myszą (jak ekran dotykowy) + strzałki po bokach ──

class KineticPan(QObject):
    """Przewijanie „jak na ekranie dotykowym”: łapiesz zawartość myszą i przeciągasz,
    a po puszczeniu przewija się jeszcze chwilę z bezwładnością.
    Widżety tylko zgłaszają press() / move() / release() — reszta dzieje się tutaj."""

    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self._start = None            # punkt (globalny) naciśnięcia
        self._last = None             # ostatni punkt (globalny)
        self._active = False          # True, gdy przekroczono próg i faktycznie przewijamy
        self._vx = self._vy = 0.0     # prędkość w px/s (do bezwładności)
        self._rx = self._ry = 0.0     # ułamkowe pozostałości pikseli
        self._t = 0.0
        self._cursor_set = False
        self._timer = QTimer(self); self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def press(self, gp):
        self._timer.stop()
        self._start = QPoint(gp); self._last = QPoint(gp)
        self._active = False
        self._vx = self._vy = 0.0
        self._t = time.monotonic()

    def move(self, gp):
        """True = trwa przeciąganie (zdarzenie trzeba „połknąć”, żeby nie było kliknięcia)."""
        if self._start is None:
            return False
        if not self._active:
            if (gp - self._start).manhattanLength() < QApplication.startDragDistance():
                return False
            self._active = True
            self._last = QPoint(gp); self._t = time.monotonic()
            QApplication.setOverrideCursor(Qt.ClosedHandCursor); self._cursor_set = True
            return True
        now = time.monotonic()
        dt = max(now - self._t, 1e-3)
        dx = gp.x() - self._last.x(); dy = gp.y() - self._last.y()
        self._scroll_by(-dx, -dy)
        a = 0.35                                   # wygładzona prędkość
        self._vx = (1 - a) * self._vx + a * (-dx / dt)
        self._vy = (1 - a) * self._vy + a * (-dy / dt)
        self._last = QPoint(gp); self._t = now
        return True

    def release(self):
        """True = to było przeciąganie (a nie zwykłe kliknięcie)."""
        was = self._active
        self._start = None; self._active = False
        self._restore_cursor()
        if was and time.monotonic() - self._t < 0.08 and (abs(self._vx) > 60 or abs(self._vy) > 60):
            self._timer.start()                    # „rzut” — bezwładność
        return was

    def cancel(self):
        self._timer.stop()
        self._start = None; self._active = False
        self._restore_cursor()

    def _restore_cursor(self):
        if self._cursor_set:
            QApplication.restoreOverrideCursor(); self._cursor_set = False

    def _scroll_by(self, dx, dy):
        hb, vb = self.area.horizontalScrollBar(), self.area.verticalScrollBar()
        before = (hb.value(), vb.value())
        self._rx += dx; self._ry += dy
        ix, iy = int(self._rx), int(self._ry)
        self._rx -= ix; self._ry -= iy
        if ix: hb.setValue(hb.value() + ix)
        if iy: vb.setValue(vb.value() + iy)
        return before != (hb.value(), vb.value())

    def _tick(self):
        moved = self._scroll_by(self._vx * 0.016, self._vy * 0.016)
        self._vx *= 0.93; self._vy *= 0.93         # tarcie
        speed = max(abs(self._vx), abs(self._vy))
        if speed < 20 or (not moved and speed > 70):      # wyhamowało albo dobiło do końca listy
            self._timer.stop()


class ArrowButton(QAbstractButton):
    """Przycisk-strzałka rysowany ręcznie (bez czcionek/emoji).
    Kliknięcie = skok o pół „strony”, przytrzymanie = płynne, ciągłe przewijanie."""

    def __init__(self, direction, bar, size=26, parent=None):
        super().__init__(parent)
        self._dir = direction                      # "up" | "down" | "left" | "right"
        self._bar = bar
        self._sign = -1 if direction in ("up", "left") else 1
        self._size = size
        self._held = False; self._t0 = 0.0; self._target = 0
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip({"up": "Przewiń w górę", "down": "Przewiń w dół",
                         "left": "Przewiń w lewo", "right": "Przewiń w prawo"}[direction])
        self._timer = QTimer(self); self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.pressed.connect(self._on_press)
        self.released.connect(self._on_release)

    def _clamp(self, v):
        return max(self._bar.minimum(), min(self._bar.maximum(), v))

    def _on_press(self):
        step = max(120, int(self._bar.pageStep() * 0.5))
        self._target = self._clamp(self._bar.value() + self._sign * step)
        self._held = True; self._t0 = time.monotonic()
        self._timer.start()

    def _on_release(self):
        self._held = False                         # animacja dochodzi do celu i sama się zatrzyma

    def _tick(self):
        bar = self._bar
        self._held = self._held and self.isDown()
        if self._held and time.monotonic() - self._t0 > 0.35:
            self._target = self._clamp(self._target + self._sign * 20)   # przytrzymanie → ciągły ruch
        d = self._target - bar.value()
        if d == 0:
            if not self._held: self._timer.stop()
            return
        step = int(d * 0.35)
        if step == 0: step = 1 if d > 0 else -1
        bar.setValue(bar.value() + step)

    def hideEvent(self, e):
        self._timer.stop(); self._held = False
        super().hideEvent(e)

    def enterEvent(self, e):
        self.update(); super().enterEvent(e)

    def leaveEvent(self, e):
        self.update(); super().leaveEvent(e)

    def sizeHint(self):
        return QSize(self._size, self._size)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            bg, fg, bd = QColor(C['card']), QColor(C['t3']), QColor(C['border'])
            bg.setAlpha(110); fg.setAlpha(110)
        elif self.isDown():
            bg, fg, bd = QColor(C['acc']), QColor("white"), QColor(C['acc'])
        elif self.underMouse():
            bg, fg, bd = QColor(C['card_h']), QColor(C['acc_glow']), QColor(C['acc'])
        else:
            bg, fg, bd = QColor(C['card']), QColor(C['t2']), QColor(C['border'])
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(bd); p.setBrush(bg); p.drawRoundedRect(r, 7, 7)
        cx, cy = r.center().x(), r.center().y()
        k = min(r.width(), r.height()) * 0.17
        pts = {
            "up":    [(-1.4*k,  .8*k), (1.4*k,  .8*k), (0, -.9*k)],
            "down":  [(-1.4*k, -.8*k), (1.4*k, -.8*k), (0,  .9*k)],
            "left":  [( .8*k, -1.4*k), ( .8*k, 1.4*k), (-.9*k, 0)],
            "right": [(-.8*k, -1.4*k), (-.8*k, 1.4*k), ( .9*k, 0)],
        }[self._dir]
        p.setPen(Qt.NoPen); p.setBrush(fg)
        p.drawPolygon(QPolygonF([QPointF(cx + x, cy + y) for x, y in pts]))


class _WheelScrollArea(QScrollArea):
    """QScrollArea, w którym kółko myszy przewija poziomo, gdy nie ma przewijania pionowego."""
    def wheelEvent(self, e):
        vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        if vb.maximum() == 0 and hb.maximum() > 0:
            d = e.angleDelta().y() or e.angleDelta().x()
            hb.setValue(hb.value() - d)
            e.accept(); return
        super().wheelEvent(e)


class ArrowScrollArea(QWidget):
    """Obszar przewijany ze strzałkami po bokach (pokazują się tylko, gdy zawartość się nie mieści).
       orient="v": kolumna ▲ (góra) / ▼ (dół) po prawej stronie
       orient="h": ◀ po lewej i ▶ po prawej stronie
    Obiekt .pan (KineticPan) pozwala przewijać przeciąganiem myszą."""

    def __init__(self, orient="v", parent=None):
        super().__init__(parent)
        self.orient = orient
        self.area = _WheelScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.pan = KineticPan(self.area)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        if orient == "v":
            self._bar = self.area.verticalScrollBar()
            self._a = ArrowButton("up",   self._bar, 26)
            self._b = ArrowButton("down", self._bar, 26)
            self._side = QWidget(); self._side.setFixedWidth(32)
            sl = QVBoxLayout(self._side); sl.setContentsMargins(0, 8, 6, 8); sl.setSpacing(0)
            sl.addWidget(self._a); sl.addStretch(); sl.addWidget(self._b)
            lay.addWidget(self.area, 1); lay.addWidget(self._side)
        else:
            self._bar = self.area.horizontalScrollBar()
            self._a = ArrowButton("left",  self._bar, 22)
            self._b = ArrowButton("right", self._bar, 22)
            self._side = None
            lay.addSpacing(2)
            lay.addWidget(self._a, 0, Qt.AlignVCenter)
            lay.addWidget(self.area, 1)
            lay.addWidget(self._b, 0, Qt.AlignVCenter)
        # Odświeżanie stanu strzałek (scalane w jedno wywołanie, żeby nie zapętlać layoutu)
        self._sync_timer = QTimer(self); self._sync_timer.setSingleShot(True); self._sync_timer.setInterval(0)
        self._sync_timer.timeout.connect(self._sync)
        self._bar.rangeChanged.connect(lambda *_: self._sync_timer.start())
        self._bar.valueChanged.connect(lambda *_: self._sync_timer.start())
        self._sync()

    def _sync(self):
        bar = self._bar
        over = bar.maximum() > bar.minimum()
        if self._side is not None:
            if self._side.isVisible() != over: self._side.setVisible(over)
        else:
            self._a.setVisible(over); self._b.setVisible(over)
        self._a.setEnabled(bar.value() > bar.minimum())
        self._b.setEnabled(bar.value() < bar.maximum())


# ─── Dialogs ──────────────────────────────────────────────────────────────────

class EditDialog(QDialog):
    def __init__(self, item: ClipItem, parent=None, create_mode=False):
        super().__init__(parent)
        self.item = item
        self.create_mode = create_mode
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumWidth(420); self.setStyleSheet(SS)
        lay = QVBoxLayout(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(10)
        t = QLabel("New Card" if create_mode else "Edit Clip")
        t.setStyleSheet(f"font-size:15px;font-weight:600;")
        lay.addWidget(t)
        lay.addWidget(self._lbl("Name:" if create_mode else "Label (optional):"))
        self.lbl_e = QLineEdit(item.label)
        self.lbl_e.setPlaceholderText("Card name…" if create_mode else "Custom name…")
        lay.addWidget(self.lbl_e)
        if create_mode or item.ctype == "text":
            lay.addWidget(self._lbl("Content:"))
            self.txt = QTextEdit()
            self.txt.setPlainText(item.text)
            self.txt.setMinimumHeight(110)
            lay.addWidget(self.txt)
        else:
            lay.addWidget(self._lbl("[Image — not editable]")); self.txt = None
        row = QHBoxLayout(); row.addStretch()
        c = QPushButton("Cancel"); c.setObjectName("DlgCancel"); c.clicked.connect(self.reject)
        s = QPushButton("Add" if create_mode else "Save"); s.setObjectName("DlgOk"); s.clicked.connect(self._save)
        row.addWidget(c); row.addWidget(s); lay.addLayout(row)

    def _lbl(self, t):
        l = QLabel(t); l.setStyleSheet(f"color:{C['t2']};font-size:12px"); return l

    def _save(self):
        self.item.label = self.lbl_e.text().strip()
        if self.txt and (self.create_mode or self.item.ctype == "text"):
            self.item.text = self.txt.toPlainText()
        if self.create_mode and not self.item.label and not self.item.text.strip():
            # Nie pozwalamy dodać zupełnie pustej karty
            self.lbl_e.setFocus()
            return
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg.copy()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumWidth(400); self.setStyleSheet(SS)
        # Zewnętrzny układ: przewijana zawartość + stały pasek przycisków na dole,
        # dzięki temu okno nigdy nie jest wyższe niż ekran.
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("SettingsBody")
        body.setStyleSheet("#SettingsBody{background:transparent;}")
        self._scroll.setWidget(body)
        outer.addWidget(self._scroll, 1)
        lay = QVBoxLayout(body); lay.setContentsMargins(20,20,20,10); lay.setSpacing(14)

        t = QLabel("⚙  Settings"); t.setStyleSheet("font-size:15px;font-weight:600;")
        lay.addWidget(t)

        r = QHBoxLayout(); r.addWidget(self._lbl("Toggle Hotkey:")); r.addStretch()
        self.hotkey = QLineEdit(cfg.get("hotkey","`"))
        self.hotkey.setMaxLength(10); self.hotkey.setFixedWidth(80)
        r.addWidget(self.hotkey); lay.addLayout(r)
        lay.addWidget(self._note("Single key or name/combination: \n`\nF1\nCtrl + `  \netc…"))
        lay.addWidget(self._sep())

        lay.addWidget(self._lbl("Layout Mode:"))
        mr = QHBoxLayout(); mr.setSpacing(8)
        cur = cfg.get("layout_mode","panel")
        self.btn_panel = QPushButton("🪟  Floating Panel"); self.btn_panel.setObjectName("ModeBtn"); self.btn_panel.setCheckable(True)
        self.btn_bar   = QPushButton("▬  Bottom Bar");      self.btn_bar.setObjectName("ModeBtn");   self.btn_bar.setCheckable(True)
        self.btn_panel.setChecked(cur=="panel"); self.btn_bar.setChecked(cur=="bar")
        self.btn_panel.clicked.connect(lambda: (self.btn_panel.setChecked(True),  self.btn_bar.setChecked(False)))
        self.btn_bar.clicked.connect(  lambda: (self.btn_bar.setChecked(True),    self.btn_panel.setChecked(False)))
        mr.addWidget(self.btn_panel); mr.addWidget(self.btn_bar); lay.addLayout(mr)
        lay.addWidget(self._note("Bottom Bar spans full width, anchored to the bottom edge."))
        lay.addWidget(self._sep())

        self.cb_cursor = QCheckBox("Show panel at mouse cursor position")
        self.cb_cursor.setChecked(cfg.get("show_at_cursor", True))
        lay.addWidget(self.cb_cursor)
        lay.addWidget(self._note("When enabled, the panel appears where your cursor is. When disabled, opens in the bottom-right corner."))
        lay.addWidget(self._sep())

        lay.addWidget(self._lbl("New cards position:"))
        self.rb_top = QRadioButton("At the top (within its category — pinned / unpinned)")
        self.rb_bottom = QRadioButton("At the bottom (within its category — pinned / unpinned)")
        self._pos_group = QButtonGroup(self)
        self._pos_group.addButton(self.rb_top); self._pos_group.addButton(self.rb_bottom)
        (self.rb_bottom if cfg.get("new_card_position", "top") == "bottom" else self.rb_top).setChecked(True)
        lay.addWidget(self.rb_top); lay.addWidget(self.rb_bottom)
        lay.addWidget(self._note("Where newly copied or created cards are placed. Pinned cards always stay above unpinned ones."))
        lay.addWidget(self._sep())

        self.cb_excel_dep = QCheckBox("Excel mode depends from 'works' mode")
        self.cb_excel_dep.setChecked(cfg.get("excel_dependent", False))
        lay.addWidget(self.cb_excel_dep)
        lay.addWidget(self._note("Check if Excel mode should be paused when clipboard listening is paused. Uncheck (default) for cleanup to always run."))
        lay.addWidget(self._sep())

        lay.addWidget(self._lbl("Cards per row:"))
        cr = QHBoxLayout(); cr.setSpacing(12)
        cpr = int(cfg.get("cards_per_row", 0) or 0)
        self.spin_cpr = QSpinBox(); self.spin_cpr.setRange(1, 12); self.spin_cpr.setSingleStep(1)
        self.spin_cpr.setValue(cpr if cpr > 0 else 4)
        self.cb_cpr_auto = QCheckBox("Auto")
        self.cb_cpr_auto.setChecked(cpr <= 0)
        self.spin_cpr.setEnabled(cpr > 0)
        self.cb_cpr_auto.toggled.connect(lambda on: self.spin_cpr.setEnabled(not on))
        cr.addWidget(self.spin_cpr); cr.addWidget(self.cb_cpr_auto); cr.addStretch(); lay.addLayout(cr)
        lay.addWidget(self._note("Auto = as many cards as fit (cards stretch to fill the row). "
                                 "A number fixes how many cards are in each row — cards scale to fit the window width."))
        lay.addWidget(self._sep())

        lay.addWidget(self._lbl("Size (px):"))
        hr = QHBoxLayout(); hr.setSpacing(16)
        for attr, label, lo, hi, val in [
            ("spin_ph", "Panel height", 300, 1400, cfg.get("panel_height",560)),
            ("spin_pw", "Panel width",  400, 1800, cfg.get("panel_width", 820)),
            ("spin_bh", "Bar height",   160,  600, cfg.get("bar_height",  300)),
        ]:
            col = QVBoxLayout(); col.addWidget(self._note(label))
            sp = QSpinBox(); sp.setRange(lo, hi); sp.setSingleStep(20); sp.setValue(val)
            setattr(self, attr, sp); col.addWidget(sp); hr.addLayout(col)
        hr.addStretch(); lay.addLayout(hr)

        lay.addStretch()
        row2 = QHBoxLayout(); row2.setContentsMargins(20,10,20,16); row2.addStretch()
        c = QPushButton("Cancel"); c.setObjectName("DlgCancel"); c.clicked.connect(self.reject)
        s = QPushButton("Apply");  s.setObjectName("DlgOk");    s.clicked.connect(self._save)
        row2.addWidget(c); row2.addWidget(s); outer.addLayout(row2)
        self._body = body

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_to_screen()

    def _fit_to_screen(self):
        """Ogranicz wysokość do dostępnego obszaru ekranu i przesuń okno tak, by w całości było widoczne."""
        from PySide6.QtGui import QGuiApplication
        scr = (self.parentWidget().screen() if self.parentWidget() else None) or self.screen() or QGuiApplication.primaryScreen()
        sc = scr.availableGeometry()
        margin = 20
        want_h = self._body.sizeHint().height() + 70          # zawartość + pasek przycisków
        h = max(300, min(want_h, sc.height() - 2*margin))
        w = max(self.width(), self.minimumWidth())
        if self._scroll.verticalScrollBar().isVisible() or want_h > h:
            w += 14                                            # miejsce na scrollbar
        w = min(w, sc.width() - 2*margin)
        self.resize(w, h)
        x = max(sc.x() + margin, min(self.x(), sc.x() + sc.width()  - w - margin))
        y = max(sc.y() + margin, min(self.y(), sc.y() + sc.height() - h - margin))
        self.move(x, y)

    def _lbl(self, t):  l=QLabel(t); l.setStyleSheet(f"color:{C['t2']}"); return l
    def _note(self, t): l=QLabel(t); l.setStyleSheet(f"color:{C['t3']};font-size:11px"); l.setWordWrap(True); return l
    def _sep(self):     f=QFrame(); f.setFrameShape(QFrame.HLine); f.setStyleSheet(f"background:{C['border']};max-height:1px"); return f

    def _save(self):
        self.cfg["hotkey"]       = self.hotkey.text().strip() or "`"
        self.cfg["layout_mode"]  = "bar" if self.btn_bar.isChecked() else "panel"
        self.cfg["panel_height"] = self.spin_ph.value()
        self.cfg["panel_width"]  = self.spin_pw.value()
        self.cfg["bar_height"]   = self.spin_bh.value()
        self.cfg["cards_per_row"] = 0 if self.cb_cpr_auto.isChecked() else self.spin_cpr.value()
        self.cfg["excel_dependent"] = self.cb_excel_dep.isChecked()
        self.cfg["show_at_cursor"]  = self.cb_cursor.isChecked()
        self.cfg["new_card_position"] = "bottom" if self.rb_bottom.isChecked() else "top"
        self.accept()

    def get(self): return self.cfg


# ─── Clip Card ────────────────────────────────────────────────────────────────

CARD_W = 280          # preferowana (minimalna w trybie auto) szerokość karty
CARD_MIN_W = 150      # absolutne minimum szerokości karty
CARDS_PER_ROW = 0     # 0 = auto; >0 = stała liczba kart w wierszu (ustawiana z Settings)
DRAG_MIME = "application/x-clipcard-reorder"


class DragHandle(QWidget):
    """Uchwyt (6 kropek) do przeciągania karty."""
    drag_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 28)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Przeciągnij, aby zmienić kolejność")
        self._press = None
        self._hover = False

    def enterEvent(self, e):
        self._hover = True; self.update(); super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C['t1'] if self._hover else C['t3']))
        cx, cy = self.width() / 2, self.height() / 2
        for dx in (-3, 3):
            for dy in (-6, 0, 6):
                p.drawEllipse(QPointF(cx + dx, cy + dy), 1.6, 1.6)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        e.accept()

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            if (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance():
                self._press = None
                self.drag_requested.emit()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._press = None; e.accept()


class ClipCard(QFrame):
    sig_click      = Signal(object)
    sig_remove     = Signal(object)
    sig_pin        = Signal(object)
    sig_edit       = Signal(object)
    sig_drag_begin = Signal(object)
    sig_drag_end   = Signal()

    def __init__(self, item: ClipItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._img_lbl = None
        self._img_w   = 0
        self._movie   = None      # QMovie dla animowanych GIFów
        self._gif_size = QSize()
        self.setFixedWidth(CARD_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setCursor(Qt.PointingHandCursor)
        self.pan = None            # KineticPan planszy (ustawiany przez Board) — przeciąganie = przewijanie
        self._press_ok = False
        self._build(); self._restyle()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(40)
        hdr.setStyleSheet(f"background:{C['acc_dim']};border-radius:8px 8px 0 0;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,0,6,0); hl.setSpacing(4)
        ico = QLabel({"image": "🖼", "gif": "🎞"}.get(self.item.ctype, "📋"))
        ico.setStyleSheet("font-size:16px;background:transparent;")
        hl.addWidget(ico)
        disp = self.item.display()
        title = QLabel(disp[:38] + ("…" if len(disp)>38 else ""))
        title.setStyleSheet(f"color:{C['t1']};font-size:12px;font-weight:600;background:transparent;")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl.addWidget(title, 1)
        # uchwyt do zmiany kolejności (przed przyciskiem Edit)
        self._handle = DragHandle()
        self._handle.drag_requested.connect(self._start_drag)
        hl.addWidget(self._handle)
        # action buttons
        for sym, obj, tip, fn in [
            ("📝","CardBtn",    "Edit",   lambda: self.sig_edit.emit(self.item)),
            ("📌","CardBtnPin","Pin",    self._toggle_pin),
            ("🗑","CardBtnDel","Remove", lambda: self.sig_remove.emit(self.item)),
        ]:
            b = QPushButton(sym); b.setObjectName(obj); b.setToolTip(tip); b.clicked.connect(fn)
            if obj == "CardBtnPin":
                b.setProperty("on", "true" if self.item.pinned else "false")
                self._pin_btn = b
            hl.addWidget(b)
        root.addWidget(hdr)

        # Body
        body = QWidget(); body.setStyleSheet(f"background:{C['card']};border-radius:0 0 8px 8px;")
        bl = QVBoxLayout(body); bl.setContentsMargins(10,8,10,10)
        bl.setAlignment(Qt.AlignTop) # Prevents vertical centering layout quirks
        
        if self.item.ctype in ("image", "gif") and (self.item.file or self.item.img_b64):
            lbl = QLabel()
            lbl.setStyleSheet("background:transparent;")
            if self.item.ctype == "gif":
                raw = self.item.raw()
                if raw:
                    # Bajty trzymamy w pamięci (nie otwieramy pliku) — dzięki temu plik można
                    # bez problemu skasować na Windows, a bufor żyje tak długo jak QMovie.
                    self._gif_bytes = QByteArray(raw)
                    self._gif_buf = QBuffer(self._gif_bytes); self._gif_buf.open(QBuffer.ReadOnly)
                    movie = QMovie(self._gif_buf, QByteArray(b"gif"), self)
                    if movie.isValid() and movie.jumpToFrame(0):
                        self._gif_size = movie.currentImage().size()
                        self._movie = movie
                        self._img_lbl = lbl
                        lbl.setMovie(movie)
                        self._update_image(self.width())
            else:
                self._img_lbl = lbl
                self._update_image(self.width())
            if self._img_lbl is None:
                self._missing(lbl)
            bl.addWidget(lbl)
        else:
            # TEXT DISPLAY - Wykorzystujemy QTextEdit dla identycznego wyglądu jak w edytorze
            txt = QTextEdit()
            txt.setPlainText(self.item.text[:500]) # Pokazujemy nieco więcej tekstu
            txt.setReadOnly(True)
            txt.setFrameStyle(QFrame.NoFrame)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            txt.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            
            # To sprawia, że kliknięcia "przelatują" przez tekst do karty pod spodem
            txt.setAttribute(Qt.WA_TransparentForMouseEvents)
            
            # Usuwamy marginesy wewnętrzne dokumentu
            txt.document().setDocumentMargin(0)
            
            txt.setStyleSheet(f"""
                QTextEdit {{
                    color: {C['t2']};
                    background: transparent;
                    border: none;
                    font-size: 11px;
                }}
            """)
            txt.setFixedHeight(60) # Dopasuj wysokość do rozmiaru swoich kart
            bl.addWidget(txt)
        ts = QLabel(datetime.fromtimestamp(self.item.ts).strftime("%H:%M  %d %b"))
        ts.setStyleSheet(f"color:{C['t3']};font-size:11px;background:transparent;")
        bl.addWidget(ts)
        root.addWidget(body)

    def _update_image(self, card_w):
        """Skaluje obrazek do aktualnej szerokości karty (minus marginesy body 2x10 px)."""
        if self._img_lbl is None: return
        tw = max(40, card_w - 20)
        if tw == self._img_w: return
        self._img_w = tw
        if self._movie is not None:
            sw, sh = self._gif_size.width(), self._gif_size.height()
            th = max(1, round(tw * sh / sw)) if sw > 0 else tw
            self._movie.setScaledSize(QSize(tw, th))
            self._img_lbl.setFixedSize(tw, th)
        else:
            pm = _scaled_pixmap(self.item, tw)
            if pm is not None:
                self._img_lbl.setPixmap(pm)
            else:
                self._missing(self._img_lbl)
                self._img_lbl = None

    @staticmethod
    def _missing(lbl):
        """Plik obrazu usunięty / uszkodzony — pokazujemy placeholder zamiast wywracać kartę."""
        lbl.setText("⚠ brak pliku obrazu")
        lbl.setStyleSheet(f"color:{C['t3']};font-size:11px;background:transparent;")

    # GIF animuje się tylko, gdy karta jest widoczna (oszczędza CPU przy ukrytym panelu / innej zakładce)
    def showEvent(self, e):
        super().showEvent(e)
        m = self._movie
        if m is not None:
            if m.state() == QMovie.NotRunning: m.start()
            elif m.state() == QMovie.Paused:   m.setPaused(False)

    def hideEvent(self, e):
        super().hideEvent(e)
        m = self._movie
        if m is not None and m.state() == QMovie.Running:
            m.setPaused(True)

    def set_card_width(self, w):
        if self.width() == w and self.minimumWidth() == w and self._img_w == max(40, w - 20):
            return
        self.setFixedWidth(w)
        self._update_image(w)
        lay = self.layout()
        if lay: lay.activate()     # odśwież sizeHint po zmianie szerokości/obrazka

    def _start_drag(self):
        pm = self.grab()
        ghost = QPixmap(pm.size())
        ghost.setDevicePixelRatio(pm.devicePixelRatio())
        ghost.fill(Qt.transparent)
        gp = QPainter(ghost); gp.setOpacity(0.85); gp.drawPixmap(0, 0, pm); gp.end()

        mime = QMimeData(); mime.setData(DRAG_MIME, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(ghost)
        drag.setHotSpot(self._handle.mapTo(self, self._handle.rect().center()))

        eff = QGraphicsOpacityEffect(self); eff.setOpacity(0.35)
        self.setGraphicsEffect(eff)
        self.sig_drag_begin.emit(self.item)
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self.setGraphicsEffect(None)
            self.sig_drag_end.emit()

    def _toggle_pin(self):
        self.item.pinned = not self.item.pinned
        v = "true" if self.item.pinned else "false"
        self._pin_btn.setProperty("on", v)
        self._pin_btn.style().unpolish(self._pin_btn); self._pin_btn.style().polish(self._pin_btn)
        self.sig_pin.emit(self.item); self._restyle()

    def _restyle(self):
        self.setObjectName("CardPin" if self.item.pinned else "Card")
        self.style().unpolish(self); self.style().polish(self)

    # Klik (kopiuj i ukryj) dopiero po PUSZCZENIU przycisku — dzięki temu przeciągnięcie karty
    # myszą przewija listę (jak na ekranie dotykowym), a nie kopiuje karty.
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_ok = not isinstance(self.childAt(e.position().toPoint()), QPushButton)
            if self._press_ok and self.pan is not None:
                self.pan.press(e.globalPosition().toPoint())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_ok and self.pan is not None and (e.buttons() & Qt.LeftButton):
            if self.pan.move(e.globalPosition().toPoint()):
                e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._press_ok:
            self._press_ok = False
            panned = self.pan.release() if self.pan is not None else False
            if not panned and self.rect().contains(e.position().toPoint()):
                self.sig_click.emit(self.item)
        super().mouseReleaseEvent(e)


# ─── Board ────────────────────────────────────────────────────────────────────

class DropContainer(QWidget):
    """Kontener kart — przyjmuje upuszczane karty i rysuje wskaźnik wstawienia."""
    def __init__(self, board):
        super().__init__()
        self.board = board
        self.indicator = None
        self.pan = None            # KineticPan (ustawiany przez Board)
        self.setAcceptDrops(True)

    # Przeciąganie myszą po pustym tle (między kartami) też przewija listę
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.pan is not None:
            self.pan.press(e.globalPosition().toPoint())
        e.accept()

    def mouseMoveEvent(self, e):
        if self.pan is not None and (e.buttons() & Qt.LeftButton):
            self.pan.move(e.globalPosition().toPoint())
        e.accept()

    def mouseReleaseEvent(self, e):
        if self.pan is not None:
            self.pan.release()
        e.accept()

    def set_indicator(self, rect):
        if rect != self.indicator:
            self.indicator = rect; self.update()

    def dragEnterEvent(self, e):   self.board._drag_enter(e)
    def dragMoveEvent(self, e):    self.board._drag_move(e, e.position().toPoint())
    def dragLeaveEvent(self, e):   self.set_indicator(None)
    def dropEvent(self, e):        self.board._drop(e, e.position().toPoint())

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.indicator:
            p = QPainter(self)
            p.setPen(Qt.NoPen); p.setBrush(QColor(C['acc']))
            p.drawRoundedRect(self.indicator, 1.5, 1.5)


class Board(QWidget):
    item_clicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.items: list[ClipItem] = []
        self._filter = ""
        self._drag_item = None
        self._pending_drop = None
        self._rebuild_pending = False
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        # Przewijanie: kółko, pasek, strzałki ▲▼ po prawej i przeciąganie myszą (jak na telefonie)
        self._scroller = ArrowScrollArea("v")
        self.scroll = self._scroller.area
        self.pan = self._scroller.pan
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cont = DropContainer(self); self.cont.setStyleSheet("background:transparent;")
        self.cont.pan = self.pan
        self.flow = FlowLayout(self.cont, margin=10, h_sp=8, v_sp=8)
        self.scroll.setWidget(self.cont)
        lay.addWidget(self._scroller)

    def hideEvent(self, e):
        self.pan.cancel()          # nie zostawiaj kursora „łapki” / bezwładności po schowaniu panelu
        super().hideEvent(e)

    def add_item(self, item):
        # --- ZMIANA: Usuwanie duplikatu i przesuwanie na górę ---
        to_remove = None
        for existing in self.items:
            if existing.ctype == item.ctype:
                if item.ctype == "text" and existing.text == item.text:
                    to_remove = existing
                    break
                elif item.ctype in ("image", "gif") and item.key() and existing.key() == item.key():
                    to_remove = existing
                    break
                    
        if to_remove:
            # Transferujemy właściwości z istniejącej karty
            item.pinned = to_remove.pinned
            item.label = to_remove.label
            self.items.remove(to_remove)
            
        # Kolejność wyświetlania: przypięte na górze, w grupie wg kolejności listy (sort stabilny),
        # więc insert(0) = początek swojej kategorii, append = koniec swojej kategorii.
        cfg = getattr(self.window(), "config", None) or {}
        if cfg.get("new_card_position", "top") == "bottom":
            self.items.append(item)
        else:
            self.items.insert(0, item)
        self._rebuild()

    def remove_item(self, item):
        if item in self.items: self.items.remove(item); self._rebuild()

    def remove_all(self):
        self.items.clear(); self._rebuild()

    def remove_unpinned(self):
        self.items = [it for it in self.items if it.pinned]
        self._rebuild()

    def set_filter(self, t):
        self._filter = t.lower(); self._rebuild()

    def _rebuild(self):
        if self._drag_item is not None:      # nie niszcz kart w trakcie przeciągania
            self._rebuild_pending = True
            return
        self.pan.cancel()
        self.flow.clear()
        visible = [it for it in self.items
                   if not self._filter
                   or self._filter in it.display().lower()
                   or self._filter in it.text.lower()]
        for it in sorted(visible, key=lambda x: not x.pinned):   # stabilnie: przypięte na górze, reszta wg kolejności listy
            c = ClipCard(it)
            c.pan = self.pan
            c.sig_click.connect(self.item_clicked)
            c.sig_remove.connect(self._on_remove)
            c.sig_pin.connect(self._on_pin)
            c.sig_edit.connect(self._on_edit)
            c.sig_drag_begin.connect(self._drag_begin)
            c.sig_drag_end.connect(self._drag_end)
            self.flow.addWidget(c)
            c.show()
        self.cont.updateGeometry()
        self.cont.adjustSize()

    # ── Drag & drop (zmiana kolejności w obrębie tej samej grupy: przypięte / zwykłe) ──
    def _drag_begin(self, item):
        self._drag_item = item
        self._pending_drop = None

    def _drag_end(self):
        self.cont.set_indicator(None)
        pending, self._pending_drop = self._pending_drop, None
        self._drag_item = None
        changed = False
        if pending:
            item, target, before = pending
            if item is not target and item in self.items and target in self.items:
                self.items.remove(item)
                idx = self.items.index(target) + (0 if before else 1)
                self.items.insert(idx, item)
                changed = True
        if changed or self._rebuild_pending:
            self._rebuild_pending = False
            self._rebuild()
        if changed:
            self._save()

    def _locate(self, pos):
        """Zwraca (karta_docelowa, wstaw_przed) lub None — tylko karty tej samej grupy."""
        drag = self._drag_item
        if drag is None: return None
        best, best_d = None, None
        for i in range(self.flow.count()):
            w = self.flow.itemAt(i).widget()
            if not isinstance(w, ClipCard) or w.item.pinned != drag.pinned:
                continue
            g = w.geometry()
            dx = max(g.left() - pos.x(), 0, pos.x() - g.right())
            dy = max(g.top() - pos.y(), 0, pos.y() - g.bottom())
            d = dx*dx + dy*dy
            if best_d is None or d < best_d:
                best, best_d = w, d
        if best is None: return None
        return best, pos.x() < best.geometry().center().x()

    def _drag_enter(self, e):
        if e.mimeData().hasFormat(DRAG_MIME) and self._drag_item in self.items:
            e.acceptProposedAction()
        else:
            e.ignore()

    def _autoscroll(self, pos):
        vp = self.scroll.viewport()
        y = self.cont.mapTo(vp, pos).y()
        bar = self.scroll.verticalScrollBar()
        if y < 30:                  bar.setValue(bar.value() - 18)
        elif y > vp.height() - 30:  bar.setValue(bar.value() + 18)

    def _drag_move(self, e, pos):
        if not e.mimeData().hasFormat(DRAG_MIME) or self._drag_item is None:
            e.ignore(); return
        e.acceptProposedAction()
        self._autoscroll(pos)
        loc = self._locate(pos)
        if not loc:
            self.cont.set_indicator(None); return
        card, before = loc
        g = card.geometry()
        x = g.left() - 5 if before else g.right() + 3
        self.cont.set_indicator(QRect(x, g.top(), 3, g.height()))

    def _drop(self, e, pos):
        loc = self._locate(pos) if e.mimeData().hasFormat(DRAG_MIME) else None
        self.cont.set_indicator(None)
        if loc:
            card, before = loc
            self._pending_drop = (self._drag_item, card.item, before)
            e.acceptProposedAction()
        else:
            e.ignore()

    def _on_remove(self, it): self.remove_item(it); self._save()
    def _on_pin(self, it):    self._rebuild();       self._save()
    def _on_edit(self, it):
        dlg = EditDialog(it, self.window())
        if dlg.exec(): self._rebuild(); self._save()

    def _save(self):
        w = self.window()
        if hasattr(w, "_save_data"): w._save_data()


# ─── Tab bar row ─────────────────────────────────────────────────────────────

class TabBarRow(QWidget):
    tab_clicked    = Signal(int)
    tab_close_req  = Signal(int)
    tab_rename_req = Signal(int) 
    tab_add_req    = Signal()

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self._lay = lay

    def refresh(self, names, active):
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for i, name in enumerate(names):
            wrap = QWidget(); wrap.setStyleSheet("background:transparent")
            wl = QHBoxLayout(wrap); wl.setContentsMargins(0,0,0,0); wl.setSpacing(1)
            btn = QPushButton(name); btn.setObjectName("Tab")
            btn.setProperty("active","true" if i==active else "false")
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _,idx=i: self.tab_clicked.emit(idx))
            wl.addWidget(btn)
            
            if name != "Main":
                x = QPushButton("✕"); x.setObjectName("TabClose"); x.setToolTip("Close")
                x.clicked.connect(lambda _,idx=i: self.tab_close_req.emit(idx))
                wl.addWidget(x)
                
                btn.setContextMenuPolicy(Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, idx=i, b=btn: self._show_menu(pos, idx, b))
                
            self._lay.addWidget(wrap)
        add = QPushButton("+"); add.setObjectName("TabAdd"); add.setToolTip("New tab")
        add.clicked.connect(self.tab_add_req)
        self._lay.addWidget(add)
        self._lay.addStretch()

    def _show_menu(self, pos, idx, btn):
        m = QMenu(self)
        m.setStyleSheet(SS) 
        m.addAction("Rename").triggered.connect(lambda: self.tab_rename_req.emit(idx))
        m.addAction("Remove").triggered.connect(lambda: self.tab_close_req.emit(idx))
        m.exec(btn.mapToGlobal(pos))

    def set_active(self, idx):
        i = 0
        for j in range(self._lay.count()):
            it = self._lay.itemAt(j)
            if not it or not it.widget(): continue
            for child in it.widget().findChildren(QPushButton):
                if child.objectName() == "Tab":
                    child.setProperty("active","true" if i==idx else "false")
                    child.style().unpolish(child); child.style().polish(child)
                    i += 1


# ─── Main Panel ───────────────────────────────────────────────────────────────

class MainPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._is_paused = False
        self._loaded_ok = True            # False => nie sprzątamy plików (np. uszkodzony JSON)
        # Zapis z opóźnieniem: seria zmian (pin, drag, kilka kopiowań) = jeden zapis
        self._save_timer = QTimer(self); self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._write_data)
        QApplication.instance().aboutToQuit.connect(self._flush_save)
        self.config = self._load_cfg()
        self._apply_cards_per_row()
        self._drag_pos = None
        self._last_tab = 0
        self._boards: list[Board] = []
        self._tab_labels: list[str] = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setObjectName("Panel")
        self._build_ui()
        self._setup_tray()
        self._load_data()
        self._setup_clipboard()
        self._setup_hotkey()
        self._setup_outside_filter()

    def _load_cfg(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f: return {**DEFAULT_CONFIG, **json.load(f)}
            except: pass
        return DEFAULT_CONFIG.copy()

    def _save_cfg(self):
        with open(CONFIG_FILE,"w") as f: json.dump(self.config, f, indent=2)

    def _load_data(self):
        # Nowy format w ~/.clipboard_manager/, a jeśli go jeszcze nie ma — stary plik (migracja)
        src = DATA_FILE if DATA_FILE.exists() else (LEGACY_DATA_FILE if LEGACY_DATA_FILE.exists() else None)
        if src is None: return
        migrated = src is LEGACY_DATA_FILE
        try:
            with open(src, encoding="utf-8") as f: data = json.load(f)
            for td in data.get("tabs",[]):
                name  = td.get("name","Tab")
                items = [ClipItem.from_dict(d) for d in td.get("items",[])]
                idx = self._find_tab(name)
                if idx >= 0:
                    self._boards[idx].items = items; self._boards[idx]._rebuild()
                else:
                    self._add_tab(name, items)
        except Exception as e:
            print("load:", e)
            self._loaded_ok = False
            migrated = False
            try: shutil.copy2(src, src.with_name(src.name + ".corrupt"))   # kopia ratunkowa
            except OSError: pass
        self._refresh_tabs()
        if migrated:
            self._write_data()    # zapisz nowy format od razu; stary plik zostaje jako kopia zapasowa

    def _save_data(self):
        """Zapis z opóźnieniem 400 ms (wywoływany często — pin, drag, nowe kopie)."""
        self._save_timer.start(400)

    def _flush_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._write_data()

    def _write_data(self):
        tabs = [{"name": n, "items": [it.to_dict() for it in self._boards[i].items]}
                for i, n in enumerate(self._tab_labels)]
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"tabs": tabs}, f, ensure_ascii=False)
            os.replace(tmp, DATA_FILE)       # atomowo — awaria w trakcie zapisu nie psuje historii
        except OSError as e:
            print("save:", e); return
        if self._loaded_ok:
            self._sweep_media(tabs)

    def _sweep_media(self, tabs):
        """Kasuje pliki z img/ i gif/, do których nie odwołuje się żadna karta."""
        used = {d["file"] for t in tabs for d in t["items"] if d.get("file")}
        for sub in ("img", "gif"):
            folder = DATA_DIR / sub
            try: names = os.listdir(folder)
            except OSError: continue
            for n in names:
                if n not in used:
                    try: (folder / n).unlink()
                    except OSError: pass     # np. plik chwilowo zajęty — spróbujemy przy następnym zapisie

    def _find_tab(self, name):
        try: return self._tab_labels.index(name)
        except ValueError: return -1

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(SS)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Toolbar
        tb_w = QWidget(); tb_w.setObjectName("Toolbar"); tb_w.setFixedHeight(50)
        tb_w.mousePressEvent   = self._drag_press
        tb_w.mouseMoveEvent    = self._drag_move
        tb_w.mouseReleaseEvent = self._drag_release
        # Zawartość paska jest przewijana poziomo (kółko myszy albo strzałki ◀ ▶ po bokach),
        # gdy się nie mieści — np. w wąskim oknie / na ekranie w trybie portrait.
        tb_outer = QHBoxLayout(tb_w); tb_outer.setContentsMargins(0,0,0,0); tb_outer.setSpacing(0)
        self._tb_scroller = ArrowScrollArea("h")
        self._tb_scroller.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tb_scroller.area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tb_inner = QWidget(); tb_inner.setObjectName("ToolbarInner")
        tb = QHBoxLayout(tb_inner); tb.setContentsMargins(12,0,8,0); tb.setSpacing(6)
        self._tb_scroller.area.setWidget(tb_inner)
        tb_outer.addWidget(self._tb_scroller)

        self._btn_new_card = QPushButton("+ New Card")
        self._btn_new_card.setObjectName("BtnNewCard")
        self._btn_new_card.setToolTip("Create a new custom card")
        self._btn_new_card.clicked.connect(self._new_card)
        tb.addWidget(self._btn_new_card)
        tb.addSpacing(8)

        self._btn_rem_unpinned = QPushButton("Remove all 🗑️")
        self._btn_rem_unpinned.setObjectName("BtnRemove")
        self._btn_rem_unpinned.setToolTip("Remove all unpinned items")
        self._btn_rem_unpinned.clicked.connect(self._remove_unpinned)
        tb.addWidget(self._btn_rem_unpinned)

        self._btn_rem_all = QPushButton("Remove all 🗑️📌")
        self._btn_rem_all.setObjectName("BtnRemove")
        self._btn_rem_all.setToolTip("Remove absolutely everything")
        self._btn_rem_all.clicked.connect(self._remove_all)
        tb.addWidget(self._btn_rem_all)
        tb.addSpacing(8)

        self._search = QLineEdit(); self._search.setObjectName("Search")
        self._search.setPlaceholderText("Search…"); self._search.textChanged.connect(self._on_search)
        tb.addWidget(self._search)
        tb.addSpacing(4)
        
        self._tabbar = TabBarRow()
        self._tabbar.tab_clicked.connect(self._switch_tab)
        self._tabbar.tab_close_req.connect(self._close_tab)
        self._tabbar.tab_rename_req.connect(self._rename_tab) 
        self._tabbar.tab_add_req.connect(self._new_tab)
        tb.addWidget(self._tabbar, 1)
        tb.addSpacing(4)
        
        self._btn_pause = QPushButton("works ⏸️")
        self._btn_pause.setObjectName("BtnPause")
        self._btn_pause.setCheckable(True)
        self._btn_pause.setToolTip("Toggle clipboard listening")
        self._btn_pause.clicked.connect(self._toggle_pause)
        tb.addWidget(self._btn_pause)
        tb.addSpacing(4)

        self._cb_excel = QCheckBox("Excel mode")
        self._cb_excel.setObjectName("CbExcel")
        self._cb_excel.setStyleSheet(f"""
            QCheckBox {{ color: {C['t2']}; spacing: 5px; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; background: {C['card']}; border: 1px solid {C['border']}; border-radius: 3px; }}
            QCheckBox::indicator:checked {{ background: {C['acc']}; border-color: {C['acc']}; }}
        """)
        self._cb_excel.setToolTip("Automatycznie usuwa skrajne cudzysłowy ze skopiowanego tekstu")
        tb.addWidget(self._cb_excel)
        tb.addSpacing(4)

        for sym, obj, tip, fn in [
            ("⏻","BtnQuit","Quit",     self._quit),
            ("⚙","BtnIcon","Settings", self._settings),
            ("—","BtnIcon","Hide",     self.hide_to_tray),
        ]:
            b = QPushButton(sym); b.setObjectName(obj); b.setToolTip(tip); b.clicked.connect(fn)
            tb.addWidget(b)
        root.addWidget(tb_w)

        # Body
        body = QWidget(); body.setObjectName("Body")
        bl = QHBoxLayout(body); bl.setContentsMargins(0,0,0,0); bl.setSpacing(0)

        self._stack = QWidget(); self._stack.setStyleSheet("background:transparent;")
        self._stack_lay = QVBoxLayout(self._stack)
        self._stack_lay.setContentsMargins(0,0,0,0); self._stack_lay.setSpacing(0)
        bl.addWidget(self._stack, 1)
        
        root.addWidget(body, 1)

        # Status bar
        sb = QWidget(); sb.setFixedHeight(26)
        sb.setStyleSheet(f"background:{C['panel']};border-top:1px solid {C['border']};border-radius:0 0 10px 10px;")
        sbl = QHBoxLayout(sb); sbl.setContentsMargins(12,0,12,0)
        lbl = QLabel("Click item to copy & hide"); lbl.setStyleSheet(f"color:{C['t3']};font-size:11px;")
        sbl.addWidget(lbl); sbl.addStretch()
        root.addWidget(sb)

        self._add_tab("Main"); self._refresh_tabs()

    def _add_tab(self, name, items=None):
        board = Board(); board.item_clicked.connect(self._on_item_click)
        if items: board.items = items; board._rebuild()
        for b in self._boards: b.setVisible(False)
        self._boards.append(board); self._tab_labels.append(name)
        self._stack_lay.addWidget(board); board.setVisible(True)
        self._last_tab = len(self._boards)-1
        return self._last_tab

    def _refresh_tabs(self):
        self._tabbar.refresh(self._tab_labels, self._last_tab)

    def _switch_tab(self, idx):
        if idx < 0 or idx >= len(self._boards): return
        self._boards[self._last_tab].setVisible(False)
        self._last_tab = idx
        self._boards[idx].setVisible(True)
        self._boards[idx].set_filter(self._search.text())
        self._tabbar.set_active(idx)

    def _new_card(self):
        item = ClipItem("text", text="")
        dlg = EditDialog(item, self, create_mode=True)
        if dlg.exec():
            if not self._boards:
                self._add_tab("Main")
            self._boards[self._last_tab].add_item(item)
            self._refresh_tabs()
            self._save_data()

    def _new_tab(self):
        text, ok = QInputDialog.getText(self,"New Tab","Tab name:",text=f"Tab {len(self._tab_labels)}")
        if ok and text.strip():
            self._add_tab(text.strip()); self._refresh_tabs(); self._save_data()

    def _close_tab(self, idx):
        if self._tab_labels[idx]=="Main" or len(self._tab_labels)<=1: return
        if QMessageBox.question(self,"Remove Tab",
               f"Remove '{self._tab_labels[idx]}' and all its items?",
               QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        b = self._boards.pop(idx); self._stack_lay.removeWidget(b); b.deleteLater()
        self._tab_labels.pop(idx)
        ni = min(idx, len(self._boards)-1); self._last_tab = ni
        self._boards[ni].setVisible(True)
        self._refresh_tabs(); self._save_data()

    def _rename_tab(self, idx):
        text, ok = QInputDialog.getText(self,"Rename","Name:", text=self._tab_labels[idx])
        if ok and text.strip():
            self._tab_labels[idx] = text.strip(); self._refresh_tabs(); self._save_data()

    def _remove_all(self):
        b = self._boards[self._last_tab] if self._boards else None
        if b and b.items:
            if QMessageBox.question(self,"Remove All","Clear EVERYTHING from this board (including pinned)?",
                   QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
                b.remove_all(); self._save_data()

    def _remove_unpinned(self):
        b = self._boards[self._last_tab] if self._boards else None
        if b and b.items:
            if QMessageBox.question(self,"Remove Unpinned","Clear all unpinned items from this board?",
                   QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
                b.remove_unpinned(); self._save_data()

    def _toggle_pause(self):
        self._is_paused = self._btn_pause.isChecked()
        if self._is_paused:
            self._btn_pause.setText("stopped ▶️")
        else:
            self._btn_pause.setText("works ⏸️")
            # --- ZMIANA: Sync schowka przy wznowieniu, by zignorować to co już tam jest ---
            cb = QGuiApplication.clipboard()
            mime = cb.mimeData()
            self._last_text = cb.text().strip() if mime.hasText() else ""
            if mime.hasImage() and mime.hasFormat("image/png"):
                self._last_img = (mime.data("image/png").size(), "png")
            elif mime.hasImage():
                img = cb.image()
                self._last_img = (img.width(), img.height(), img.pixel(0,0) if img.width()>0 else 0) if not img.isNull() else None

    def _on_search(self, t):
        if self._boards: self._boards[self._last_tab].set_filter(t)

    # ZAKTUALIZOWANA FUNKCJA: Wklejanie do schowka z zachowaniem przezroczystości
    def _on_item_click(self, item):
        cb = QGuiApplication.clipboard()
        # Blokujemy nasłuchiwanie schowka, żeby kliknięcie nie dodało elementu po raz drugi
        self._ignore_clipboard = True
        try:
            if item.ctype == "text":
                cb.setText(item.text)
                self._last_text = item.text.strip()
                self._last_processed = item.text.strip()
            elif item.ctype == "image" and (item.file or item.img_b64):
                ba = QByteArray(item.raw())
                img = QImage.fromData(ba)
                if not img.isNull():
                    mime = QMimeData()
                    mime.setImageData(img)
                    # Wymuszamy dodanie surowego formatu PNG, by nie utracić kanału alpha!
                    mime.setData("image/png", ba)
                    cb.setMimeData(mime)
                    self._last_img = (ba.size(), "png")
                    self._last_text = ""
            elif item.ctype == "gif" and (item.file or item.img_b64):
                raw = item.raw()
                if raw:
                    mime = QMimeData()
                    # Plik .gif prosto z img/gif (czaty, Explorer, Discord/Slack/Teams wklejają animację),
                    # surowy image/gif oraz pierwsza klatka jako obraz (Paint, Word itd.)
                    if item.file and item.path().exists():
                        mime.setUrls([QUrl.fromLocalFile(str(item.path()))])
                    mime.setData("image/gif", QByteArray(raw))
                    first = QImage.fromData(QByteArray(raw))
                    if not first.isNull(): mime.setImageData(first)
                    cb.setMimeData(mime)
                    self._last_text = ""
        finally:
            QTimer.singleShot(200, lambda: setattr(self, '_ignore_clipboard', False))
        self.hide_to_tray()

    # ── Clipboard ───────────────────────────────────────────────────────────

    def _setup_clipboard(self):
        self._last_update = 0  # Zmienna do zapobiegania spamowi zdarzeń
        self._ignore_clipboard = False  # Flaga: blokuje _poll_clip gdy sami piszemy do schowka
        cb = QGuiApplication.clipboard()
        self._nam = QNetworkAccessManager(self)   # pobieranie GIFów kopiowanych z przeglądarki
        self._gif_pending = set()
        # Zamiast QTimer, używamy sygnału systemowego - reaguje na sam fakt "Kopiuj"
        cb.dataChanged.connect(self._poll_clip)

    def _add_gif(self, data: bytes):
        self._boards[self._last_tab].add_item(ClipItem.media("gif", data))

    def _fetch_gif(self, url: str, fallback_png: bytes):
        """Pobiera GIF z URL-a asynchronicznie; przy porażce dodaje statyczny obraz z fallbacku."""
        if url in self._gif_pending: return
        self._gif_pending.add(url)
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                         QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(8000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda r=reply: self._gif_fetched(r, url, fallback_png))

    def _gif_fetched(self, reply, url, fallback_png):
        self._gif_pending.discard(url)
        data = bytes(reply.readAll()) if reply.error() == QNetworkReply.NoError else b""
        reply.deleteLater()
        if self._is_paused: return
        if _is_animated_gif(data):
            self._add_gif(data)
        elif fallback_png:
            self._boards[self._last_tab].add_item(ClipItem.media("image", fallback_png))
        else:
            return
        self._save_data()

    def _poll_clip(self):
        # Jeśli sami właśnie zapisaliśmy do schowka (Excel mode), ignorujemy to zdarzenie
        if getattr(self, '_ignore_clipboard', False):
            return

        excel_on = hasattr(self, '_cb_excel') and self._cb_excel.isChecked()
        excel_dependent = self.config.get("excel_dependent", False)

        if self._is_paused: 
            if not (excel_on and not excel_dependent):
                return
            
        now = time.time()
        if now - getattr(self, '_last_update', 0) < 0.1:
            return
            
        cb = QGuiApplication.clipboard()
        mime = cb.mimeData()
        t = cb.text().strip() if mime.hasText() else ""

        # --- WYKRYWANIE FORMATÓW ---
        formats = mime.formats()
        f_list = [f.lower() for f in formats]
        
        # Czy to aplikacja Office (Excel, PPT, Word, Web Excel/Sheets)?
        office_markers = ["biff", "excel", "spreadsheet", "powerpnt", "presentation", "office"]
        is_office_app = any(m in f for f in f_list for m in office_markers)
        
        # Czy to tabela lub metadane Office w HTML?
        html_content = mime.html().lower() if mime.hasHtml() else ""
        has_office_html = any(x in html_content for x in ["office:excel", "powerpoint", "urn:schemas-microsoft-com:office", "data-sheets-value"])
        is_table = "\t" in t or "<table" in html_content or "google-sheets" in html_content
        
        is_office_or_table = is_office_app or has_office_html or is_table

        # --- PRIORYTET 1: Pliki z Eksploratora (np. kopiowanie zdjęć jako pliki) ---
        if mime.hasUrls():
            added = False
            for url in mime.urls():
                if url.isLocalFile():
                    fp = url.toLocalFile()
                    ext = Path(fp).suffix.lower()
                    if ext == '.gif':
                        try: gdata = Path(fp).read_bytes()
                        except OSError: gdata = b""
                        if _is_animated_gif(gdata):
                            if not self._is_paused:
                                self._add_gif(gdata)
                            added = True
                            continue
                    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                        img = QImage(fp)
                        if not img.isNull():
                            ba = QByteArray(); b = QBuffer(ba); b.open(QBuffer.WriteOnly)
                            img.save(b, "PNG")
                            if not self._is_paused:
                                self._boards[self._last_tab].add_item(ClipItem.media("image", bytes(ba)))
                            added = True
            if added:
                if not self._is_paused:
                    self._save_data()
                self._last_update = now
                return

        # --- PRIORYTET 2: Obrazy (Przeglądarka, Photoshop, PrintScreen) ---
        # Wyjątek: Jeśli to Office LUB tabela, ignorujemy podgląd obrazu (aby priorytetyzować tekst komórek),
        # chyba że nie ma w ogóle tekstu (wtedy kopiujemy jako obraz, np. skopiowany wykres z Excela).
        # --- PRIORYTET 2a: Animowany GIF w schowku (surowe bajty image/gif) ---
        if not (is_office_or_table and bool(t)):
            gif = _gif_from_mime(mime)
            if gif and _is_animated_gif(gif):
                if not self._is_paused:
                    self._add_gif(gif)
                    self._save_data()
                self._last_update = now
                return

        if mime.hasImage() and not (is_office_or_table and bool(t)):
            if mime.hasFormat("image/png"):
                ba = mime.data("image/png")
            else:
                img = cb.image()
                if img.isNull(): return
                ba = QByteArray(); buf = QBuffer(ba); buf.open(QBuffer.WriteOnly); img.save(buf, "PNG")

            # --- PRIORYTET 2b: kopiowanie obrazu z przeglądarki — w HTML jest adres GIFa,
            # a w schowku tylko statyczna klatka. Pobieramy oryginał (asynchronicznie).
            gif_src = _gif_src_from_html(mime.html()) if mime.hasHtml() else None
            if gif_src and not self._is_paused:
                if gif_src.lower().startswith("data:"):
                    try: gdata = base64.b64decode(gif_src.split(",", 1)[1])
                    except Exception: gdata = b""
                    if _is_animated_gif(gdata):
                        self._add_gif(gdata); self._save_data()
                        self._last_update = now
                        return
                else:
                    self._fetch_gif(gif_src, bytes(ba))
                    self._last_update = now
                    return

            if not self._is_paused:
                self._boards[self._last_tab].add_item(ClipItem.media("image", bytes(ba)))
                self._save_data()
            self._last_update = now
            return
        # --- PRIORYTET 3: Tekst (Office, Tabele, Zwykły tekst) ---
        if t:
            # Obróbka dla trybu Excel
            if excel_on:
                cleaned = _excel_clean(t)
                # Anty-miganie dla tekstu (Excel generuje wiele zdarzeń dla tego samego tekstu)
                if getattr(self, '_last_processed', None) == cleaned and (now - getattr(self, '_last_update', 0) < 1.0):
                    return

                # Odkładamy setText na następny tick pętli zdarzeń.
                # Dzięki temu Excel zdąży dokończyć własne operacje na schowku,
                # a my nadpiszemy go już czystym tekstem (bez cudzysłowów).
                def _deferred_set(text=cleaned):
                    self._ignore_clipboard = True
                    QGuiApplication.clipboard().setText(text)
                    QTimer.singleShot(200, lambda: setattr(self, '_ignore_clipboard', False))

                QTimer.singleShot(0, _deferred_set)

                self._last_processed = cleaned
                self._last_update = now

                # Dodaj kartę TYLKO jeśli program nie jest zatrzymany
                if not self._is_paused:
                    self._boards[self._last_tab].add_item(ClipItem("text", text=cleaned))
                    self._save_data()
            else:
                # Anty-miganie dla tekstu (Excel generuje wiele zdarzeń dla tego samego tekstu)
                if getattr(self, '_last_processed', None) == t and (now - getattr(self, '_last_update', 0) < 1.0):
                    return

                self._last_processed = t
                self._last_update = now
                self._boards[self._last_tab].add_item(ClipItem("text", text=t))
                self._save_data()
            return
            
            

    # ── Tray ────────────────────────────────────────────────────────────────

    def _setup_tray(self):
        pix=QPixmap(32,32); pix.fill(QColor(C["acc"]))
        p=QPainter(pix); p.setPen(QColor("white")); p.setFont(QFont("Segoe UI",14))
        p.drawText(pix.rect(),Qt.AlignCenter,"📋"); p.end()
        self.tray=QSystemTrayIcon(QIcon(pix),self); self.tray.setToolTip(APP_NAME)
        m=QMenu(); m.setStyleSheet(SS)
        m.addAction("Show").triggered.connect(self.show_panel)
        m.addSeparator(); m.addAction("Quit").triggered.connect(self._quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_panel() if r==QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def hide_to_tray(self): self.hide()

    def show_panel(self):
        self._apply_geometry()
        self.show()
        self.raise_()
        self.activateWindow()
        # Wyczyszczenie fokusu z pola wyszukiwania i przekazanie go na główne okno.
        # Dzięki temu wciskany skrót (`) nie wpisze się do wyszukiwarki.
        self._search.clearFocus()
        self.setFocus()

    def _apply_geometry(self):
        from PySide6.QtGui import QCursor
        
        show_at_cursor = self.config.get("show_at_cursor", True)
        
        # 1. Wybór odpowiedniego ekranu NA SAMYM POCZĄTKU
        if show_at_cursor:
            cursor_pt = QCursor.pos()
            screen = QGuiApplication.screenAt(cursor_pt) or QGuiApplication.primaryScreen()
        else:
            screen = QGuiApplication.primaryScreen()
            
        sc = screen.availableGeometry()
        mode = self.config.get("layout_mode", "panel")
        
        if mode == "bar":
            bh = self.config.get("bar_height", 300)
            self.setMinimumSize(sc.width(), bh); self.setMaximumSize(sc.width(), bh)
            self.setGeometry(sc.x(), sc.y() + sc.height() - bh, sc.width(), bh)
        else:
            ph = self.config.get("panel_height", 560); pw = self.config.get("panel_width", 820)
            self.setMinimumSize(400, 300); self.setMaximumSize(16777215, 16777215)
            
            if show_at_cursor:
                mx = cursor_pt.x()
                my = cursor_pt.y()
                x = max(sc.x(), min(mx - pw // 2, sc.x() + sc.width()  - pw))
                y = max(sc.y(), min(my - ph // 2, sc.y() + sc.height() - ph))
                self.setGeometry(x, y, pw, ph)
            else:
                # Sztywna pozycja: prawy dolny róg wybranego (Głównego) ekranu
                self.setGeometry(sc.x() + sc.width() - pw - 20, sc.y() + sc.height() - ph - 60, pw, ph)

    # ── Settings ─────────────────────────────────────────────────────────

    def _apply_cards_per_row(self):
        global CARDS_PER_ROW
        try: CARDS_PER_ROW = max(0, int(self.config.get("cards_per_row", 0)))
        except Exception: CARDS_PER_ROW = 0
        for b in getattr(self, "_boards", []):
            b.flow.invalidate(); b.cont.updateGeometry(); b.cont.adjustSize()

    def _settings(self):
        dlg = SettingsDialog(self.config, self)
        dlg.setParent(self, Qt.Tool | Qt.FramelessWindowHint)
        if dlg.exec():
            old_key = self.config.get("hotkey")
            self.config = dlg.get(); self._save_cfg()
            self._apply_cards_per_row()
            if self.config.get("hotkey") != old_key: self._setup_hotkey()
            self._apply_geometry(); self.show(); self.raise_(); self.activateWindow()

    def _quit(self):
        self._save_data(); self._flush_save(); self._save_cfg(); QApplication.quit()

    def closeEvent(self, e):
        e.ignore(); self._save_data(); self._save_cfg(); self.hide_to_tray()

    # ── Hotkey ───────────────────────────────────────────────────────────

    def _setup_hotkey(self):
        try:
            import keyboard as kb
            if hasattr(self,"_hk_id") and self._hk_id:
                try: kb.remove_hotkey(self._hk_id)
                except: pass
            self._hk_triggered = False
            def _fire(): self._hk_triggered = True
            # suppress=False - klawisz działa normalnie w systemie
            self._hk_id = kb.add_hotkey(self.config.get("hotkey","`"), _fire, suppress=False)
        except Exception as e: print("hotkey:",e); self._hk_id=None
        if not hasattr(self,"_hk_timer"):
            self._hk_timer=QTimer(); self._hk_timer.timeout.connect(self._poll_hk)
            self._hk_timer.start(100)

    def _poll_hk(self):
        if getattr(self,"_hk_triggered",False):
            self._hk_triggered=False
            if self.isVisible(): self.hide_to_tray()
            else: self.show_panel()

    # ── Outside-click ────────────────────────────────────────────────────

    def _setup_outside_filter(self):
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type()==QEvent.MouseButtonPress and self.isVisible():
            # Zapobiega znikaniu: jeśli kliknięto w jakiekolwiek inne okno naszej aplikacji (np. Ustawienia)
            if QApplication.widgetAt(event.globalPosition().toPoint()) is not None:
                return super().eventFilter(obj, event)
                
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.hide_to_tray()
        return super().eventFilter(obj, event)

    # ── Drag ─────────────────────────────────────────────────────────────

    def _drag_press(self, e):
        if e.button()==Qt.LeftButton:
            self._drag_pos=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def _drag_move(self, e):
        if e.buttons()==Qt.LeftButton and self._drag_pos:
            self.move(e.globalPosition().toPoint()-self._drag_pos)
    def _drag_release(self, e): self._drag_pos=None

    # ── Keyboard ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        # Pochłaniamy wciśnięcie klawisza skrótu, żeby Windows nie odtwarzał
        # dźwięku błędu (ding) gdy okno nie ma aktywnego pola tekstowego.
        hk = self.config.get("hotkey", "`")
        if event.text() == hk:
            event.accept()
            return
            
        # Opcjonalnie: zamykanie okna klawiszem ESC
        if event.key() == Qt.Key_Escape:
            self.hide_to_tray()
            event.accept()
            return
            
        super().keyPressEvent(event)


# ─── Entry ───────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    panel = MainPanel()
    panel.show_panel()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()