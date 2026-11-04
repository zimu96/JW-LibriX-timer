"""Lo stile del timer: i colori e gli angoli di JW LibriX.

Si applica solo alla finestra del timer.  I colori vengono dal tema
dell'app (Utility.tema), chiaro o scuro, e cambiano con lui.
"""


def foglio(chiaro: bool) -> str:
    from Utility import tema
    c = tema.colori(chiaro)
    r = tema.RAGGIO
    acc = tema.ACCENTO
    return f"""
QMainWindow {{ background-color: {c['sfondo']}; }}
QDialog {{ background-color: {c['sfondo']}; border: 1px solid {acc}; }}
QMenuBar {{ background-color: {c['sfondo']}; color: {c['testo']}; }}
QMenuBar::item:selected {{ background-color: {c['lavato']}; border-radius: {r}px; }}
QMenu {{ background-color: {c['pannello']}; color: {c['testo']};
        border: 1px solid {c['bordo']}; border-radius: {r}px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {c['lavato']}; }}
QMenu::separator {{ height: 1px; background: {c['bordo']}; margin: 4px 8px; }}
QToolBar {{ background-color: {c['sfondo']}; border: none;
           border-bottom: 1px solid {c['bordo']}; spacing: 6px; padding: 4px; }}
QStatusBar {{ background-color: {c['sfondo']}; color: {c['grigio']}; }}
QLabel {{ color: {c['testo']}; background: transparent; }}

QPushButton {{ background-color: {c['lavato']}; color: {c['testo']};
              border: 1px solid {c['bordo']}; border-radius: {r}px;
              padding: 6px 14px; }}
QPushButton:hover {{ background-color: {c['hover']}; }}
QPushButton:pressed {{ background-color: {acc}; color: #ffffff; }}
QPushButton:disabled {{ color: {c['spento']}; background-color: {c['pannello']}; }}
QPushButton:checked {{ background-color: {acc}; color: #ffffff; border: none; }}
QPushButton:default {{ background-color: {acc}; color: #ffffff; border: none; }}

QComboBox, QLineEdit, QSpinBox, QTimeEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c['pannello']}; color: {c['testo']};
    border: 1px solid {c['bordo']}; border-radius: {r}px; padding: 4px 8px; }}
QComboBox:disabled {{ background-color: {c['pannello']}; color: {c['grigio']};
    border: 1px solid {c['bordo']}; }}
QComboBox QAbstractItemView {{ background-color: {c['pannello']}; color: {c['testo']};
    selection-background-color: {acc}; selection-color: #ffffff; }}

QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget {{
    background-color: {c['sfondo']}; alternate-background-color: {c['pannello']};
    color: {c['testo']}; border: 1px solid {c['bordo']}; border-radius: {r}px;
    gridline-color: {c['griglia']}; }}
QTreeView::item, QTableView::item, QListWidget::item {{ padding: 4px; }}
QTreeView::item:selected, QTableView::item:selected, QListWidget::item:selected {{
    background-color: {acc}; color: #ffffff; }}
QHeaderView::section {{ background-color: {c['lavato']}; color: {c['testo']};
    border: none; border-bottom: 1px solid {c['bordo']}; padding: 6px; }}

QTabWidget::pane {{ border: 1px solid {c['bordo']}; border-radius: {r}px; }}
QTabBar::tab {{ background: {c['pannello']}; color: {c['testo']};
    padding: 7px 14px; border-top-left-radius: {r}px; border-top-right-radius: {r}px; }}
QTabBar::tab:selected {{ background: {c['lavato']}; color: {c['accentoTesto']}; }}
QGroupBox {{ border: 1px solid {c['bordo']}; border-radius: {r}px;
    margin-top: 12px; padding-top: 10px; color: {c['testo']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {c['accentoTesto']}; }}
QCheckBox, QRadioButton {{ color: {c['testo']}; }}
QDockWidget {{ color: {c['testo']}; }}
QDockWidget::title {{ background: {c['lavato']}; padding: 6px; }}
/* le cifre del timer: stessi colori del monitor del timer */
QLabel#digitalTimerRunning {{ color: #4ade80; font-weight: bold; }}
QLabel#digitalTimerWarning {{ color: #fbbf24; font-weight: bold; }}
QLabel#digitalTimerDanger {{ color: #f87171; font-weight: bold; }}
QLabel#digitalTimerPaused {{ color: #60a5fa; font-weight: bold; }}
QLabel#digitalTimerTransition {{ color: #c4a1ff; font-weight: bold; }}
QLabel#digitalTimerStopped {{ color: {c['testo']}; font-weight: bold; }}
QToolTip {{ background-color: {c['pannello']}; color: {c['testo']};
    border: 1px solid {c['bordo']}; }}
"""
