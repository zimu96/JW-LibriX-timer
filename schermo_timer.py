"""Il monitor del timer per chi parla: cifre grandi, parte corrente, prossima parte.

Sostituisce la finestra `SecondaryDisplay` del timer originale con la stessa
interfaccia verso il resto del timer (`info_label1`, `info_label2`,
`show_clock`, `show_countdown`, `_update_countdown`,
`show_on_configured_screen_safely`), ma con:
    - tutto in italiano (anche i testi che il timer manda in inglese)
    - lo stile di JW LibriX
    - cifre che occupano lo schermo
    - nessun dato tecnico (ora di fine prevista ecc.)
"""
import re
from datetime import date, datetime

from PyQt6.QtCore import QLocale, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.models.timer import TimerState

SFONDO = "#000000"
ACCENTO = "#a77fd4"
BIANCO = "#ffffff"
VERDE = "#4ade80"
ARANCIO = "#fbbf24"
ROSSO = "#f87171"
BLU = "#60a5fa"
VIOLA_CHIARO = "#c4a1ff"

_TRADUZIONI = (
    (r"^\s*next part\s*:\s*(.*)$", lambda m: f"Prossima parte: {m.group(1)}"),
    (r"^\s*last part\s*$", lambda m: "Ultima parte"),
    (r"^\s*meeting (ended|completed)\s*$", lambda m: "Adunanza terminata"),
    (r"^\s*meeting conclusion\s*$", lambda m: "Conclusione"),
    (r"^\s*meeting starts now!?\s*$", lambda m: "L'adunanza inizia ora!"),
    (r"^\s*meeting starts in\s*(.*)$", lambda m: f"L'adunanza inizia tra {m.group(1)}"),
)


def in_italiano(testo: str) -> str:
    """I testi che il timer manda in inglese diventano italiano."""
    for modello, f in _TRADUZIONI:
        m = re.match(modello, testo, re.IGNORECASE)
        if m:
            return f(m)
    return testo


class _Etichetta(QLabel):
    """Etichetta che il resto del timer puo' riempire come la vecchia.

    Il timer scrive testo e `setStyleSheet("color: ...; font-size: 60px")`.
    Qui il testo passa dalla traduzione e dallo stile resta solo il colore:
    la grandezza la decide il monitor, in base allo schermo.
    """

    def __init__(self, colore: str, padre=None) -> None:
        super().__init__(padre)
        self._colore = colore
        self._pixel = 20
        self._famiglia = ""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._applica()

    def setText(self, testo: str) -> None:  # noqa: N802
        testo = in_italiano(testo or "")
        super().setText(testo)
        self.setVisible(bool(testo))
        finestra = self.window()
        if hasattr(finestra, "_adatta_caratteri") and self.parent() is not None:
            finestra._adatta_caratteri()

    def setStyleSheet(self, stile: str) -> None:  # noqa: N802
        m = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{3,8})", stile or "")
        if m:
            self._colore = m.group(1)
        self._applica()

    def colore(self, colore: str) -> None:
        self._colore = colore
        self._applica()

    def pixel(self, n: int, famiglia: str = "") -> None:
        """Grandezza dei caratteri: va nello stile, che altrimenti la annulla."""
        self._pixel = n
        self._famiglia = famiglia
        self._applica()

    def _applica(self) -> None:
        fam = f"font-family:'{self._famiglia}';" if self._famiglia else ""
        super().setStyleSheet(
            f"color:{self._colore};background:transparent;border:none;"
            f"font-weight:bold;font-size:{self._pixel}px;{fam}")


class MonitorTimer(QWidget):
    def __init__(self, timer_controller, settings_controller, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.timer_controller = timer_controller
        self.settings_controller = settings_controller
        self.show_clock = True
        self.show_countdown = True
        self._show_countdown = True
        self.next_part = None
        self._schermo = None

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Timer adunanza")
        self.setStyleSheet(f"MonitorTimer{{background:{SFONDO};}}")
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QColor(SFONDO))
        self.setPalette(p)

        self.parte_label = _Etichetta(ACCENTO)
        self.timer_label = _Etichetta(BIANCO)
        self.timer_label.setWordWrap(False)
        self.timer_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Expanding)
        self.info_label1 = _Etichetta(BIANCO)
        self.info_label2 = _Etichetta(ACCENTO)
        self.timer_view = None

        riga = QVBoxLayout(self)
        riga.setContentsMargins(40, 24, 40, 24)
        riga.setSpacing(6)
        riga.addWidget(self.parte_label, 0)
        riga.addWidget(self.timer_label, 1)
        riga.addWidget(self.info_label1, 0)
        riga.addWidget(self.info_label2, 0)

        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._famiglia_cifre = ""

        self._collega()
        self._adatta_caratteri()
        self._mostra_ora_e_data()
        # Le parti possono cambiare mentre l'adunanza e' in corso (titolo
        # scritto a mano, visita del sorvegliante): il monitor le rilegge da solo.
        self._rilettura = QTimer(self)
        self._rilettura.timeout.connect(self._rileggi_titoli)
        self._rilettura.start(500)

    # ------------------------------------------------------------------
    def _collega(self) -> None:
        c = self.timer_controller
        c.timer.time_updated.connect(self._update_time)
        c.timer.state_changed.connect(self._update_timer_state)
        c.timer.current_time_updated.connect(self._update_current_time)
        c.part_changed.connect(self._part_changed)
        c.transition_started.connect(self._transition_started)
        c.meeting_started.connect(self._meeting_started)
        c.meeting_ended.connect(self._meeting_ended)
        c.meeting_countdown_updated.connect(self._update_countdown)

    def _rileggi_titoli(self) -> None:
        c = self.timer_controller
        if self._fermo() or self.show_clock or c.timer.state == TimerState.TRANSITION:
            return
        parti = c.parts_list
        i = c.current_part_index
        if not (0 <= i < len(parti)):
            return
        titolo = parti[i].title or ""
        prossima = f"Prossima parte: {parti[i + 1].title}" if i + 1 < len(parti) else "Ultima parte"
        if self.parte_label.text() != in_italiano(titolo):
            self.parte_label.setText(titolo)
        if self.info_label1.text() != prossima:
            self.info_label1.setText(prossima)
            self.info_label1.colore(BIANCO)

    def _fermo(self) -> bool:
        return self.timer_controller.timer.state == TimerState.STOPPED

    # --- testo ----------------------------------------------------------
    def _update_time(self, secondi: int) -> None:
        if self._fermo():
            return
        if secondi < 0:
            testo = f"-{abs(secondi) // 60:02d}:{abs(secondi) % 60:02d}"
            colore = ROSSO
        else:
            testo = f"{secondi // 60:02d}:{secondi % 60:02d}"
            colore = ARANCIO if secondi <= 60 else VERDE
        if self.timer_label.text() != testo:
            self.timer_label.setText(testo)
        self.timer_label.colore(colore)

    def _update_timer_state(self, stato) -> None:
        if stato == TimerState.PAUSED:
            self.timer_label.colore(BLU)
        elif stato == TimerState.TRANSITION:
            self.timer_label.colore(VIOLA_CHIARO)

    def _update_current_time(self, ora: str) -> None:
        if self._fermo() and self.show_clock:
            self.timer_label.setText(ora)
            self.timer_label.colore(BIANCO)
            self._mostra_data()

    def _mostra_ora_e_data(self) -> None:
        self.timer_label.setText(
            datetime.now().strftime("%H:%M:%S"))
        self._mostra_data()

    def _mostra_data(self) -> None:
        if self._fermo() and self.show_clock:
            oggi = QLocale("it").toString(date.today(), "dddd d MMMM yyyy")
            if self.info_label2.text() != oggi:
                self.info_label2.setText(oggi)
                self.info_label2.colore(ACCENTO)

    def _update_countdown(self, secondi: int, messaggio: str) -> None:
        """Prima dell'adunanza: quanto manca all'inizio."""
        if not self._fermo() or self.timer_controller.current_part_index >= 0:
            self.show_countdown = False
            return
        if secondi > 0 and getattr(self, "show_countdown", True):
            self.info_label1.setText(messaggio)
            self.info_label1.colore(BLU)
            self.parte_label.setText("")
        self._mostra_data()

    def _part_changed(self, parte, indice) -> None:
        self.show_countdown = False
        self.parte_label.setText(getattr(parte, "title", "") or "")
        parti = self.timer_controller.parts_list
        if indice + 1 < len(parti):
            self.next_part = parti[indice + 1]
            self.info_label1.setText(f"Prossima parte: {self.next_part.title}")
        else:
            self.next_part = None
            self.info_label1.setText("Ultima parte")
        self.info_label1.colore(BIANCO)
        self.info_label2.setText("")
        self._adatta_caratteri()

    def _transition_started(self, messaggio) -> None:
        if messaggio:
            self.parte_label.setText(str(messaggio))
        self.timer_label.colore(VIOLA_CHIARO)

    def _meeting_started(self) -> None:
        self.show_clock = False
        self.show_countdown = False
        self.info_label1.setText("")
        self.info_label2.setText("")
        indice = max(0, self.timer_controller.current_part_index)
        parti = self.timer_controller.parts_list
        if 0 <= indice < len(parti):
            self._part_changed(parti[indice], indice)

    def _meeting_ended(self) -> None:
        self.show_clock = True
        self.show_countdown = False
        self.parte_label.setText("")
        self.info_label1.setText("Adunanza terminata")
        self.info_label1.colore(BIANCO)
        self.info_label2.setText("")

    # --- grandezza dei caratteri -----------------------------------------
    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._adatta_caratteri()

    def _adatta_caratteri(self) -> None:
        """Le dimensioni si misurano sul testo: non devono mai uscire dallo schermo."""
        h, w = max(1, self.height()), max(1, self.width())
        larghezza = max(1, w - 100)

        def adatta(etichetta, px_max: int, famiglia: str = "", righe: int = 1):
            px = max(10, px_max)
            testo = etichetta.text() or "00:00:00"
            while px > 10:
                f = QFont(famiglia or etichetta.font().family())
                f.setBold(True)
                f.setPixelSize(px)
                fm = QFontMetrics(f)
                ok_largh = fm.horizontalAdvance(testo) * (1 if righe == 1 else 1) <= larghezza \
                    if righe == 1 else \
                    fm.boundingRect(0, 0, larghezza, 10000, Qt.TextFlag.TextWordWrap, testo).height() \
                    <= fm.lineSpacing() * righe
                if ok_largh:
                    break
                px -= max(1, px // 25)
            etichetta.pixel(px, famiglia)

        adatta(self.timer_label, int(h * 0.36), self._famiglia_cifre)
        adatta(self.parte_label, int(h * 0.07), righe=2)
        adatta(self.info_label1, int(h * 0.055), righe=2)
        adatta(self.info_label2, int(h * 0.05), righe=1)

    # --- posizione --------------------------------------------------------
    def _schermo_scelto(self):
        d = self.settings_controller.get_settings().display
        nome = getattr(d, "secondary_screen_name", "") or ""
        for s in QApplication.screens():
            if nome and s.name() == nome:
                return s
        return None

    def show_on_configured_screen_safely(self) -> None:
        """Tutto schermo sullo schermo scelto nelle impostazioni dell'app."""
        schermo = self._schermo_scelto()
        if schermo is None:
            return
        self._schermo = schermo
        if (self.isVisible() and self.isFullScreen()
                and self.windowHandle() is not None
                and self.windowHandle().screen() is schermo):
            return
        self.metti_a_schermo_intero(schermo)

    def metti_a_schermo_intero(self, schermo=None) -> None:
        schermo = schermo or self._schermo or self._schermo_scelto()
        if schermo is None:
            return
        self._schermo = schermo
        self.winId()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(schermo)
        self.setGeometry(schermo.geometry())
        self.schermo_intero()
        QTimer.singleShot(250, self._rimetti)

    def schermo_intero(self) -> None:
        """Come `showFullScreen()`, ma senza chiedere il fuoco.

        `showFullScreen()` alla fine chiede anche di attivare la finestra, e
        questa il fuoco non lo prende di proposito (`WindowDoesNotAcceptFocus`):
        Qt allora scrive l'avviso «requestActivate() called for ...».  Se capita
        mentre la schermata di avvio dell'app sta ancora lavorando, la schermata
        si ferma su «messaggi con problemi» e aspetta «Ignora e parti».
        """
        stato = self.windowState() & ~(Qt.WindowState.WindowMinimized
                                       | Qt.WindowState.WindowMaximized)
        self.setWindowState(stato | Qt.WindowState.WindowFullScreen)
        self.setVisible(True)

    def _rimetti(self) -> None:
        """Dopo showFullScreen Qt puo' rimettere lo schermo di prima."""
        s = self._schermo
        try:
            if s is None or not self.isVisible() or not self.isFullScreen():
                return
            if self.windowHandle() is not None and self.windowHandle().screen() is not s:
                self.windowHandle().setScreen(s)
                self.setGeometry(s.geometry())
                self.schermo_intero()
        except RuntimeError:
            pass

    def _on_settings_updated(self) -> None:
        pass

    def paintEvent(self, evento) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(SFONDO))
        p.end()
