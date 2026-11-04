"""Il monitor del timer: i due tasti a scomparsa e la scelta dello schermo.

Stessa logica del monitor multimediale di JW LibriX (SubViews/SchermoEsterno):
passando il mouse sopra la finestra compaiono, in alto a destra, due tasti.
    - riduci / ingrandisci: tutto schermo <-> finestra piccola al centro
    - chiudi: spegne il monitor del timer
Quando il mouse esce, i tasti spariscono in dissolvenza.

La finestra del timer (src/views/secondary_display.py) non e' modificata:
i tasti le si aggiungono da fuori con `installa_comandi`.
"""
from PyQt6.QtCore import (QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt,
                          QTimer, pyqtProperty)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

#: Chiamata quando l'utente chiude il monitor dal tasto X.  La imposta l'app.
al_chiudere = None


class _Comandi(QWidget):
    """I due tasti rotondi, disegnati a mano.

    Niente QGraphicsOpacityEffect: su una finestra a tutto schermo riempiva
    il terminale di avvisi QPainter.  La dissolvenza e' una proprieta' che
    il disegno legge.
    """
    LATO = 34
    GAP = 6

    def __init__(self, padre) -> None:
        super().__init__(padre)
        self.setMouseTracking(True)
        self.setFixedSize(self.LATO * 2 + self.GAP, self.LATO)
        self._opacita = 0.0
        self._sopra = -1
        self.su_misura = None
        self.su_chiudi = None
        self.tip_misura = "Riduci la finestra"
        self._pix = [self._pixmap("arrow.up.left.and.arrow.down.right"),
                     self._pixmap("xmark")]

    @staticmethod
    def _pixmap(simbolo: str):
        try:
            from Utility.Stuff import icon
            i = icon(simbolo, "#ffffff", 20)
            if not i.isNull():
                return i.pixmap(20, 20)
        except Exception:  # noqa: BLE001
            pass
        return None

    def opacita(self) -> float:
        return self._opacita

    def imposta_opacita(self, v: float) -> None:
        self._opacita = v
        self.update()

    opacity = pyqtProperty(float, opacita, imposta_opacita)

    def _indice(self, x: int) -> int:
        for i in range(2):
            ini = i * (self.LATO + self.GAP)
            if ini <= x <= ini + self.LATO:
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        i = self._indice(int(e.position().x()))
        if i != self._sopra:
            self._sopra = i
            self.setToolTip(self.tip_misura if i == 0 else
                            "Chiudi il monitor del timer" if i == 1 else "")
            self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._sopra = -1
        self.update()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        i = self._indice(int(e.position().x()))
        f = self.su_misura if i == 0 else self.su_chiudi if i == 1 else None
        if f:
            f()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacita)
        for i in range(2):
            x = i * (self.LATO + self.GAP)
            p.setPen(QColor(255, 255, 255, 90))
            p.setBrush(QColor(110, 70, 160, 235) if i == self._sopra
                       else QColor(40, 40, 40, 215))
            p.drawEllipse(x + 1, 1, self.LATO - 2, self.LATO - 2)
            pix = self._pix[i]
            if pix is not None:
                p.drawPixmap(x + (self.LATO - pix.width()) // 2,
                             (self.LATO - pix.height()) // 2, pix)
            else:
                p.setPen(QColor("white"))
                p.drawText(x, 0, self.LATO, self.LATO, Qt.AlignmentFlag.AlignCenter,
                           "\u2922" if i == 0 else "\u2715")
        p.end()


class ComandiMonitor(QObject):
    """I tasti compaiono quando il mouse si muove sulla finestra.

    Non basta l'evento "il mouse e' entrato" sulla finestra: sopra la finestra
    ci sono le etichette, che lo ricevono per prime, e su alcuni desktop la
    finestra non lo riceve mai.  Quindi si ascolta il movimento su tutta la
    finestra e su tutto quello che c'e' dentro; i tasti spariscono quando il
    mouse esce o sta fermo per un po'.
    """
    ATTESA_MS = 2500

    def __init__(self, display) -> None:
        super().__init__(display)
        self._d = display
        self._piccola = False
        self._comandi = _Comandi(display)
        self._comandi.su_misura = self._cambia_misura
        self._comandi.su_chiudi = self._chiudi_monitor
        self._comandi.setVisible(False)
        self._animazione = QPropertyAnimation(self._comandi, b"opacity", self)
        self._animazione.setDuration(180)
        self._animazione.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._riposo = QTimer(self)
        self._riposo.setSingleShot(True)
        self._riposo.timeout.connect(self._sparisci)
        self._ascolta(display)
        for figlio in display.findChildren(QWidget):
            if figlio is not self._comandi:
                self._ascolta(figlio)

    def _ascolta(self, widget) -> None:
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def eventFilter(self, oggetto, evento) -> bool:  # noqa: N802
        t = evento.type()
        if t in (QEvent.Type.Enter, QEvent.Type.MouseMove, QEvent.Type.HoverMove,
                 QEvent.Type.MouseButtonPress):
            self._mostra()
        elif t == QEvent.Type.Leave and oggetto is self._d:
            self._sparisci()
        elif t in (QEvent.Type.Resize, QEvent.Type.Show) and oggetto is self._d:
            self._in_angolo()
        return False

    def _mostra(self) -> None:
        self._comandi.setVisible(True)
        self._in_angolo()
        self._comandi.raise_()
        if self._comandi.opacita() < 0.99:
            self._dissolvenza(1.0)
        self._riposo.start(self.ATTESA_MS)

    def _sparisci(self) -> None:
        self._riposo.stop()
        if self._comandi.underMouse():
            self._riposo.start(self.ATTESA_MS)
            return
        self._dissolvenza(0.0)
        QTimer.singleShot(220, self._nascondi)

    def _nascondi(self) -> None:
        try:
            if self._comandi.opacita() <= 0.01:
                self._comandi.setVisible(False)
        except RuntimeError:
            pass

    def _dissolvenza(self, valore: float) -> None:
        self._animazione.stop()
        self._animazione.setStartValue(self._comandi.opacita())
        self._animazione.setEndValue(valore)
        self._animazione.start()

    def _in_angolo(self) -> None:
        self._comandi.move(max(0, self._d.width() - self._comandi.width() - 16), 16)

    def _cambia_misura(self) -> None:
        d = self._d
        if self._piccola:
            self._piccola = False
            d.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            d.metti_a_schermo_intero()
            self._comandi.tip_misura = "Riduci la finestra"
            return
        self._piccola = True
        schermo = d.screen() or QApplication.primaryScreen()
        g = schermo.geometry()
        w, h = max(240, g.width() // 3), max(135, g.height() // 3)
        x, y = g.x() + (g.width() - w) // 2, g.y() + (g.height() - h) // 2
        d.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        d.showNormal()
        d.setGeometry(x, y, w, h)
        QTimer.singleShot(0, lambda: d.setGeometry(x, y, w, h))
        self._comandi.tip_misura = "Ingrandisci a tutto schermo"

    def _chiudi_monitor(self) -> None:
        finestra = self._d.parent()
        if finestra is not None:
            spegni(finestra)
        if al_chiudere is not None:
            al_chiudere()


def installa_comandi(display) -> None:
    ComandiMonitor(display)


def _salva(finestra, nome: str | None) -> None:
    d = finestra.settings_controller.get_settings().display
    if nome:
        schermi = QApplication.screens()
        d.use_secondary_screen = True
        d.secondary_screen_name = nome
        d.secondary_screen_index = next(
            (i for i, s in enumerate(schermi) if s.name() == nome), None)
    else:
        d.use_secondary_screen = False
    finestra.settings_controller.save_settings()


def spegni(finestra) -> None:
    _salva(finestra, None)
    finestra._cleanup_secondary_display()
    finestra._update_secondary_display_label()
    if hasattr(finestra, "toggle_secondary_action"):
        finestra.toggle_secondary_action.setChecked(False)


def applica_schermo(finestra, nome: str | None) -> None:
    """Mette il monitor del timer sullo schermo `nome`, o lo spegne con None."""
    if not nome:
        spegni(finestra)
        return
    _salva(finestra, nome)
    # se c'era gia', si ricrea: cosi' va sullo schermo nuovo
    finestra._cleanup_secondary_display()
    finestra._ensure_single_secondary_display()
    finestra._update_secondary_display_label()
    if hasattr(finestra, "toggle_secondary_action"):
        finestra.toggle_secondary_action.setChecked(True)
