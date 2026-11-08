"""Correzioni di 1.0.0.1: piccoli difetti di uso trovati in un'adunanza vera.

Tutto si applica una volta sola da `adattamento.applica()`.

    - i tasti non restano mai a mezz'aria (lampeggio che non si ferma)
    - le scritte sotto il timer si rimpiccioliscono per starci, senza tagliarsi
    - la finestra puo' stare anche a mezzo schermo: il pannello Contenuti e il
      titolo dell'adunanza non allargano piu' la finestra oltre lo spazio che c'e'
    - «Ritardo» e l'avviso di partenza in ritardo sono in italiano
    - il monitor del timer torna da solo sullo schermo scelto
"""
import re

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (QApplication, QGraphicsOpacityEffect, QLabel, QSizePolicy,
                             QWidget)

_applicato = False

_TASTI = ("start_button", "pause_resume_button", "prev_button", "next_button",
          "decrease_button", "increase_button")


# ----------------------------------------------------------------------
# tasti
# ----------------------------------------------------------------------
def ferma_pulsazioni(finestra, *_args) -> None:
    """Ferma il lampeggio dei tasti (promemoria) e rimette tutto visibile.

    Il lampeggio di «Successivo» (parte scaduta) restava acceso anche dopo
    aver cambiato parte in altro modo, e il tasto spariva a intermittenza.
    Con il timer in pausa i tasti sono volutamente sbiaditi: li lascia stare.
    """
    from src.models.timer import TimerState
    in_pausa = finestra.timer_controller.timer.state == TimerState.PAUSED
    for nome in _TASTI:
        tasto = getattr(finestra, nome, None)
        if tasto is None:
            continue
        for animazione in list(getattr(tasto, "_pulse_animations", [])):
            try:
                animazione.stop()
            except RuntimeError:
                pass
        if hasattr(tasto, "_pulse_animations"):
            tasto._pulse_animations.clear()
        effetto = tasto.graphicsEffect()
        if isinstance(effetto, QGraphicsOpacityEffect) and not (in_pausa and nome != "start_button"):
            effetto.setOpacity(1.0)
            tasto.setGraphicsEffect(None)


def _stato_cambiato(finestra, stato) -> None:
    from src.models.timer import TimerState
    # Con il tempo scaduto il promemoria di «Successivo» e' voluto.
    if stato in (TimerState.RUNNING, TimerState.STOPPED, TimerState.TRANSITION):
        ferma_pulsazioni(finestra)


def _avviso_ritardo(finestra, ritardo: int, tolti: int) -> None:
    def tempo(s: int) -> str:
        m, sec = divmod(int(s), 60)
        return f"{m} min {sec} s" if m else f"{sec} s"

    if tolti >= ritardo:
        testo = (f"Sei partito con {tempo(ritardo)} di ritardo. Li ho tolti alle parti "
                 "(cantici e preghiere restano uguali), così finisci in orario.")
    elif tolti > 0:
        testo = (f"Sei partito con {tempo(ritardo)} di ritardo. Ho tolto {tempo(tolti)} "
                 "alle parti (cantici e preghiere restano uguali): il resto non si può recuperare.")
    else:
        testo = (f"Sei partito con {tempo(ritardo)} di ritardo: le parti sono già brevi, "
                 "non si può togliere altro.")
    finestra._show_toast_notification("Adunanza iniziata in ritardo", testo, icon="toast-adjust")


# ----------------------------------------------------------------------
# scritte che si adattano
# ----------------------------------------------------------------------
def _adatta_scritta(etichetta: QLabel, massimo: int, minimo: int, righe: int) -> None:
    """Fa stare il testo (anche a capo) in `righe` righe, rimpicciolendolo se serve."""
    testo = etichetta.text() or ""
    chiave = (testo, etichetta.width(), massimo, righe)
    if getattr(etichetta, "_chiave_adatta", None) == chiave:
        return
    etichetta._chiave_adatta = chiave
    larghezza = max(80, etichetta.width() - 6)
    px = massimo
    while True:
        f = QFont(etichetta.font())
        f.setBold(True)
        f.setPixelSize(px)
        fm = QFontMetrics(f)
        rettangolo = fm.boundingRect(0, 0, larghezza, 100000, int(Qt.TextFlag.TextWordWrap), testo)
        if rettangolo.height() <= fm.lineSpacing() * righe + 2 or px <= minimo:
            break
        px -= 1
    foglio = etichetta.styleSheet()
    if re.search(r"font-size:\s*\d+px", foglio):
        nuovo = re.sub(r"font-size:\s*\d+px", f"font-size: {px}px", foglio)
    else:
        nuovo = f"{foglio} font-size: {px}px;"
    if nuovo != foglio:
        etichetta.setStyleSheet(nuovo)
    fm = QFontMetrics(_font_con(etichetta, px))
    alto = fm.boundingRect(0, 0, larghezza, 100000, int(Qt.TextFlag.TextWordWrap), testo).height()
    etichetta.setMinimumHeight(min(alto, fm.lineSpacing() * (righe + 1)) + 4 if testo else 0)


def _font_con(etichetta: QLabel, px: int) -> QFont:
    f = QFont(etichetta.font())
    f.setBold(True)
    f.setPixelSize(px)
    return f


def _adatta_titoli(vista) -> None:
    try:
        # grandezza di prima (18 e 16 px): si rimpiccioliscono solo se non ci stanno
        _adatta_scritta(vista.part_label, 18, 11, 3)
        _adatta_scritta(vista.countdown_label, 16, 10, 3)
    except RuntimeError:
        pass          # il widget non c'e' piu'


# ----------------------------------------------------------------------
# il monitor torna da solo sullo schermo scelto
# ----------------------------------------------------------------------
def _controlla_monitor(finestra) -> None:
    """Se il monitor del timer dovrebbe esserci e non c'e' (schermo comparso dopo
    l'avvio), lo rimette.  Mai mentre l'app si sta chiudendo o riavviando."""
    try:
        if getattr(finestra, "_in_chiusura", False) or QApplication.closingDown():
            return
        d = finestra.settings_controller.get_settings().display
        if not d.use_secondary_screen or not d.secondary_screen_name:
            return
        schermo = next((s for s in QApplication.screens()
                        if s.name() == d.secondary_screen_name), None)
        if schermo is None:
            return
        mon = getattr(finestra, "secondary_display", None)
        if mon is None:
            finestra._ensure_single_secondary_display()
            finestra._update_secondary_display_label()
    except (RuntimeError, AttributeError):
        pass


def applica() -> None:
    global _applicato
    if _applicato:
        return
    _applicato = True
    import src.views.main_window as mw
    import src.views.meeting_view as mv
    import src.views.timer_view as tv

    # --- TimerView: le due scritte sotto le cifre ---------------------------
    originale_tv = tv.TimerView.__init__

    def tv_init(self, *a, **k):
        originale_tv(self, *a, **k)
        # le scritte non decidono la larghezza della finestra
        for et in (self.part_label, self.countdown_label):
            et.setMinimumWidth(1)
        self.timer_label.setMinimumWidth(1)       # le cifre si rimpiccioliscono, non allargano
        self.timer_panel.setMinimumWidth(1)
        controllo = QTimer(self)
        controllo.timeout.connect(lambda: _adatta_titoli(self))
        controllo.start(250)
        self._adatta_titoli_timer = controllo

    tv.TimerView.__init__ = tv_init

    for nome in ("_create_digital_display",):
        orig = getattr(tv.TimerView, nome)

        def con_policy(self, *a, _orig=orig, **k):
            r = _orig(self, *a, **k)
            if hasattr(self, "timer_label"):
                self.timer_label.setMinimumWidth(1)
            return r

        setattr(tv.TimerView, nome, con_policy)

    # --- titolo dell'adunanza: va a capo invece di allargare la finestra -----
    originale_mv = mv.MeetingView.__init__

    def mv_init(self, *a, **k):
        originale_mv(self, *a, **k)
        etichetta = getattr(self, "title_label", None)
        if etichetta is not None:
            etichetta.setMinimumWidth(1)      # a mezzo schermo si taglia a destra, non allarga

    mv.MeetingView.__init__ = mv_init

    # --- finestra principale ------------------------------------------------
    def ritardo_in_italiano(self, totale):
        if totale > 0:
            minuti, secondi = divmod(int(totale), 60)
            colore = "orange" if totale < 60 else "red"
            self.meeting_overtime_label.setText(f"Ritardo: {minuti:02d}:{secondi:02d}")
            self.meeting_overtime_label.setStyleSheet(f"color: {colore}; font-weight: bold;")
            self.meeting_overtime_label.setVisible(True)

    mw.MainWindow._meeting_overtime = ritardo_in_italiano

    originale_mw = mw.MainWindow.__init__

    def mw_init(self, *a, **k):
        originale_mw(self, *a, **k)
        # le scritte della barra in basso si accorciano invece di allargare la finestra
        for nome in ("current_part_label", "current_meeting_label",
                     "predicted_end_time_label", "meeting_overtime_label"):
            et = getattr(self, nome, None)
            if et is not None:
                et.setMinimumWidth(1)
        c = self.timer_controller
        c.part_changed.connect(lambda *_: ferma_pulsazioni(self))
        c.meeting_ended.connect(lambda: ferma_pulsazioni(self))
        c.timer.state_changed.connect(lambda stato: _stato_cambiato(self, stato))
        c.late_start_absorbed.connect(lambda r, t: _avviso_ritardo(self, r, t))
        # monitor: solo all'avvio (lo schermo puo' comparire dopo) e quando compare
        # uno schermo nuovo; mai in chiusura.
        self._in_chiusura = False
        QApplication.instance().aboutToQuit.connect(lambda: setattr(self, "_in_chiusura", True))
        giro = QTimer(self)
        giro.timeout.connect(lambda: _controlla_monitor(self))
        giro.start(4000)
        QTimer.singleShot(60000, giro.stop)
        self._giro_monitor = giro
        QApplication.instance().screenAdded.connect(
            lambda *_: QTimer.singleShot(1500, lambda: _controlla_monitor(self)))

    mw.MainWindow.__init__ = mw_init

    chiusura_originale = mw.MainWindow.closeEvent

    def chiusura(self, evento):
        self._in_chiusura = True
        chiusura_originale(self, evento)

    mw.MainWindow.closeEvent = chiusura
