#!/usr/bin/env python3
"""
Clipboard Manager — clean rewrite matching the reference UI.
"""

import sys, json, os, time, base64
from pathlib import Path
from datetime import datetime

# ── Hide console on Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    import ctypes
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw):
            import subprocess
            subprocess.Popen([pythonw] + sys.argv, creationflags=0x08000000)
            sys.exit(0)
        else:
            ctypes.windll.user32.ShowWindow(hwnd, 0)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QLineEdit, QSystemTrayIcon, QMenu, QDialog,
    QMessageBox, QInputDialog, QFrame, QSizePolicy, QTextEdit, QSpinBox,
    QLayout, QCheckBox,
)
# DODANO QMimeData DO IMPORTÓW PONIŻEJ
from PySide6.QtCore import Qt, QTimer, Signal, QByteArray, QEvent, QBuffer, QSize, QRect, QPoint, QMimeData
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPixmap, QPainter, QImage,
    QGuiApplication, QKeySequence, QShortcut,
)

# ─── Config ───────────────────────────────────────────────────────────────────

APP_NAME    = "Clipboard Manager"
DATA_FILE   = Path.home() / ".clipboard_manager_data.json"
CONFIG_FILE = Path.home() / ".clipboard_manager_config.json"

DEFAULT_CONFIG = {
    "hotkey":       "`",
    "layout_mode":  "panel",
    "panel_height": 560,
    "bar_height":   300,
    "panel_width":  820,
    "excel_dependent": False,
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
"""

# ─── Data model ───────────────────────────────────────────────────────────────

class ClipItem:
    def __init__(self, ctype="text", text="", img_b64="",
                 ts=None, pinned=False, label=""):
        self.ctype   = ctype
        self.text    = text
        self.img_b64 = img_b64
        self.ts      = ts or time.time()
        self.pinned  = pinned
        self.label   = label

    def display(self):
        if self.label: return self.label
        if self.ctype == "text": return self.text[:200].replace("\n", " ")
        return "[Image]"

    def to_dict(self):
        return dict(ctype=self.ctype, text=self.text, img_b64=self.img_b64,
                    ts=self.ts, pinned=self.pinned, label=self.label)

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("ctype","text"), d.get("text",""), d.get("img_b64",""),
                   d.get("ts", time.time()), d.get("pinned",False), d.get("label",""))


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
        x   = x0
        rh  = 0
        for it in self._items:
            w = it.widget()
            if w is None: continue
            iw = it.sizeHint().width()
            ih = it.sizeHint().height()
            nx = x + iw + self._h
            if nx - self._h > rect.right() - m.right() and x > x0:
                x = x0; y += rh + self._v; rh = 0
                nx = x + iw + self._h
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x = nx; rh = max(rh, ih)
        return y + rh - rect.y() + m.bottom()

    def clear(self):
        while self._items:
            it = self._items.pop()
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()


# ─── Dialogs ──────────────────────────────────────────────────────────────────

class EditDialog(QDialog):
    def __init__(self, item: ClipItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setMinimumWidth(420); self.setStyleSheet(SS)
        lay = QVBoxLayout(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(10)
        t = QLabel("Edit Clip"); t.setStyleSheet(f"font-size:15px;font-weight:600;")
        lay.addWidget(t)
        lay.addWidget(self._lbl("Label (optional):"))
        self.lbl_e = QLineEdit(item.label); self.lbl_e.setPlaceholderText("Custom name…")
        lay.addWidget(self.lbl_e)
        if item.ctype == "text":
            lay.addWidget(self._lbl("Content:"))
            self.txt = QTextEdit()
            self.txt.setPlainText(item.text)
            self.txt.setMinimumHeight(110)
            lay.addWidget(self.txt)
        else:
            lay.addWidget(self._lbl("[Image — not editable]")); self.txt = None
        row = QHBoxLayout(); row.addStretch()
        c = QPushButton("Cancel"); c.setObjectName("DlgCancel"); c.clicked.connect(self.reject)
        s = QPushButton("Save");   s.setObjectName("DlgOk");    s.clicked.connect(self._save)
        row.addWidget(c); row.addWidget(s); lay.addLayout(row)

    def _lbl(self, t):
        l = QLabel(t); l.setStyleSheet(f"color:{C['t2']};font-size:12px"); return l

    def _save(self):
        self.item.label = self.lbl_e.text().strip()
        if self.txt and self.item.ctype == "text": self.item.text = self.txt.toPlainText()
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg.copy()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setMinimumWidth(400); self.setStyleSheet(SS)
        lay = QVBoxLayout(self); lay.setContentsMargins(20,20,20,20); lay.setSpacing(14)

        t = QLabel("⚙  Settings"); t.setStyleSheet("font-size:15px;font-weight:600;")
        lay.addWidget(t)

        r = QHBoxLayout(); r.addWidget(self._lbl("Toggle Hotkey:")); r.addStretch()
        self.hotkey = QLineEdit(cfg.get("hotkey","`"))
        self.hotkey.setMaxLength(10); self.hotkey.setFixedWidth(80)
        r.addWidget(self.hotkey); lay.addLayout(r)
        lay.addWidget(self._note("Single key or name: ` F1 F2 …"))
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

        self.cb_excel_dep = QCheckBox("Excel mode depends from 'works' mode")
        self.cb_excel_dep.setChecked(cfg.get("excel_dependent", False))
        self.cb_excel_dep.setStyleSheet(f"color:{C['t1']}; spacing: 8px;")
        lay.addWidget(self.cb_excel_dep)
        lay.addWidget(self._note("Check if Excel mode should be paused when clipboard listening is paused. Uncheck (default) for cleanup to always run."))
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
        row2 = QHBoxLayout(); row2.addStretch()
        c = QPushButton("Cancel"); c.setObjectName("DlgCancel"); c.clicked.connect(self.reject)
        s = QPushButton("Apply");  s.setObjectName("DlgOk");    s.clicked.connect(self._save)
        row2.addWidget(c); row2.addWidget(s); lay.addLayout(row2)

    def _lbl(self, t):  l=QLabel(t); l.setStyleSheet(f"color:{C['t2']}"); return l
    def _note(self, t): l=QLabel(t); l.setStyleSheet(f"color:{C['t3']};font-size:11px"); l.setWordWrap(True); return l
    def _sep(self):     f=QFrame(); f.setFrameShape(QFrame.HLine); f.setStyleSheet(f"background:{C['border']};max-height:1px"); return f

    def _save(self):
        self.cfg["hotkey"]       = self.hotkey.text().strip() or "`"
        self.cfg["layout_mode"]  = "bar" if self.btn_bar.isChecked() else "panel"
        self.cfg["panel_height"] = self.spin_ph.value()
        self.cfg["panel_width"]  = self.spin_pw.value()
        self.cfg["bar_height"]   = self.spin_bh.value()
        self.cfg["excel_dependent"] = self.cb_excel_dep.isChecked()
        self.accept()

    def get(self): return self.cfg


# ─── Clip Card ────────────────────────────────────────────────────────────────

CARD_W = 280

class ClipCard(QFrame):
    sig_click  = Signal(object)
    sig_remove = Signal(object)
    sig_pin    = Signal(object)
    sig_edit   = Signal(object)

    def __init__(self, item: ClipItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setFixedWidth(CARD_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setCursor(Qt.PointingHandCursor)
        self._build(); self._restyle()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(40)
        hdr.setStyleSheet(f"background:{C['acc_dim']};border-radius:8px 8px 0 0;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,0,6,0); hl.setSpacing(4)
        ico = QLabel("🖼" if self.item.ctype=="image" else "📋")
        ico.setStyleSheet("font-size:16px;background:transparent;")
        hl.addWidget(ico)
        disp = self.item.display()
        title = QLabel(disp[:38] + ("…" if len(disp)>38 else ""))
        title.setStyleSheet(f"color:{C['t1']};font-size:12px;font-weight:600;background:transparent;")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl.addWidget(title, 1)
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
        
        if self.item.ctype == "image" and self.item.img_b64:
            lbl = QLabel()
            data = base64.b64decode(self.item.img_b64)
            qimg = QImage.fromData(QByteArray(data))
            if not qimg.isNull():
                pm = QPixmap.fromImage(qimg).scaledToWidth(CARD_W-20, Qt.SmoothTransformation)
                lbl.setPixmap(pm)
            lbl.setStyleSheet("background:transparent;")
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

    def _toggle_pin(self):
        self.item.pinned = not self.item.pinned
        v = "true" if self.item.pinned else "false"
        self._pin_btn.setProperty("on", v)
        self._pin_btn.style().unpolish(self._pin_btn); self._pin_btn.style().polish(self._pin_btn)
        self.sig_pin.emit(self.item); self._restyle()

    def _restyle(self):
        self.setObjectName("CardPin" if self.item.pinned else "Card")
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not isinstance(self.childAt(e.pos()), QPushButton):
                self.sig_click.emit(self.item)
        super().mousePressEvent(e)


# ─── Board ────────────────────────────────────────────────────────────────────

class Board(QWidget):
    item_clicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.items: list[ClipItem] = []
        self._filter = ""
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cont = QWidget(); self.cont.setStyleSheet("background:transparent;")
        self.flow = FlowLayout(self.cont, margin=10, h_sp=8, v_sp=8)
        self.scroll.setWidget(self.cont)
        lay.addWidget(self.scroll)

    def add_item(self, item):
        # --- ZMIANA: Usuwanie duplikatu i przesuwanie na górę ---
        to_remove = None
        for existing in self.items:
            if existing.ctype == item.ctype:
                if item.ctype == "text" and existing.text == item.text:
                    to_remove = existing
                    break
                elif item.ctype == "image" and existing.img_b64 == item.img_b64:
                    to_remove = existing
                    break
                    
        if to_remove:
            # Transferujemy właściwości z istniejącej karty
            item.pinned = to_remove.pinned
            item.label = to_remove.label
            self.items.remove(to_remove)
            
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
        self.flow.clear()
        visible = [it for it in self.items
                   if not self._filter
                   or self._filter in it.display().lower()
                   or self._filter in it.text.lower()]
        for it in sorted(visible, key=lambda x: (not x.pinned, -x.ts)):
            c = ClipCard(it)
            c.sig_click.connect(self.item_clicked)
            c.sig_remove.connect(self._on_remove)
            c.sig_pin.connect(self._on_pin)
            c.sig_edit.connect(self._on_edit)
            self.flow.addWidget(c)
            c.show()
        self.cont.updateGeometry()
        self.cont.adjustSize()

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
        self.config = self._load_cfg()
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
        if not DATA_FILE.exists(): return
        try:
            with open(DATA_FILE) as f: data = json.load(f)
            for td in data.get("tabs",[]):
                name  = td.get("name","Tab")
                items = [ClipItem.from_dict(d) for d in td.get("items",[])]
                idx = self._find_tab(name)
                if idx >= 0:
                    self._boards[idx].items = items; self._boards[idx]._rebuild()
                else:
                    self._add_tab(name, items)
        except Exception as e: print("load:", e)
        self._refresh_tabs()

    def _save_data(self):
        tabs = [{"name": n, "items": [it.to_dict() for it in self._boards[i].items]}
                for i, n in enumerate(self._tab_labels)]
        with open(DATA_FILE,"w") as f: json.dump({"tabs": tabs}, f, indent=2)

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
        tb = QHBoxLayout(tb_w); tb.setContentsMargins(12,0,8,0); tb.setSpacing(6)

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
            self._btn_pause.setText("stopped ⏸️")
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
        if item.ctype == "text":
            cb.setText(item.text)
            self._last_text = item.text.strip()
        elif item.ctype == "image" and item.img_b64:
            ba = QByteArray(base64.b64decode(item.img_b64))
            img = QImage.fromData(ba)
            if not img.isNull():
                mime = QMimeData()
                mime.setImageData(img)
                # Wymuszamy dodanie surowego formatu PNG, by nie utracić kanału alpha!
                mime.setData("image/png", ba)
                cb.setMimeData(mime)
                self._last_img = (ba.size(), "png") # Zabezpieczenie przed pętlą kopiowania
                self._last_text = ""
        self.hide_to_tray()

    # ── Clipboard ───────────────────────────────────────────────────────────

    def _setup_clipboard(self):
        self._last_update = 0  # Zmienna do zapobiegania spamowi zdarzeń
        cb = QGuiApplication.clipboard()
        # Zamiast QTimer, używamy sygnału systemowego - reaguje na sam fakt "Kopiuj"
        cb.dataChanged.connect(self._poll_clip)

    def _poll_clip(self):
        excel_on = hasattr(self, '_cb_excel') and self._cb_excel.isChecked()
        excel_dependent = self.config.get("excel_dependent", False)

        if self._is_paused: 
            if not (excel_on and not excel_dependent):
                return
            
        now = time.time()
        if now - getattr(self, '_last_update', 0) < 0.2:
            return
        self._last_update = now
        
        cb = QGuiApplication.clipboard()
        mime = cb.mimeData()
        
        t = cb.text().strip() if mime.hasText() else ""
        
        # --- LOGIKA: Tryb Excel ---
        if excel_on and t:
            if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
                t = t[1:-1]
                
        has_html_table = mime.hasHtml() and "<table" in mime.html().lower()
        is_excel_or_table = t and ("\t" in t or has_html_table)
        
        # PRIORYTET 1: Obraz bezpośredni (np. Kopiuj grafikę z przeglądarki, PrintScreen)
        if mime.hasImage():
            if mime.hasFormat("image/png"):
                ba = mime.data("image/png")
                self._boards[self._last_tab].add_item(
                    ClipItem("image", img_b64=base64.b64encode(bytes(ba)).decode())
                )
                self._save_data()
            else:
                img = cb.image()
                if not img.isNull():
                    ba = QByteArray()
                    buf = QBuffer(ba)
                    buf.open(QBuffer.WriteOnly)
                    img.save(buf, "PNG")
                    self._boards[self._last_tab].add_item(
                        ClipItem("image", img_b64=base64.b64encode(bytes(ba)).decode())
                    )
                    self._save_data()

        # PRIORYTET 2: Pliki z Eksploratora Windows (hasUrls)
        elif mime.hasUrls():
            added_image = False
            # Sprawdzamy wszystkie skopiowane pliki
            for url in mime.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = Path(file_path).suffix.lower()
                    # Jeśli plik ma rozszerzenie graficzne, wczytujemy go
                    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                        try:
                            img = QImage(file_path)
                            if not img.isNull():
                                ba = QByteArray()
                                buf = QBuffer(ba)
                                buf.open(QBuffer.WriteOnly)
                                # Zapisujemy jako PNG do bufora, aby zachować standard formatu w aplikacji
                                img.save(buf, "PNG")
                                self._boards[self._last_tab].add_item(
                                    ClipItem("image", img_b64=base64.b64encode(bytes(ba)).decode())
                                )
                                added_image = True
                        except Exception as e:
                            print(f"Błąd wczytywania pliku obrazu: {e}")
            
            # Zapisujemy dane, jeśli dodano chociaż jeden obraz
            if added_image:
                self._save_data()
            elif t:
                # Jeśli skopiowano pliki, ale żaden nie był obrazem (np. pliki .txt, .pdf), 
                # dodajemy ich ścieżki jako tekst
                self._boards[self._last_tab].add_item(ClipItem("text", text=t))
                self._save_data()

        # PRIORYTET 3: Tabela/Excel
        elif is_excel_or_table:
            self._boards[self._last_tab].add_item(ClipItem("text", text=t))
            self._save_data()
            
        # PRIORYTET 4: Standardowy tekst
        elif t:
            self._boards[self._last_tab].add_item(ClipItem("text", text=t))
            self._save_data()

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
        if not self.isVisible(): self._apply_geometry()
        self.show(); self.raise_(); self.activateWindow()

    def _apply_geometry(self):
        sc = QGuiApplication.primaryScreen().availableGeometry()
        mode = self.config.get("layout_mode","panel")
        if mode == "bar":
            bh = self.config.get("bar_height",300)
            self.setMinimumSize(sc.width(),bh); self.setMaximumSize(sc.width(),bh)
            self.move(sc.x(), sc.y()+sc.height()-bh)
        else:
            ph=self.config.get("panel_height",560); pw=self.config.get("panel_width",820)
            self.setMinimumSize(400,300); self.setMaximumSize(16777215,16777215)
            self.resize(pw,ph)
            self.move(sc.x()+sc.width()-pw-20, sc.y()+sc.height()-ph-60)

    # ── Settings ─────────────────────────────────────────────────────────

    def _settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            old_key = self.config.get("hotkey")
            self.config = dlg.get(); self._save_cfg()
            if self.config.get("hotkey") != old_key: self._setup_hotkey()
            self._apply_geometry(); self.show(); self.raise_(); self.activateWindow()

    def _quit(self):
        self._save_data(); self._save_cfg(); QApplication.quit()

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