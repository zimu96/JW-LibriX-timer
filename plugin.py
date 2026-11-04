"""Plugin Timer per JW LibriX: l'OnTime Meeting Timer dentro la sezione Timer.

L'app chiama `crea_schermata()` e riceve un widget da mettere nella sezione.
Il resto del timer (src/, assets/, ...) e' quello originale, non toccato.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Librerie opzionali messe dentro il plugin (libs/): hanno la precedenza
# sul sistema solo se il sistema non le ha.
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
if (BASE / "libs").is_dir() and str(BASE / "libs") not in sys.path:
    sys.path.append(str(BASE / "libs"))


def _librerie_mancanti() -> list[str]:
    mancanti = []
    for modulo, pacchetto in (("bs4", "beautifulsoup4"), ("dateparser", "dateparser"),
                              ("requests", "requests"), ("websockets", "websockets"),
                              ("qrcode", "qrcode"), ("dateutil", "python-dateutil"),
                              ("platformdirs", "platformdirs"), ("jsonschema", "jsonschema")):
        try:
            __import__(modulo)
        except ImportError:
            mancanti.append(pacchetto)
    return mancanti


def _messaggio(testo: str):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    etichetta = QLabel(testo)
    etichetta.setAlignment(Qt.AlignmentFlag.AlignCenter)
    etichetta.setWordWrap(True)
    return etichetta


def _cartella_dati() -> Path:
    """I dati del timer stanno nei dati di JW LibriX (dati/timer)."""
    import shutil

    from Utility.Structures.Paths import Paths
    nuova = Path(Paths.root) / "timer"
    vecchia = Path.home() / ".ontime"
    if not nuova.exists() and vecchia.is_dir():
        try:
            shutil.copytree(vecchia, nuova)       # una volta sola, dalla vecchia posizione
        except OSError:
            pass
    nuova.mkdir(parents=True, exist_ok=True)
    # Versione 2: le date delle settimane in italiano erano sbagliate e le
    # adunanze gia' salvate vanno rifatte, una volta sola.
    segno = nuova / ".dati_v2"
    if not segno.exists():
        shutil.rmtree(nuova / "meetings", ignore_errors=True)
        shutil.rmtree(nuova / "cache", ignore_errors=True)
        (nuova / "meetings").mkdir(exist_ok=True)
        segno.write_text("2", encoding="utf-8")
    return nuova


_classe = None


def _classe_finestra():
    """La finestra del timer, con i due segnali che JW LibriX sa gestire.

    `mediaRichiesto` e `scaricaRichiesta`: la finestra principale li collega
    da sola e riproduce o scarica come per la schermata Contenuti originale.
    """
    global _classe
    if _classe is None:
        from PyQt6.QtCore import pyqtSignal

        from src.views.main_window import MainWindow as Originale

        # Il nome deve restare «MainWindow»: le traduzioni sono legate al
        # nome della classe, e con un altro nome i testi tornano in inglese.
        class MainWindow(Originale):
            mediaRichiesto = pyqtSignal(dict)
            scaricaRichiesta = pyqtSignal(dict)
            pubblicazioneRichiesta = pyqtSignal(dict)

        _classe = MainWindow
    return _classe


def crea_schermata():
    import os
    os.environ.setdefault("ONTIME_DATA_DIR", str(_cartella_dati()))
    mancanti = _librerie_mancanti()
    if mancanti:
        elenco = " ".join(mancanti)
        return _messaggio(
            "Al Timer mancano delle librerie Python:\n\n" + elenco +
            "\n\nArch: sudo pacman -S " + " ".join("python-" + m.replace("python-", "")
                                                 for m in mancanti) +
            "\noppure: pip install --target \"" + str(BASE / "libs") + "\" " + elenco)

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from src.controllers.meeting_controller import MeetingController
    from src.controllers.settings_controller import SettingsController
    from src.controllers.timer_controller import TimerController
    from src.utils.translator import load_translation
    _adatta_all_app()
    from src.utils.epub_scraper import EPUBMeetingScraper
    EPUBMeetingScraper.CACHE_DIR = Path(os.environ["ONTIME_DATA_DIR"]) / "cache"
    EPUBMeetingScraper.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    controller = MeetingController()
    impostazioni = SettingsController(controller.settings_manager)
    _segui_la_lingua_dell_app(controller, impostazioni)
    timer = TimerController(impostazioni)

    import adattamento
    adattamento.scarta_file_con_visita(controller)
    controller.load_meetings()
    lingua = impostazioni.get_settings().language
    if lingua != "en":
        load_translation(QApplication.instance(), lingua)
    if lingua == "it":
        import adattamento
        adattamento.installa_traduzione_italiana()

    finestra = _classe_finestra()(controller, timer, impostazioni)
    import contenuti_timer
    finestra.contenuti = contenuti_timer.installa(finestra)
    adattamento._riordina_barra(finestra)
    adattamento._barra_che_basta(finestra)       # dopo: ora esistono anche Contenuti e Aggiungi file
    _adatta_dialoghi(finestra)
    applica_tema(finestra)
    # Una finestra senza bordi di sistema, che sta DENTRO la sezione.
    finestra.setWindowFlags(Qt.WindowType.Widget)
    _scegli_adunanza_di_oggi(controller, finestra)
    # All'uscita dell'app il timer chiude la sessione: senza, al prossimo
    # avvio crederebbe a un'interruzione.
    QApplication.instance().aboutToQuit.connect(finestra.close)
    return finestra


_adattato = False


def _segui_la_lingua_dell_app(controller, impostazioni) -> None:
    """Il timer usa la lingua corrente di JW LibriX (titoli, menu, monitor)."""
    try:
        from Utility import Lingua
        iso = Lingua.iso_corrente()
    except Exception:  # noqa: BLE001 - senza lingua dell'app resta quella del timer
        return
    s = impostazioni.get_settings()
    if iso and s.language != iso:
        s.language = iso
        impostazioni.save_settings()
        from src.utils.epub_scraper import EPUBMeetingScraper
        controller.scraper = EPUBMeetingScraper(iso)


def _adatta_dialoghi(finestra) -> None:
    import adattamento
    adattamento.dialoghi_senza_bordi(finestra)


def _adatta_all_app() -> None:
    import adattamento
    adattamento.applica()


def applica_tema(finestra, chiaro=None) -> None:
    """Colori di JW LibriX per il timer; si richiama quando l'app cambia tema."""
    import stile
    from Utility import tema
    if chiaro is None:
        chiaro = tema.tema_attivo()
    finestra.setStyleSheet(stile.foglio(chiaro))


def applica_schermo(finestra, nome) -> None:
    """Dall'app: su quale schermo sta il monitor del timer (None = spento)."""
    import monitor_timer as monitor
    monitor.applica_schermo(finestra, nome)


def al_chiudere_il_monitor(funzione) -> None:
    """Dall'app: cosa fare quando l'utente chiude il monitor con la X."""
    import monitor_timer as monitor
    monitor.al_chiudere = funzione


def _scegli_adunanza_di_oggi(controller, finestra) -> None:
    """Come faceva main.py: sceglie l'adunanza in base al giorno."""
    from datetime import datetime

    from src.models.meeting import MeetingType

    oggi = datetime.now().weekday()
    s = finestra.settings_controller.get_settings()
    infra, fine = s.midweek_meeting.day.value, s.weekend_meeting.day.value
    adunanze = controller.current_meetings
    scelta = None
    if oggi == infra and MeetingType.MIDWEEK in adunanze:
        scelta = adunanze[MeetingType.MIDWEEK]
    elif oggi == fine and MeetingType.WEEKEND in adunanze:
        scelta = adunanze[MeetingType.WEEKEND]
    elif (infra - oggi) % 7 <= (fine - oggi) % 7 and MeetingType.MIDWEEK in adunanze:
        scelta = adunanze[MeetingType.MIDWEEK]
    elif MeetingType.WEEKEND in adunanze:
        scelta = adunanze[MeetingType.WEEKEND]
    elif MeetingType.MIDWEEK in adunanze:
        scelta = adunanze[MeetingType.MIDWEEK]
    if scelta is None:
        return
    # Visita del sorvegliante ancora valida: l'adunanza si apre gia' modificata
    # (prima restava quella normale anche con il pulsante acceso).
    try:
        if finestra.settings_controller.is_co_visit_active():
            scelta = controller.apply_co_visit_modifications(scelta)
    except Exception:  # noqa: BLE001 - meglio l'adunanza normale che nessuna
        pass
    controller.set_current_meeting(scelta)
    finestra.contenuti.imposta_adunanza(scelta)
    finestra.timer_controller.set_meeting(scelta)
    if finestra._is_component_ready("meeting_view"):
        finestra.meeting_view.set_meeting(scelta)
    else:
        finestra._store_pending_action("meeting_view", "set_meeting", scelta)
    for i in range(finestra.meeting_selector.count()):
        m = finestra.meeting_selector.itemData(i)
        if m and m.meeting_type == scelta.meeting_type:
            finestra.meeting_selector.blockSignals(True)
            finestra.meeting_selector.setCurrentIndex(i)
            finestra.meeting_selector.blockSignals(False)
            break
    finestra.current_part_label.setText(finestra.tr("Meeting:") + f" {scelta.title}")
