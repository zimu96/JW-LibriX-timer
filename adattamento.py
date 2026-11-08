"""Adattamento del timer a JW LibriX, senza riscrivere il codice originale.

Cosa toglie, perche' lo fa gia' l'app:
    - tema chiaro/scuro: il timer usa lo stile dell'app
    - controllo aggiornamenti e voce "Informazioni": gli aggiornamenti sono
      quelli dell'app
    - scelta degli schermi e lingua: si scelgono nelle Impostazioni dell'app
    - uscita dal programma: il timer e' una sezione, non un programma
Cosa tiene: tutta la logica del timer, le adunanze, il monitor di rete (IP).
Cosa aggiunge: monitor del timer (schermo_timer), traduzione italiana di
riserva per i testi che il timer originale non traduce.
"""
import re

from PyQt6.QtCore import QEvent, QObject, QTimer, QTranslator, Qt
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QGroupBox, QLabel,
                             QWidget)

_applicato = False

DIZIONARIO = {
    "Meeting in progress": "Adunanza in corso",
    "Current Part: %s": "Parte attuale: %s",
    "Data Management": "Dati",
    "Target Duration:": "Durata prevista:",
    "Target duration for this meeting": "Durata prevista per questa adunanza",
    "Total: 0 min": "Totale: 0 min",
    "Invalid Title": "Titolo non valido",
    "Meeting title must be at least 3 characters long.": "Il titolo deve avere almeno 3 caratteri.",
    "Organizational standard for total meeting duration (e.g., 105 minutes)": "Durata totale standard dell'adunanza (es. 105 minuti)",
    "Automatic Data Cleanup": "Pulizia automatica dei dati",
    "Enable automatic cleanup on startup": "Pulisci da solo all'apertura",
    "Automatically remove old meeting files and cache data when the application starts": "Elimina i vecchi file delle adunanze e la cache all'apertura",
    " days": " giorni",
    "Files older than this many days will be removed": "I file più vecchi di questi giorni vengono eliminati",
    "Retention period:": "Conserva per:",
    "Meeting will end at:": "L'adunanza finirà alle:",
    "Schedule Updated": "Programma aggiornato",
    "Durations Reset": "Durate ripristinate",
    "All part durations restored to their original values.": "Tutte le durate sono tornate ai valori originali.",
    "Ready to Begin?": "Pronti a cominciare?",
    "Press Start Meeting to begin the timer and stay on schedule.": "Premi «Inizia adunanza» per avviare il timer e restare nei tempi.",
    "Over Time": "Tempo scaduto",
    "'{part_title}' has exceeded its allotted time.": "«{part_title}» ha superato il tempo assegnato.",
    "End Meeting At": "Termina l'adunanza alle",
    "End Meeting At...": "Termina l'adunanza alle...",
    "End meeting at:": "Termina alle:",
    "Current predicted end: ": "Fine prevista attuale: ",
    "will be adjusted": "verranno adattati",
    "Target time must be in the future": "L'ora deve essere nel futuro",
    "Not enough time": "Tempo insufficiente",
    "for": "per", "parts": "parti", "Saving": "Si risparmiano",
    "from remaining parts": "dalle parti rimanenti", "Adding": "Si aggiungono",
    "to remaining parts": "alle parti rimanenti", "No change needed": "Nessuna modifica necessaria",
    "Invalid Time": "Ora non valida",
    "The target end time must be in the future.": "L'ora di fine deve essere nel futuro.",
    "added": "aggiunti", "removed": "tolti", "Adjusted:": "Modificata:", "(original:": "(originale:",
    "Start the meeting timer first": "Prima avvia il timer",
    "Only available for current or upcoming parts": "Solo per la parte attuale o le prossime",
    "Reset Adjusted Durations": "Ripristina le durate originali",
    "Cannot Adjust": "Impossibile modificare", "Unknown error": "Errore sconosciuto",
    "&File": "&File",
    "&View": "&Visualizza",
    "&Settings": "&Impostazioni",
    "&New Meeting": "&Nuova adunanza",
    "&Open Meeting": "&Apri adunanza",
    "&Edit Current Meeting": "&Modifica adunanza corrente",
    "Edit Weekend &Songs": "Modifica i &cantici del fine settimana",
    "&Update Meetings from Web": "&Aggiorna le adunanze dal web",
    "&Network Display": "Monitor di &rete",
    "Show Network Panel": "Mostra il pannello di rete",
    "Start Network Display": "Avvia il monitor di rete",
    "Network Display Info...": "Monitor di rete...",
    "CO Visit Mode": "Visita del sorvegliante di circoscrizione",
    "Some songs of the weekend meeting have no number yet.": "Nell'adunanza della domenica mancano i numeri di alcuni cantici.",
    "Enter them now?": "Vuoi inserirli adesso?",
    "Edit Now": "Inserisci adesso", "Skip": "Dopo",
    "End Meeting?": "Terminare l'adunanza?",
    "%n part(s) redistributed — meeting now ends at": "Durate di %n parte/i ridistribuite: l'adunanza ora finisce alle",
    "%n part(s)": "%n parte/i",
    "😅 Hold up! Are you sure you want to stop the meeting?\nThis will end the timer and reset the session.":
        "Aspetta! Vuoi davvero terminare l'adunanza?\nIl timer si fermerà e la sessione verrà azzerata.",
    "Template:": "Modello:",
    "Presenter": "Relatore",
    "Presenter:": "Relatore:",
    "Public Talk and Watchtower Study": "Discorso pubblico e Studio di Torre di Guardia",
    "Next Part: %s": "Prossima parte: %s",
    "Secondary Display: Active": "Monitor del timer: attivo",
    "Secondary Display: Inactive": "Monitor del timer: spento",
    "Display secondario: inattivo": "Monitor del timer: spento",
    "Display secondario: attivo": "Monitor del timer: attivo",
}

MODELLI = (
    (r"^Next Part:\s*(.*)$", r"Prossima parte: \1"),
    (r"^Current Part:\s*(.*)$", r"Parte attuale: \1"),
    (r"^Last Part$", "Ultima parte"),
    (r"^Meeting Overtime:\s*(.*)$", r"Ritardo: \1"),
    (r"^Parts in section:\s*(.*)$", r"Parti della sezione: \1"),
    (r"^Total:\s*(\d+) min$", r"Totale: \1 min"),
    (r"^Meeting Ended$", "Adunanza terminata"),
    (r"^Midweek Meeting:\s*(.*)$", r"Adunanza infrasettimanale: \1"),
    (r"^Weekend Meeting:\s*(.*)$", r"Adunanza del fine settimana: \1"),
)


class TraduttoreDiRiserva(QTranslator):
    """Risponde solo dove il file di traduzione non ha una frase italiana."""

    def translate(self, contesto, sorgente, disambiguazione=None, n=-1):  # noqa: N802
        if not sorgente:
            return None
        if sorgente in DIZIONARIO:
            return DIZIONARIO[sorgente]
        for modello, sost in MODELLI:
            if re.match(modello, sorgente):
                return re.sub(modello, sost, sorgente)
        return None

    def isEmpty(self) -> bool:  # noqa: N802
        return False


_traduttore = None


def installa_traduzione_italiana() -> None:
    global _traduttore
    if _traduttore is None:
        _traduttore = TraduttoreDiRiserva()
        QApplication.instance().installTranslator(_traduttore)


def _titolo_con_numero(titolo: str, n: int, t: dict) -> str:
    """Il titolo di un cantico con un altro numero, senza toccare il resto."""
    import re

    from contenuti_timer import numero_cantico
    if n <= 0:
        return titolo
    if numero_cantico(titolo) is not None:
        return re.sub(r"(?<![\d.])\d{1,3}(?![\d.])", str(n), titolo, count=1)
    if titolo in (t.get("opening_song_prayer"), t.get("closing_song_prayer")):
        return f"{t['song']} {n} {t['and_prayer']}"
    m = re.match(r"(\S+)\s*(.*)$", titolo)
    if not m:
        return titolo
    resto = re.sub(r"^(iniziale|finale|di apertura|di chiusura)\s*", "", m.group(2),
                   flags=re.IGNORECASE)
    return f"{m.group(1)} {n} {resto}".strip()


def _numero_nel_dialogo(dialogo, vista) -> None:
    """Se la parte e' un cantico: un campo «Numero del cantico» al posto del titolo."""
    import re

    from PyQt6.QtWidgets import QFormLayout, QSpinBox

    from contenuti_timer import numero_cantico
    dialogo._traduzioni = {}
    try:
        dialogo._traduzioni = vista.meeting_controller._get_translations(vista.meeting.language)
    except Exception:  # noqa: BLE001
        pass
    titolo = dialogo.part.title
    t = dialogo._traduzioni
    generico = titolo in (t.get("opening_song_prayer"), t.get("closing_song_prayer"))
    parola = re.match(r"\s*(cantico|canto|song|cantique|lied|canci[oó]n|c[aâ]ntico)\b",
                      titolo, re.IGNORECASE)
    dialogo.numero_cantico = None
    if numero_cantico(titolo) is None and not generico and not parola:
        return
    forma = dialogo.layout()
    if not isinstance(forma, QFormLayout):
        return
    for campo in (dialogo.title_edit, dialogo.presenter_edit):
        etichetta = forma.labelForField(campo)
        if etichetta is not None:
            etichetta.hide()
        campo.hide()
    numero = QSpinBox()
    numero.setRange(0, 200)
    numero.setSpecialValueText("da scegliere")
    numero.setValue(numero_cantico(titolo) or 0)
    forma.insertRow(0, "Numero del cantico:", numero)
    dialogo.numero_cantico = numero
    dialogo.setWindowTitle("Cantico")


def _pulisci_menu(finestra) -> None:
    barra = finestra.menuBar()
    for azione in list(barra.actions()):
        testo = azione.text().replace("&", "").lower()
        if testo in ("help", "aiuto"):
            barra.removeAction(azione)
    for nome in ("theme_menu",):
        menu = getattr(finestra, nome, None)
        if menu is not None:
            menu.menuAction().setVisible(False)
    if hasattr(finestra, "toggle_secondary_action"):
        finestra.toggle_secondary_action.setVisible(False)
    for menu in barra.findChildren(type(finestra.theme_menu)):
        for azione in list(menu.actions()):
            t = azione.text().replace("&", "").lower()
            if t.startswith(("exit", "esci", "switch display", "cambia modalit")):
                menu.removeAction(azione)


def _gruppo_monitor(dialogo) -> QGroupBox:
    """Dove si mostra il timer: un solo monitor, scelto per nome, attivo subito."""
    from PyQt6.QtWidgets import QFormLayout

    from Utility import Plugin, Schermi

    gruppo = QGroupBox("Monitor del timer")
    forma = QFormLayout(gruppo)
    scelta = QComboBox()
    scelta.addItem("Disattivato", "")
    for voce in Schermi.elenco():
        scelta.addItem(voce["etichetta"], voce["nome"])
    scelta.setCurrentIndex(max(0, scelta.findData(Plugin.schermo("timer"))))

    def cambiato(_i: int) -> None:
        import monitor_timer
        nome = str(scelta.currentData() or "")
        Plugin.imposta_schermo("timer", nome)
        monitor_timer.applica_schermo(dialogo.parent(), nome or None)

    scelta.activated.connect(cambiato)
    forma.addRow("Schermo:", scelta)
    nota = QLabel("Mostra l'ora e il tempo a chi parla. E' separato dal monitor "
                  "di video e immagini: scegli uno schermo diverso.")
    nota.setWordWrap(True)
    forma.addRow("", nota)
    return gruppo


def _allinea_schermi_nascosti(dialogo) -> None:
    """I campi nascosti della vecchia scelta devono dire quello che dice la nuova.

    Il salvataggio originale li rilegge e riscrive: con valori diversi
    spegnerebbe il monitor appena scelto.
    """
    from src.utils.screen_handler import ScreenHandler

    from Utility import Plugin

    nome = Plugin.schermo("timer")
    indice = next((s["index"] for s in ScreenHandler.get_all_screens()
                   if s["name"] == nome), None) if nome else None
    dialogo.use_secondary_check.setChecked(indice is not None)
    voce = dialogo.secondary_screen_combo.findData(indice)
    if voce >= 0:
        dialogo.secondary_screen_combo.setCurrentIndex(voce)


def _gruppo_contenuti(dialogo) -> QGroupBox:
    from PyQt6.QtWidgets import QCheckBox, QVBoxLayout

    import opzioni

    gruppo = QGroupBox("Contenuti multimediali")
    colonna = QVBoxLayout(gruppo)
    casella = QCheckBox("Avvia subito il cantico quando inizia la parte")
    casella.setChecked(opzioni.avvio_automatico())
    casella.toggled.connect(opzioni.imposta_avvio_automatico)
    colonna.addWidget(casella)
    nota = QLabel("Quando passi a una parte che e' un cantico, il cantico parte subito, "
                  "senza premere altro. Gli altri video e audio li avvii tu dal "
                  "pannello Contenuti. Se l'opzione e' spenta, avvii tu anche i cantici.")
    nota.setWordWrap(True)
    colonna.addWidget(nota)
    return gruppo


def _gruppo_scaletta(dialogo) -> QGroupBox:
    from PyQt6.QtWidgets import QCheckBox, QVBoxLayout

    import opzioni

    gruppo = QGroupBox("Scaletta")
    colonna = QVBoxLayout(gruppo)
    casella = QCheckBox("Dopo ogni parte, un minuto di passaggio del presidente")
    casella.setChecked(opzioni.passaggio_presidente())
    casella.toggled.connect(opzioni.imposta_passaggio_presidente)
    colonna.addWidget(casella)
    nota = QLabel("Se spento, «Successivo» passa subito alla parte dopo. Se acceso, "
                  "«Successivo» chiude la parte e avvia il minuto del presidente; "
                  "un secondo «Successivo» lo salta.")
    nota.setWordWrap(True)
    colonna.addWidget(nota)
    return gruppo


def _pulisci_impostazioni(dialogo) -> None:
    schede = dialogo.tab_widget
    schede.removeTab(schede.indexOf(dialogo.general_tab))   # lingua: segue l'app
    gruppo_schermi = dialogo.primary_screen_combo.parentWidget()
    if isinstance(gruppo_schermi, QGroupBox):
        gruppo_schermi.hide()                               # la vecchia scelta a due schermi
        dialogo.display_tab.layout().insertWidget(0, _gruppo_monitor(dialogo))
        dialogo.display_tab.layout().insertWidget(1, _gruppo_contenuti(dialogo))
        dialogo.display_tab.layout().insertWidget(2, _gruppo_scaletta(dialogo))
    dialogo.theme_combo.hide()                              # tema: lo sceglie l'app
    gruppo_tema = dialogo.theme_combo.parentWidget()
    if isinstance(gruppo_tema, QGroupBox):
        gruppo_tema.hide()                                  # il riquadro conteneva solo il tema
    for etichetta in dialogo.display_tab.findChildren(QLabel):
        if etichetta.text().strip().rstrip(":").lower() in ("theme", "tema"):
            etichetta.hide()


def _rifinisci_impostazioni(dialogo) -> None:
    """Testi rimasti in inglese e voci che non servono piu' (rete su una porta sola)."""
    from PyQt6.QtWidgets import QCheckBox, QDialogButtonBox, QFormLayout

    for tasto, testo in ((QDialogButtonBox.StandardButton.Ok, "OK"),
                         (QDialogButtonBox.StandardButton.Cancel, "Annulla"),
                         (QDialogButtonBox.StandardButton.Apply, "Applica"),
                         (QDialogButtonBox.StandardButton.Reset, "Ripristina")):
        for scatola in dialogo.findChildren(QDialogButtonBox):
            if scatola.button(tasto) is not None:
                scatola.button(tasto).setText(testo)
    for etichetta in dialogo.findChildren(QLabel):
        if etichetta.text().startswith("Cleanup removes old meeting"):
            etichetta.setText("La pulizia elimina i vecchi file delle adunanze, i download EPUB "
                              "e la cache. Le adunanze aperte non vengono mai eliminate.")
    for casella in dialogo.findChildren(QCheckBox):
        if casella.text().startswith("Ricorda lo stato del pannello"):
            gruppo = casella.parentWidget()
            (gruppo if isinstance(gruppo, QGroupBox) else casella).hide()   # il pannello non c'e' piu'
    # Rete: una porta sola, un solo modo di accenderla.
    if dialogo.ws_only_radio.isChecked():
        dialogo.http_ws_radio.setChecked(True)
    dialogo.ws_only_radio.hide()
    dialogo.http_ws_radio.setText("Acceso (pagina per tablet e telefoni)")
    dialogo.http_ws_radio.setToolTip("Mostra il timer su un tablet o un telefono collegato alla stessa rete.")
    dialogo.disabled_radio.setText("Spento")
    forma = dialogo.http_port_spin.parentWidget().layout()
    if isinstance(forma, QFormLayout):
        forma.labelForField(dialogo.http_port_spin).hide()
        forma.labelForField(dialogo.ws_port_spin).setText("Porta:")
        dialogo.ws_port_spin.setToolTip("Porta della pagina e dei dati del timer")
        dialogo.ws_port_spin.parentWidget().setTitle("Porta di rete")
    dialogo.http_port_spin.hide()


def _riordina_barra(finestra) -> None:
    """A mezzo schermo la barra non basta e i tasti in fondo finiscono nascosti.

    Davanti stanno quelli che servono mentre si parla (-1 / +1 minuto), poi
    Precedente/Successivo; Contenuti e Aggiungi file vanno dopo.
    """
    from PyQt6.QtWidgets import QToolBar
    barra = finestra.findChild(QToolBar)
    if barra is None:
        return
    azioni = barra.actions()

    def di(widget):
        return next((a for a in azioni if barra.widgetForAction(a) is widget), None)

    def per_testo(testo):
        return next((a for a in azioni if isinstance(barra.widgetForAction(a), QPushButton)
                     and barra.widgetForAction(a).text() == testo), None)

    from PyQt6.QtWidgets import QPushButton
    avvia, pausa = di(finestra.start_button), di(finestra.pause_resume_button)
    meno, piu = di(finestra.decrease_button), di(finestra.increase_button)
    prec, succ = di(finestra.prev_button), di(finestra.next_button)
    contenuti, aggiungi = per_testo("Contenuti"), per_testo("Aggiungi file")
    if None in (avvia, pausa, meno, piu, prec, succ, contenuti, aggiungi):
        return
    sep = [a for a in azioni if a.isSeparator()]
    primi = [avvia, pausa, meno, piu, prec, succ, contenuti, aggiungi]
    ordine = [avvia, pausa, sep[0] if sep else None, meno, piu,
              sep[1] if len(sep) > 1 else None, prec, succ,
              sep[2] if len(sep) > 2 else None, contenuti, aggiungi,
              sep[3] if len(sep) > 3 else None]
    resto = [a for a in azioni if a not in primi and a not in sep]
    for a in azioni:
        barra.removeAction(a)
    for a in [x for x in ordine if x is not None] + resto:
        barra.addAction(a)


def _barra_che_basta(finestra) -> None:
    """Nessuna freccia «»» nella barra: il menu a comparsa si chiude appena si muove il mouse.

    Scelta adunanza, visita e Rete vanno su una seconda riga; i tasti con icona
    perdono il testo (resta nel suggerimento) quando la finestra e' stretta.
    """
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QFontMetrics
    from PyQt6.QtWidgets import QPushButton, QToolBar

    barra = finestra.findChild(QToolBar)
    if barra is None or getattr(finestra, "_barra_due", None) is not None:
        return
    centrali = {finestra.start_button, finestra.pause_resume_button, finestra.decrease_button,
                finestra.increase_button, finestra.prev_button, finestra.next_button}
    nomi = {w for w in centrali}
    resto = [a for a in barra.actions() if not a.isSeparator()
             and barra.widgetForAction(a) not in nomi
             and not (isinstance(barra.widgetForAction(a), QPushButton)
                      and barra.widgetForAction(a).text() in ("Contenuti", "Aggiungi file"))]
    resto_vis = [a for a in resto if a.isVisible()]
    seconda = QToolBar("Adunanza", finestra)
    seconda.setMovable(False)
    seconda.setIconSize(barra.iconSize())
    for a in resto:
        barra.removeAction(a)
        seconda.addAction(a)
    finestra.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
    finestra.addToolBar(Qt.ToolBarArea.TopToolBarArea, seconda)
    finestra._barra_due = seconda

    def adatta() -> None:
        icone = [w for w in centrali if w is not None]
        for w in icone:
            if w.text():
                w.setProperty("pieno", w.text())
        fm = QFontMetrics(finestra.start_button.font())

        senza: set = set()

        def larghezza(azioni, _=True) -> int:
            n = 0
            for a in azioni:
                w = (barra.widgetForAction(a) or seconda.widgetForAction(a))
                senza_testo = w in senza
                if not a.isVisible():
                    continue
                if a.isSeparator():
                    n += 12
                elif w in centrali and not senza_testo:
                    n += fm.horizontalAdvance(w.property("pieno") or "") + 24 + 36
                elif w in centrali:
                    n += 24 + 36
                elif w is not None:
                    n += w.sizeHint().width() + 6
            return n

        fissi = [a for a in barra.actions() if a not in resto]
        base = 40 + larghezza(fissi, True)
        una_riga = base + larghezza(resto, True) <= barra.width()
        # Se non basta, perdono il testo prima Precedente/Successivo, poi Inizia/Pausa;
        # -1 e +1 minuto restano sempre scritti: con la sola icona si confondono.
        for w in (finestra.prev_button, finestra.next_button,
                  finestra.start_button, finestra.pause_resume_button):
            if base <= barra.width():
                break
            senza.add(w)
            base = 40 + larghezza(fissi, True)

        # Una riga se ci sta tutto, altrimenti i tasti secondari scendono in una seconda.
        dove = barra if una_riga else seconda
        if resto and dove.actions()[-len(resto):] != resto:
            for a in resto:
                barra.removeAction(a)
                seconda.removeAction(a)
            for a in resto:
                dove.addAction(a)
        seconda.setVisible(not una_riga)

        for w in icone:
            pieno = w.property("pieno") or ""
            if w in senza:
                if w.text():
                    w.setText("")
                w.setToolTip(pieno)
            elif not w.text() and pieno:
                w.setText(pieno)
                w.setToolTip("")

    orologio = QTimer(finestra)
    orologio.timeout.connect(adatta)
    orologio.start(400)
    QTimer.singleShot(0, adatta)


def _pulisci_separatori(finestra) -> None:
    """Nessun separatore all'inizio, alla fine o doppio nei menu."""
    for voce in finestra.menuBar().actions():
        menu = voce.menu()
        if menu is None:
            continue
        precedente_sep = True
        for azione in menu.actions():
            if not azione.isVisible():
                continue
            if azione.isSeparator():
                if precedente_sep:
                    menu.removeAction(azione)
                precedente_sep = True
            else:
                precedente_sep = False
        for azione in reversed(menu.actions()):
            if not azione.isVisible():
                continue
            if azione.isSeparator():
                menu.removeAction(azione)
            break


def _titoli_della_visita(controllo, lingua: str) -> tuple:
    t = controllo._get_translations(lingua)
    return tuple(x for x in (t.get("co_talk"), t.get("service_talk")) if x)


def _ha_parti_della_visita(controllo, meeting) -> bool:
    """True se l'adunanza e' la versione «visita»: non deve finire sul file."""
    titoli = _titoli_della_visita(controllo, meeting.language)
    return any(p.title.startswith(titoli) for s in meeting.sections for p in s.parts) \
        if titoli else False


def scarta_file_con_visita(controllo) -> None:
    """Toglie dalla cartella le adunanze salvate per sbaglio con la visita dentro.

    Sono dati letti dal web: alla prossima lettura tornano giusti.
    """
    import json
    from pathlib import Path
    for f in Path(controllo.meetings_dir).glob("*.json"):
        try:
            dati = json.loads(f.read_text(encoding="utf-8"))
            titoli = _titoli_della_visita(controllo, dati.get("language", "it"))
            parti = [p.get("title", "") for s in dati.get("sections", []) for p in s.get("parts", [])]
            if titoli and dati.get("source") != "manual" and any(x.startswith(titoli) for x in parti):
                f.unlink()
        except (OSError, ValueError, AttributeError):
            pass


def _scarta_sessione_interrotta(self) -> None:
    """Niente domande all'avvio: una sessione rimasta aperta si scarta."""
    try:
        if self.timer_controller.session_manager.check_for_recovery():
            self.timer_controller.session_manager.clear_session()
    except Exception:  # noqa: BLE001 - un file di sessione rotto non deve fermare il timer
        pass


def _aggiungi_visita(finestra) -> None:
    """Il pulsante «Visita» nella barra: sempre visibile, non nelle impostazioni."""
    from PyQt6.QtWidgets import QPushButton, QToolBar

    barra = finestra.findChild(QToolBar)
    azione = getattr(finestra, "co_visit_action", None)
    if barra is None or azione is None:
        return
    tasto = QPushButton()
    tasto.setCheckable(True)
    tasto.setToolTip("Settimana della visita: l'adunanza infrasettimanale e' il martedi', "
                     "al posto dello studio biblico c'e' il discorso del sorvegliante. "
                     "Si spegne da sola alla fine della settimana.")

    def testo(acceso: bool) -> None:
        tasto.setText("Disattiva visita sorvegliante" if acceso
                      else "Attiva visita sorvegliante")

    def sincronizza(acceso: bool) -> None:
        tasto.blockSignals(True)
        tasto.setChecked(acceso)
        tasto.blockSignals(False)
        testo(acceso)

    def cliccato(acceso: bool) -> None:
        if acceso and not _chiedi_titoli(finestra):
            sincronizza(False)           # annullato: la visita non si accende
            return
        azione.setChecked(acceso)
        finestra._toggle_co_visit(acceso)
        testo(acceso)

    sincronizza(azione.isChecked())
    tasto.clicked.connect(cliccato)
    azione.toggled.connect(sincronizza)
    # in fondo alla barra, dopo Impostazioni, con lo stile degli altri tasti
    barra.addWidget(tasto)
    finestra.tasto_visita = tasto

    # I titoli si possono cambiare anche dopo, dal menu Visualizza.
    for voce in finestra.menuBar().actions():
        if voce.menu() is not None and voce.text().replace("&", "") in ("Visualizza", "View"):
            titoli = voce.menu().addAction("Titoli della visita…")
            titoli.setEnabled(azione.isChecked())
            azione.toggled.connect(titoli.setEnabled)

            def cambia() -> None:
                if _chiedi_titoli(finestra):
                    finestra._reload_current_meeting_with_co_visit()

            titoli.triggered.connect(cambia)
            finestra._voce_titoli_visita = titoli

    # Durante l'adunanza la visita non si cambia: un clic per sbaglio
    # cambierebbe le parti a meta' (e il timer).  Si decide prima di iniziare.
    from PyQt6.QtCore import QTimer
    nota_attiva = tasto.toolTip()

    def blocca() -> None:
        in_corso = finestra.start_button.objectName() == "stopButton"
        voce = getattr(finestra, "_voce_titoli_visita", None)
        tasto.setEnabled(not in_corso)
        azione.setEnabled(not in_corso)
        if voce is not None:
            voce.setEnabled(azione.isChecked() and not in_corso)
        tasto.setToolTip("Non si puo' cambiare durante l'adunanza: ferma prima l'adunanza."
                         if in_corso else nota_attiva)

    controllo = QTimer(finestra)
    controllo.timeout.connect(blocca)
    controllo.start(300)


def _togli_impostazioni_dalla_barra(finestra) -> None:
    """Il pulsante Impostazioni sta nei tre puntini della barra viola dell'app."""
    from PyQt6.QtWidgets import QPushButton, QToolBar
    barra = finestra.findChild(QToolBar)
    if barra is None:
        return
    for azione in barra.actions():
        w = barra.widgetForAction(azione)
        if isinstance(w, QPushButton) and w.text() in ("Impostazioni", "Settings"):
            azione.setVisible(False)


def _lunedi() -> str:
    from datetime import date, timedelta
    oggi = date.today()
    return (oggi - timedelta(days=oggi.weekday())).isoformat()


def _chiedi_titoli(finestra) -> bool:
    """I titoli dei discorsi della visita, scritti a mano.  False se si annulla."""
    from PyQt6.QtWidgets import (QDialogButtonBox, QFormLayout, QLineEdit,
                                 QVBoxLayout)

    import opzioni
    attuali = opzioni.titoli_visita(_lunedi())
    dialogo = QDialog(finestra)
    dialogo.setWindowTitle("Visita del sorvegliante")
    colonna = QVBoxLayout(dialogo)
    colonna.setContentsMargins(14, 14, 14, 14)
    nota = QLabel("Scrivi i titoli dei discorsi di questa settimana (puoi lasciarli "
                  "vuoti e inserirli dopo). Restano per la settimana della visita, "
                  "poi si cancellano da soli.")
    nota.setWordWrap(True)
    colonna.addWidget(nota)
    forma = QFormLayout()
    campi = {}
    for chiave, etichetta in (
            ("servizio", "Infrasettimanale (martedì), al posto dello studio biblico:"),
            ("pubblico", "Domenica, all'inizio (discorso pubblico):"),
            ("finale", "Domenica, alla fine (discorso del sorvegliante):")):
        riga = QLineEdit(attuali.get(chiave, ""))
        campi[chiave] = riga
        forma.addRow(etichetta, riga)
    colonna.addLayout(forma)
    tasti = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                             | QDialogButtonBox.StandardButton.Cancel)
    tasti.accepted.connect(dialogo.accept)
    tasti.rejected.connect(dialogo.reject)
    colonna.addWidget(tasti)
    dialogo.setMinimumWidth(560)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False
    opzioni.imposta_titoli_visita(_lunedi(), {k: v.text() for k, v in campi.items()})
    return True


def _avviso_visita_all_apertura(finestra) -> None:
    """Se la visita e' attiva, un avviso giallo breve all'apertura del timer."""
    from PyQt6.QtCore import QTimer
    try:
        attiva = finestra.settings_controller.is_co_visit_active()
    except Exception:  # noqa: BLE001
        attiva = False
    if attiva:
        finestra.esegui_quando_visibile(lambda: finestra._show_toast_notification(
            "Visita del sorvegliante attiva",
            "Questa settimana: adunanza infrasettimanale il martedì, con il discorso "
            "del sorvegliante al posto dello studio biblico.", icon="toast-info"), 1500)


_TASTI_ITALIANI = (
    ("Ok", "OK"), ("Cancel", "Annulla"), ("Yes", "Sì"), ("No", "No"),
    ("Apply", "Applica"), ("Reset", "Ripristina"), ("Close", "Chiudi"),
    ("Save", "Salva"), ("Discard", "Scarta"), ("Open", "Apri"),
    ("Retry", "Riprova"), ("Ignore", "Ignora"), ("Abort", "Interrompi"),
    ("YesToAll", "Sì a tutti"), ("NoToAll", "No a tutti"), ("Help", "Aiuto"),
    ("RestoreDefaults", "Ripristina"), ("SaveAll", "Salva tutto"),
)


def tasti_in_italiano(d) -> None:
    """Sì / No / Annulla ... al posto di Yes / No / Cancel in ogni pop-up del timer."""
    from PyQt6.QtWidgets import QDialogButtonBox, QMessageBox
    scatole = d.findChildren(QDialogButtonBox)
    for nome, testo in _TASTI_ITALIANI:
        for scatola in scatole:
            tasto = scatola.button(getattr(QDialogButtonBox.StandardButton, nome))
            if tasto is not None and tasto.text().replace("&", "") != testo:
                tasto.setText(testo)
    if isinstance(d, QMessageBox):
        for nome, testo in _TASTI_ITALIANI:
            tasto = d.button(getattr(QMessageBox.StandardButton, nome, None))
            if tasto is not None and tasto.text().replace("&", "") != testo:
                tasto.setText(testo)


class _DialoghiSenzaBordi(QObject):
    """I pop-up del timer sono parte dell'app: niente cornice del sistema.

    Si interviene al momento della «rifinitura» (Polish), prima che la
    finestra venga creata, cosi' non c'e' sfarfallio.  Servono una testata
    col titolo (la barra del titolo non c'e' piu') e un bordo viola.

    I pop-up che ci stanno diventano parte della finestra dell'app (non
    finestre a parte): stanno al centro dell'app, qualunque sia la sua
    grandezza, e non finiscono mai sotto un'altra finestra (Zoom).  Sotto di
    loro un velo scuro blocca i clic sul resto del timer.
    """

    def __init__(self, finestra) -> None:
        super().__init__(finestra)
        self._finestra = finestra
        self._veli: dict = {}

    def _del_timer(self, w) -> bool:
        p = w.parentWidget()
        while p is not None:
            if p is self._finestra:
                return True
            p = p.parentWidget()
        return False

    def eventFilter(self, oggetto, evento) -> bool:  # noqa: N802
        tipo = evento.type()
        if (tipo == QEvent.Type.Polish and isinstance(oggetto, QDialog)
                and not isinstance(oggetto, QFileDialog)
                and oggetto.isWindow() and not oggetto.property("senza_bordi")
                and self._del_timer(oggetto)):
            oggetto.setProperty("senza_bordi", True)
            try:
                self._prepara(oggetto)
                tasti_in_italiano(oggetto)
                self._incorpora(oggetto)
            except Exception:  # noqa: BLE001 - un pop-up con la cornice e' meglio di nessun pop-up
                pass
        elif tipo == QEvent.Type.Show and isinstance(oggetto, QDialog) \
                and oggetto.property("incorporato"):
            QTimer.singleShot(0, lambda d=oggetto: self._metti_al_centro(d))
            self._metti_al_centro(oggetto)
        elif tipo == QEvent.Type.Hide and isinstance(oggetto, QDialog) \
                and oggetto.property("incorporato"):
            self._togli_velo(oggetto)
        elif tipo == QEvent.Type.Resize and isinstance(oggetto, QWidget) \
                and oggetto is self._finestra and self._veli:
            for d in list(self._veli):
                try:
                    self._metti_al_centro(d)
                except RuntimeError:
                    self._veli.pop(d, None)
        return False

    # -- dentro la finestra dell'app -------------------------------------
    def _incorpora(self, d) -> None:
        """Il pop-up diventa un pezzo della finestra, se ci sta dentro."""
        f = self._finestra
        if not f.isVisible():
            return                      # il timer non si vede: il pop-up resta una finestra, visibile
        d.adjustSize()
        minimo = d.minimumSizeHint()
        massimo = f.size()
        if (minimo.width() > massimo.width() - 24 or minimo.height() > massimo.height() - 24
                or d.layout() is None):
            return                      # troppo grande: resta una finestra a parte
        d.setParent(f, Qt.WindowType.Widget)     # da finestra a widget interno
        d.setProperty("incorporato", True)
        d.setAutoFillBackground(True)
        d.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def _metti_al_centro(self, d) -> None:
        f = self._finestra
        if not d.isVisible() or d.parentWidget() is not f:
            return
        self._velo_per(d).setGeometry(f.rect())
        self._velo_per(d).raise_()
        m = 12
        larg = min(max(d.sizeHint().width(), d.minimumSizeHint().width(), d.width()),
                   f.width() - 2 * m)
        alt = min(max(d.sizeHint().height(), d.minimumSizeHint().height(), d.height()),
                  f.height() - 2 * m)
        if (d.width(), d.height()) != (larg, alt):
            d.resize(larg, alt)
        finestra_app = f.window()
        centro = f.mapFromGlobal(finestra_app.mapToGlobal(finestra_app.rect().center()))
        x = max(m, min(centro.x() - d.width() // 2, f.width() - d.width() - m))
        y = max(m, min(centro.y() - d.height() // 2, f.height() - d.height() - m))
        d.move(x, y)
        d.raise_()
        if not d.property("fuoco_dato"):
            d.setProperty("fuoco_dato", True)
            d.setFocus(Qt.FocusReason.PopupFocusReason)    # Invio / Esc funzionano subito

    def _velo_per(self, d):
        velo = self._veli.get(d)
        if velo is None:
            velo = _Velo(self._finestra)
            self._veli[d] = velo
            velo.show()
            velo.raise_()
        return velo

    def _togli_velo(self, d) -> None:
        velo = self._veli.pop(d, None)
        if velo is not None:
            velo.hide()
            velo.deleteLater()

    @staticmethod
    def _prepara(d) -> None:
        import html

        from PyQt6.QtWidgets import QFormLayout, QMessageBox, QVBoxLayout

        from Utility import tema

        titolo = d.windowTitle()
        d.setWindowFlags((d.windowFlags() | Qt.WindowType.FramelessWindowHint)
                         & ~Qt.WindowType.WindowContextHelpButtonHint)
        stile_testata = (f"background-color: {tema.ACCENTO}; color: #ffffff; "
                         "font-weight: 700; font-size: 15px; padding: 10px 14px;")
        if isinstance(d, QMessageBox):
            if titolo:
                testo = d.text()
                if not ("<" in testo and ">" in testo):
                    testo = html.escape(testo).replace("\n", "<br>")
                d.setTextFormat(Qt.TextFormat.RichText)
                d.setText(f"<span style='font-size:15px;font-weight:700;"
                          f"color:{tema.colori(tema.tema_attivo())['accentoTesto']}'>"
                          f"{html.escape(titolo)}</span><br><br>{testo}")
        elif titolo and isinstance(d.layout(), QFormLayout):
            testata = QLabel(titolo)
            testata.setStyleSheet(stile_testata)
            d.layout().insertRow(0, testata)
        elif titolo and isinstance(d.layout(), QVBoxLayout):
            testata = QLabel(titolo)
            testata.setStyleSheet(stile_testata)
            d.layout().setContentsMargins(0, 0, 0, d.layout().contentsMargins().bottom())
            d.layout().insertWidget(0, testata)


class _Velo(QWidget):
    """Il velo scuro dietro un pop-up: inghiotte i clic, cosi' il resto non si tocca."""

    def __init__(self, genitore) -> None:
        super().__init__(genitore)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setAutoFillBackground(False)

    def paintEvent(self, evento) -> None:  # noqa: N802
        from PyQt6.QtGui import QColor, QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        p.end()

    def mousePressEvent(self, evento) -> None:  # noqa: N802
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        evento.accept()

    def mouseDoubleClickEvent(self, evento) -> None:  # noqa: N802
        evento.accept()

    def wheelEvent(self, evento) -> None:  # noqa: N802
        evento.accept()


def dialoghi_senza_bordi(finestra) -> None:
    """Da chiamare con la finestra del timer: i suoi pop-up diventano senza cornice."""
    filtro = _DialoghiSenzaBordi(finestra)
    QApplication.instance().installEventFilter(filtro)
    finestra._dialoghi_senza_bordi = filtro


def applica() -> None:
    global _applicato
    if _applicato:
        return
    _applicato = True
    import monitor_timer
    import schermo_timer
    import src.views.main_window as mw
    import src.views.settings_view as sv

    # tema e aggiornamenti: niente
    mw.MainWindow._apply_minimal_styling = lambda self: None
    mw.MainWindow._apply_current_theme = lambda self: None
    mw.MainWindow._apply_secondary_display_theme = lambda self: None
    mw.MainWindow._check_for_updates = lambda self, silent=False: None
    mw.MainWindow._start_screen_monitoring = lambda self: None
    mw.MainWindow._check_session_recovery = _scarta_sessione_interrotta

    # «Successivo» passa subito alla parte dopo; il minuto del presidente
    # tra le parti e' un'opzione (spenta di partenza).
    import src.controllers.timer_controller as tc
    transizione_originale = tc.TimerController._should_add_chairman_transition

    def transizione(self):
        import opzioni
        return opzioni.passaggio_presidente() and transizione_originale(self)

    tc.TimerController._should_add_chairman_transition = transizione

    scelta_originale = mw.MainWindow._set_current_meeting

    def scelta_con_contenuti(self, meeting):
        # Con la visita attiva ogni adunanza scelta si apre gia' modificata.
        if meeting and not getattr(meeting, "_co_applicata", False):
            try:
                if self.settings_controller.is_co_visit_active():
                    meeting = self.meeting_controller.apply_co_visit_modifications(meeting)
            except Exception:  # noqa: BLE001
                pass
        scelta_originale(self, meeting)
        # Il timer deve usare l'adunanza scelta: prima, scegliendo dall'elenco,
        # il timer restava sull'adunanza di prima e le parti non corrispondevano
        # piu' a quelle mostrate (e ai contenuti).  A timer fermo soltanto.
        if meeting and self.timer_controller.current_part_index < 0:
            scelta_corrente = self.meeting_controller.current_meeting or meeting
            if self.timer_controller.current_meeting is not scelta_corrente:
                self.timer_controller.set_meeting(scelta_corrente)
        if meeting and getattr(self, "contenuti", None) is not None:
            self.contenuti.imposta_adunanza(meeting)

    mw.MainWindow._set_current_meeting = scelta_con_contenuti

    originale_main = mw.MainWindow.__init__

    def main_pulita(self, *a, **k):
        originale_main(self, *a, **k)
        _pulisci_menu(self)
        self.menuBar().setVisible(False)     # i menu stanno nella barra viola dell'app
        _aggiungi_visita(self)
        _togli_impostazioni_dalla_barra(self)
        import rete_timer
        rete_timer.installa(self)
        _riordina_barra(self)
        _pulisci_separatori(self)
        _avviso_visita_all_apertura(self)

    mw.MainWindow.__init__ = main_pulita

    salva_originale = sv.SettingsDialog._apply_settings

    def salva_allineato(self, *a, **k):
        _allinea_schermi_nascosti(self)
        return salva_originale(self)          # il segnale clicked(bool) manda un argomento di troppo

    sv.SettingsDialog._apply_settings = salva_allineato

    originale_imp = sv.SettingsDialog.__init__

    def imp_pulita(self, *a, **k):
        originale_imp(self, *a, **k)
        _pulisci_impostazioni(self)
        _rifinisci_impostazioni(self)

    sv.SettingsDialog.__init__ = imp_pulita

    # Le cifre del timer nella finestra seguono la larghezza: a mezzo schermo
    # (accanto a Zoom) l'orario non deve uscire dal riquadro.
    import src.views.timer_view as tv

    def adatta_cifre(self) -> None:
        from PyQt6.QtGui import QFont, QFontMetrics
        etichetta = getattr(self, "timer_label", None)
        if etichetta is None:
            return
        try:
            testo = etichetta.text() or "00:00:00"
            larghezza = max(40, etichetta.width() - 24)
            altezza = max(40, etichetta.height() - 12)
            px = min(160, int(altezza * 0.8))
            while px > 14:
                f = QFont("Courier New")
                f.setStyleHint(QFont.StyleHint.Monospace)
                f.setBold(True)
                f.setPixelSize(px)
                if QFontMetrics(f).horizontalAdvance(testo) <= larghezza:
                    break
                px -= max(1, px // 20)
            if getattr(self, "_px_cifre", 0) != px:
                self._px_cifre = px
                etichetta.setWordWrap(False)
                etichetta.setStyleSheet(
                    f"font-size: {px}px; font-weight: bold; font-family: 'Courier New', monospace;")
        except RuntimeError:
            pass

    def con_cifre_adattate(nome):
        originale_tv = getattr(tv.TimerView, nome)

        def nuovo(self, *a, **k):
            r = originale_tv(self, *a, **k)
            adatta_cifre(self)
            return r
        setattr(tv.TimerView, nome, nuovo)

    for nome in ("resizeEvent", "_update_current_time", "_update_time", "_update_display"):
        con_cifre_adattate(nome)

    # Il doppio clic sulla scaletta non avvia piu' la parte (partiva da solo):
    # apre la modifica della parte, dove si cambia la durata a mano.  Per
    # avviarla c'e' il tasto destro > Inizia questa parte.
    import src.views.meeting_view as mv
    from PyQt6.QtCore import Qt

    def doppio_clic(self, item, colonna):
        dati = item.data(0, Qt.ItemDataRole.UserRole)
        if dati and dati[0] == "part":
            self._edit_part(item)

    mv.MeetingView._part_double_clicked = doppio_clic

    # Il titolo del discorso del sorvegliante, scritto a mano, si aggiunge
    # alla parte che la visita introduce.
    import src.controllers.meeting_controller as mc

    visita_originale = mc.MeetingController.apply_co_visit_modifications

    def visita_con_titolo(self, meeting):
        modificata = visita_originale(self, meeting)
        modificata._co_applicata = True       # versione «visita»: non si salva sui file
        import opzioni
        settimana = self.settings_manager.settings.co_visit.week_start_date
        titoli = opzioni.titoli_visita(settimana)
        t = self._get_translations(meeting.language)

        def con(parte, titolo):
            if titolo and titolo not in parte.title:
                parte.title = f"{parte.title}: {titolo}"

        for i, sezione in enumerate(modificata.sections):
            for j, parte in enumerate(sezione.parts):
                if parte.title == t.get("service_talk"):
                    con(parte, titoli["servizio"])
                elif parte.title == t.get("co_talk"):
                    con(parte, titoli["finale"])
                elif (i == 0 and j == 1 and meeting.meeting_type.value == "weekend"):
                    con(parte, titoli["pubblico"])       # discorso pubblico, all'inizio
        return modificata

    mc.MeetingController.apply_co_visit_modifications = visita_con_titolo

    # La versione «visita» dell'adunanza non va scritta sul file dell'adunanza:
    # al prossimo avvio si applicherebbe una seconda volta sopra la prima.
    salva_originale_m = mc.MeetingController.save_meeting

    def salva_senza_visita(self, meeting):
        if getattr(meeting, "_co_applicata", False) or _ha_parti_della_visita(self, meeting):
            return
        return salva_originale_m(self, meeting)

    mc.MeetingController.save_meeting = salva_senza_visita

    # Cambiare una parte a mano (titolo, cantico, durata) aggiorna anche il
    # pannello Contenuti.
    modifica_originale = mv.MeetingView._edit_part

    def modifica_e_contenuti(self, item):
        modifica_originale(self, item)
        w = self
        while w is not None and not hasattr(w, "contenuti"):
            w = w.parentWidget()
        if w is not None and self.meeting is not None:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: w.contenuti.imposta_adunanza(
                self.meeting, mantieni=True))

    mv.MeetingView._edit_part = modifica_e_contenuti

    # Per un cantico basta scrivere il NUMERO: il titolo si ricompone da solo
    # («Cantico 45 e preghiera») e non si rischia di rovinarlo.
    originale_dialogo = mv.PartEditDialog.__init__
    originale_aggiornata = mv.PartEditDialog.get_updated_part

    def dialogo_cantico(self, part, parent=None):
        originale_dialogo(self, part, parent)
        _numero_nel_dialogo(self, parent)

    def aggiornata_cantico(self):
        nuova = originale_aggiornata(self)
        if getattr(self, "numero_cantico", None) is not None:
            nuova.title = _titolo_con_numero(self.part.title, self.numero_cantico.value(),
                                             self._traduzioni)
            nuova.presenter = self.part.presenter
        return nuova

    mv.PartEditDialog.__init__ = dialogo_cantico
    mv.PartEditDialog.get_updated_part = aggiornata_cantico

    class MonitorConComandi(schermo_timer.MonitorTimer):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            monitor_timer.installa_comandi(self)

    mw.SecondaryDisplay = MonitorConComandi

    import correzioni
    correzioni.applica()
