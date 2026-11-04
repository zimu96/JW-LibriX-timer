"""Il monitor di rete del timer: un tasto piccolo nella barra e una finestra col QR.

Al posto del pannello laterale: nella barra, accanto a «visita sorvegliante»,
c'e' «Rete» con il numero di dispositivi collegati (nessun avviso quando uno
esce).  Il click, o la voce «Monitor di rete…» nei tre puntini, apre la
finestra con QR, indirizzo e il tasto Avvia/Ferma.
"""
import subprocess

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QDialog, QLabel, QPushButton, QToolBar,
                             QVBoxLayout)


def _gestore(finestra, carica: bool = True):
    """Il gestore di rete del timer: nasce al primo bisogno."""
    gestore = getattr(finestra, "network_display_manager", None)
    if gestore is None and carica:
        try:
            finestra.component_loader.get_component(
                "network_display_manager", blocking=True, timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        gestore = getattr(finestra, "network_display_manager", None)
    return gestore


def _acceso(gestore) -> bool:
    return bool(gestore and gestore.broadcaster and gestore.broadcaster.is_broadcasting)


def avvia(finestra) -> bool:
    from src.models.settings import NetworkDisplayMode
    gestore = _gestore(finestra)
    if gestore is None:
        return False
    if _acceso(gestore):
        return True
    imp = finestra.settings_controller.get_settings().network_display
    if imp.mode == NetworkDisplayMode.DISABLED:
        finestra.settings_controller.set_network_display_mode(NetworkDisplayMode.HTTP_AND_WS)
    imp = finestra.settings_controller.get_settings().network_display
    return gestore.start_network_display(imp.mode, imp.http_port, imp.ws_port)


def ferma(finestra) -> None:
    gestore = _gestore(finestra, carica=False)
    if _acceso(gestore):
        gestore.stop_network_display()


def _firewall_attivo() -> str:
    for nome in ("ufw", "firewalld"):
        try:
            if subprocess.run(["systemctl", "is-active", "--quiet", nome],
                              timeout=2).returncode == 0:
                return nome
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


class FinestraRete(QDialog):
    def __init__(self, finestra) -> None:
        super().__init__(finestra)
        self._finestra = finestra
        self.setWindowTitle("Monitor di rete")
        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(18, 16, 18, 16)
        colonna.setSpacing(10)

        self._qr = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        colonna.addWidget(self._qr)
        self._indirizzo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._indirizzo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._indirizzo.setStyleSheet("font-size: 15px; font-weight: bold;")
        colonna.addWidget(self._indirizzo)
        self._stato = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        colonna.addWidget(self._stato)
        self._nota = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._nota.setWordWrap(True)
        self._nota.setStyleSheet("color: gray;")
        colonna.addWidget(self._nota)
        self._firewall = QPushButton("Apri la porta nel firewall")
        self._firewall.clicked.connect(self._apri_porta)
        self._firewall.hide()
        colonna.addWidget(self._firewall)
        self._tasto = QPushButton()
        self._tasto.clicked.connect(self._alterna)
        colonna.addWidget(self._tasto)
        chiudi = QPushButton("Chiudi")
        chiudi.clicked.connect(self.accept)
        colonna.addWidget(chiudi)
        self.setMinimumWidth(360)

        self._orologio = QTimer(self)
        self._orologio.timeout.connect(self.aggiorna)
        self._orologio.start(1000)
        self.aggiorna()

    def _alterna(self) -> None:
        if _acceso(_gestore(self._finestra, carica=False)):
            ferma(self._finestra)
        else:
            if not avvia(self._finestra):
                self._nota.setText("Non parte: la porta e' gia' usata da un altro programma. "
                                   "Cambiala in Impostazioni > Network Display.")
        self.aggiorna()

    def _apri_porta(self) -> None:
        """Chiede la password di sistema (pkexec) e apre la porta del timer."""
        gestore = _gestore(self._finestra, carica=False)
        if gestore is None:
            return
        porta = str(gestore.broadcaster.port)
        comando = (["ufw", "allow", f"{porta}/tcp"] if _firewall_attivo() == "ufw"
                   else ["firewall-cmd", f"--add-port={porta}/tcp"])
        try:
            r = subprocess.run(["pkexec", *comando], capture_output=True, text=True, timeout=120)
            self._nota.setText("Porta aperta: riprova dal tablet." if r.returncode == 0
                               else f"Non riuscito: {(r.stderr or r.stdout).strip()[:120]}")
        except (OSError, subprocess.SubprocessError) as e:
            self._nota.setText(f"Non riuscito: {e}")

    def aggiorna(self) -> None:
        gestore = _gestore(self._finestra, carica=False)
        if not _acceso(gestore):
            self._qr.clear()
            self._indirizzo.setText("Spento")
            self._stato.setText("")
            self._nota.setText("Avvia per mostrare il timer su un tablet o un telefono "
                               "collegato alla stessa rete Wi-Fi.")
            self._tasto.setText("Avvia")
            self._firewall.hide()
            return
        from src.utils.qr_code_utility import generate_qr_code
        url = gestore.broadcaster.get_connection_url()
        if self._indirizzo.text() != url:
            self._qr.setPixmap(generate_qr_code(url, 220))
            self._indirizzo.setText(url)
            firewall = _firewall_attivo()
            porta = gestore.broadcaster.port
            self._nota.setText(
                "Inquadra il QR dal tablet (stessa rete Wi-Fi)." if not firewall else
                f"Se il tablet non apre la pagina il firewall ({firewall}) blocca la porta: "
                + (f"sudo ufw allow {porta}/tcp" if firewall == "ufw"
                   else f"sudo firewall-cmd --add-port={porta}/tcp"))
        n = gestore.broadcaster.get_client_count()
        self._stato.setText("Nessun dispositivo collegato" if n == 0
                            else f"{n} dispositiv{'o' if n == 1 else 'i'} collegat{'o' if n == 1 else 'i'}")
        self._tasto.setText("Ferma")
        self._firewall.setVisible(bool(_firewall_attivo()))


def apri(finestra) -> None:
    FinestraRete(finestra).exec()


def installa(finestra) -> None:
    """Toglie il pannello laterale e mette il tasto «Rete» nella barra."""
    dock = finestra.tools_dock
    dock.hide()
    dock.show = lambda *a: None
    dock.setVisible = lambda *a: None

    rete = getattr(finestra, "network_menu", None)
    if rete is not None:
        # Una voce sola, direttamente in Visualizza, al posto del sottomenu.
        for voce in finestra.menuBar().actions():
            if voce.menu() is not None and rete.menuAction() in voce.menu().actions():
                nuova = QAction("Monitor di rete…", finestra)
                nuova.triggered.connect(lambda: apri(finestra))
                voce.menu().insertAction(rete.menuAction(), nuova)
        rete.menuAction().setVisible(False)
    finestra._show_network_info = lambda: apri(finestra)
    finestra._toggle_network_display = lambda: apri(finestra)

    barra = finestra.findChild(QToolBar)
    if barra is None:
        return
    tasto = QPushButton("Rete")
    tasto.setToolTip("Mostra il timer su un tablet o un telefono")
    tasto.clicked.connect(lambda: apri(finestra))
    barra.addWidget(tasto)
    finestra.tasto_rete = tasto

    def testo() -> None:
        gestore = _gestore(finestra, carica=False)
        if _acceso(gestore):
            tasto.setText(f"Rete · {gestore.broadcaster.get_client_count()}")
        else:
            tasto.setText("Rete")

    orologio = QTimer(finestra)
    orologio.timeout.connect(testo)
    orologio.start(1500)
