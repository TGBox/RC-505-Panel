"""Dunkles Theme angelehnt an das Gerät: schwarzes Panel, Spur-LEDs rot (REC) / grün (PLAY)."""

ACCENT = "#e8b04a"
REC = "#e5484d"
PLAY = "#3dd68c"
ARMED = "#f5a524"
IDLE = "#3a3f47"

QSS = f"""
QWidget {{ background: #121417; color: #d9dde3; font-family: "Segoe UI", sans-serif; font-size: 10pt; }}
QFrame#TopBar, QFrame#Track {{ background: #1a1d22; border: 1px solid #262a31; border-radius: 8px; }}
QFrame#Track[dragActive="true"] {{ border: 2px dashed {ACCENT}; }}
QLabel#ModeBadge {{ padding: 4px 10px; border-radius: 10px; font-weight: 600; background: {IDLE}; }}
QLabel#ModeBadge[mode="LIVE"] {{ background: #123b2a; color: {PLAY}; }}
QLabel#ModeBadge[mode="STORAGE"] {{ background: #3b2f12; color: {ACCENT}; }}
QLabel#TrackTitle {{ font-size: 13pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#Led {{ min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px; border-radius: 7px; background: {IDLE}; }}
QLabel#Led[state="ARMED"] {{ background: {ARMED}; }}
QLabel#Led[state="RECORDING"] {{ background: {REC}; }}
QLabel#Led[state="DONE"], QLabel#Led[state="PLAY"] {{ background: {PLAY}; }}
QLabel#Led[state="FAILED"] {{ background: #8b1d22; }}
QLabel#Dropzone {{ border: 1px dashed #3a3f47; border-radius: 6px; padding: 10px; color: #8a919c; }}
QLabel#Muted {{ color: #8a919c; }}
QPushButton {{ background: #262a31; border: 1px solid #333842; border-radius: 6px; padding: 6px 10px; }}
QPushButton:hover {{ background: #2e333b; }}
QPushButton:disabled {{ color: #5b616b; background: #1d2025; }}
QPushButton#Drop {{ background: #3b2f12; border-color: {ACCENT}; color: {ACCENT}; font-weight: 700; }}
QPushButton#Drop:disabled {{ background: #1d2025; border-color: #333842; color: #5b616b; }}
QPushButton#Rec {{ color: {REC}; }}
QPlainTextEdit, QTreeView {{ background: #0e1013; border: 1px solid #262a31; border-radius: 6px; }}
QSpinBox, QDoubleSpinBox, QComboBox {{ background: #0e1013; border: 1px solid #333842; border-radius: 4px; padding: 2px 6px; }}
"""
