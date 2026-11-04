"""La finestra «Aggiungi contenuti» del timer, nello stile dell'app.

Prima di aprire la finestra del sistema per scegliere un file, si sceglie
fra quello che l'app ha gia':

    Nuovi contenuti     gli ultimi video e audio del catalogo (come nella Home)
    Preferiti           i video e gli audio messi fra i preferiti
    Cerca               la barra in alto cerca in tutto il catalogo
    Dal computer        un file esterno all'app: si apre la finestra di sistema

Nei Preferiti e nella ricerca ci sono anche le pubblicazioni: hanno la
copertina e solo «Scarica» (una pubblicazione non e' un media da mostrare).

Ogni riga ha «Aggiungi» (lo mette fra i contenuti dell'adunanza) e «Scarica»
(lo aggiunge e lo scarica; se i video hanno piu' risoluzioni si sceglie come
in tutto il resto dell'app).  Lo scaricamento si vede sulla riga.
"""
from __future__ import annotations

import re
import unicodedata

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from concurrent.futures import ThreadPoolExecutor

SEZIONI = ("Nuovi contenuti", "Preferiti", "Dal computer")
#: Le anteprime si scaricano quattro alla volta, non sessanta insieme.
_ANTEPRIME = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anteprima")
LATO_ANTEPRIMA = 64
MAX_RISULTATI = 60


def _senza_accenti(testo: str) -> str:
    n = unicodedata.normalize("NFD", testo or "")
    return "".join(c for c in n if not unicodedata.combining(c)).casefold()


def voce_da_scheda(scheda: dict) -> dict | None:
    """Dalla scheda del catalogo alla voce che il pannello sa mostrare."""
    formato = str(scheda.get("formato") or "").upper()
    sigla = scheda.get("sigla") or ""
    if not sigla and scheda.get("docid"):
        sigla = f"docid-{scheda['docid']}"
    try:
        traccia = int(scheda.get("traccia") or 0)
    except (TypeError, ValueError):
        traccia = 0
    if formato not in ("VIDEO", "AUDIO") or not sigla or not traccia:
        return None
    emissione = re.sub(r"\D", "", str(scheda.get("numero") or ""))
    return {"tipo": "video" if formato == "VIDEO" else "audio", "sigla": sigla,
            "traccia": traccia, "numero": int(emissione) * 100 if emissione else 0,
            "lingua": scheda.get("lingua") or "I", "titolo": scheda.get("titolo") or sigla,
            "durata": scheda.get("durata") or "", "pubblicato": scheda.get("pubblicato") or "",
            "miniatura_url": scheda.get("miniatura") or ""}


def nuovi_contenuti(lingua: str) -> list[dict]:
    from Utility import CatalogoMedia
    try:
        return [v for v in (voce_da_scheda(s) for s in CatalogoMedia.ultime(lingua)) if v]
    except Exception:  # noqa: BLE001 - catalogo non scaricato: elenco vuoto
        return []


def preferiti(lingua: str) -> list[dict]:
    """Tutti i preferiti: video, audio e pubblicazioni, nell'ordine in cui li hai messi."""
    from Utility import CatalogoMedia, Preferiti
    voci = []
    for p in Preferiti.voci():
        if p.get("lingua", lingua) != lingua:
            continue
        sigla = p.get("pubblicazione", "")
        if not p.get("traccia"):
            voci.append({"tipo": "pubblicazione", "sigla": sigla, "lingua": lingua,
                         "titolo": p.get("titolo") or sigla})
            continue
        traccia = int(p["traccia"])
        formato = str(p.get("formato") or "VIDEO").upper()
        scheda = {"sigla": sigla, "lingua": lingua, "traccia": traccia, "formato": formato,
                  "titolo": p.get("titolo") or sigla}
        try:
            dal_catalogo = CatalogoMedia.voce_di(sigla, lingua, traccia)
            if dal_catalogo:
                dal = CatalogoMedia._scheda(dal_catalogo)
                # Il titolo del catalogo e' quello vero: nei preferiti puo' essere
                # rimasto «lffv - traccia 1».
                scheda.update(durata=dal["durata"], miniatura=dal["miniatura"],
                              titolo=dal["titolo"] or scheda["titolo"])
        except Exception:  # noqa: BLE001
            pass
        v = voce_da_scheda(scheda)
        if v:
            voci.append(v)
    return voci


def cerca_nel_catalogo(domanda: str, lingua: str) -> list[dict]:
    """Tutte le parole della domanda nel titolo; il video vince sull'audio."""
    parole = [_senza_accenti(p) for p in domanda.split() if p.strip()]
    if not parole:
        return []
    from Utility import CatalogoMedia
    try:
        catalogo = CatalogoMedia._leggi(lingua)["voci"]
    except Exception:  # noqa: BLE001
        return []
    trovati: dict = {}
    visti = set()
    for voce in catalogo.values():
        if id(voce) in visti:
            continue
        visti.add(id(voce))
        titolo = _senza_accenti(voce.get("title") or "")
        if not all(p in titolo for p in parole):
            continue
        scheda = CatalogoMedia._scheda(voce)
        v = voce_da_scheda(scheda)
        if v is None:
            continue
        k = " ".join(titolo.split())
        if k not in trovati or (v["tipo"] == "video" and trovati[k]["tipo"] != "video"):
            trovati[k] = v
    ordinati = sorted(trovati.values(), key=lambda v: v.get("pubblicato") or "", reverse=True)
    return ordinati[:MAX_RISULTATI]


class _RigaCatalogo(QFrame):
    def __init__(self, voce: dict, colori: dict, dialogo) -> None:
        super().__init__()
        self._voce, self._dialogo = voce, dialogo
        self.setObjectName("rigaAggiungi")
        self.setStyleSheet(
            f"#rigaAggiungi {{ background-color: {colori['pannello']};"
            f" border: 1px solid {colori['bordo']}; border-radius: 8px; }}"
            f" QLabel {{ background: transparent; color: {colori['testo']}; }}")
        riga = QHBoxLayout(self)
        riga.setContentsMargins(10, 8, 10, 8)
        riga.setSpacing(10)
        from Utility.Stuff import icona_tabler
        self._anteprima = QLabel()
        self._anteprima.setFixedSize(LATO_ANTEPRIMA, LATO_ANTEPRIMA)
        self._anteprima.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._anteprima.setStyleSheet(
            f"background-color: {colori['griglia']}; border-radius: 6px;")
        nome_icona = {"video": "video", "audio": "music"}.get(voce["tipo"], "book")
        self._anteprima.setPixmap(icona_tabler(nome_icona, colori["icona"], 28).pixmap(28, 28))
        riga.addWidget(self._anteprima)
        dialogo.carica_anteprima(self, voce)

        testi = QVBoxLayout()
        testi.setSpacing(2)
        titolo = QLabel(voce["titolo"])
        titolo.setWordWrap(True)
        titolo.setStyleSheet("font-weight: 600;")
        meta = [{"video": "Video", "audio": "Audio"}.get(voce["tipo"], "Pubblicazione")]
        if voce.get("durata"):
            meta.append(voce["durata"])
        if voce.get("pubblicato"):
            meta.append(voce["pubblicato"])
        sotto = QLabel(" · ".join(meta))
        sotto.setStyleSheet(f"color: {colori['grigio']}; font-size: 12px;")
        testi.addWidget(titolo)
        testi.addWidget(sotto)
        self._barra = QProgressBar()
        self._barra.setFixedHeight(12)
        self._barra.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {colori['bordo']}; border-radius: 4px;"
            f" background: {colori['sfondo']}; color: {colori['testo']}; font-size: 9px;"
            f" text-align: center; }}"
            " QProgressBar::chunk { background-color: #a77fd4; border-radius: 3px; }")
        self._barra.setVisible(False)
        testi.addWidget(self._barra)
        riga.addLayout(testi, 1)

        self._aggiungi = QPushButton()
        self._aggiungi.clicked.connect(lambda: dialogo.aggiungi(voce))
        if voce["tipo"] != "pubblicazione":
            riga.addWidget(self._aggiungi)
        self._scarica = QPushButton()
        self._scarica.clicked.connect(lambda: dialogo.scarica(voce))
        riga.addWidget(self._scarica)
        self.aggiorna()

    def metti_anteprima(self, pixmap) -> None:
        self._anteprima.setStyleSheet("background: transparent; border-radius: 6px;")
        self._anteprima.setPixmap(pixmap.scaled(
            LATO_ANTEPRIMA, LATO_ANTEPRIMA, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def aggiorna(self) -> None:
        d = self._dialogo
        aggiunto = d.e_aggiunto(self._voce)
        self._aggiungi.setText("✔ Aggiunto" if aggiunto else "Aggiungi")
        self._aggiungi.setEnabled(not aggiunto)
        if d.e_scaricato(self._voce):
            self._scarica.setText("✔ Scaricata" if self._voce["tipo"] == "pubblicazione"
                                  else "✔ Scaricato")
            self._scarica.setEnabled(False)
        elif d.in_attesa(self._voce):
            self._scarica.setText("Scaricamento…")
            self._scarica.setEnabled(False)
        elif self._barra.isVisible():
            self._scarica.setText("In corso…")
            self._scarica.setEnabled(False)
        else:
            self._scarica.setText("Scarica")
            self._scarica.setEnabled(True)

    def avanzamento(self, scritti: int, totale: int) -> None:
        self._barra.setVisible(True)
        if totale > 0:
            per_cento = min(100, int(scritti * 100 / totale))
            self._barra.setRange(0, 100)
            self._barra.setValue(per_cento)
            self._barra.setFormat(f"{per_cento}%")
        else:
            self._barra.setRange(0, 0)
        self.aggiorna()

    def finito(self, esito: str) -> None:
        self._barra.setVisible(False)
        self.aggiorna()
        if esito == "errore":
            self._scarica.setText("Riprova")


class DialogoAggiungi(QDialog):
    """La finestra. `pannello` e' il PannelloContenuti che riceve le scelte."""

    def __init__(self, pannello, finestra) -> None:
        super().__init__(finestra)
        from Utility import Lingua, tema
        self._pannello = pannello
        self._lingua = Lingua.corrente_simbolo()
        self._colori = c = tema.colori(tema.tema_attivo())
        self._righe: dict = {}
        self._catalogo_pub = None
        self._attesa_pub: dict = {}
        self._sonda = QTimer(self)          # controlla se la pubblicazione e' arrivata
        self._sonda.setInterval(1500)
        self._sonda.timeout.connect(self._controlla_pubblicazioni)
        self._sezione = 0
        self.setWindowTitle("Aggiungi contenuti")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(640, 640)
        self.setStyleSheet(
            f"QDialog {{ background-color: {c['sfondo']}; }}"
            f" QLabel {{ color: {c['testo']}; background: transparent; }}"
            " QPushButton { background-color: #64398b; color: white; border: none;"
            " border-radius: 4px; padding: 7px 14px; }"
            " QPushButton:hover { background-color: #a77fd4; }"
            " QPushButton:disabled { background-color: #4a4a55; color: #aaaaaa; }"
            f" QPushButton#scheda {{ background: transparent; color: {c['testo']};"
            f" border: 1px solid {c['bordo']}; }}"
            " QPushButton#scheda:checked { background-color: #64398b; color: white;"
            " border-color: #64398b; }"
            f" QLineEdit {{ background-color: {c['pannello']}; color: {c['testo']};"
            f" border: 1px solid {c['bordo']}; border-radius: 6px; padding: 7px 10px; }}")

        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(14, 12, 14, 12)
        colonna.setSpacing(8)
        titolo = QLabel("Aggiungi contenuti all'adunanza")
        titolo.setStyleSheet("font-size: 16px; font-weight: 700;")
        colonna.addWidget(titolo)

        self._cerca = QLineEdit()
        self._cerca.setPlaceholderText("Cerca un video o un audio nel catalogo…")
        self._cerca.setClearButtonEnabled(True)
        self._cerca.textChanged.connect(self._testo_cambiato)
        colonna.addWidget(self._cerca)
        self._ritardo = QTimer(self)
        self._ritardo.setSingleShot(True)
        self._ritardo.setInterval(250)
        self._ritardo.timeout.connect(self._riempi)

        schede = QHBoxLayout()
        schede.setSpacing(6)
        self._schede: list[QPushButton] = []
        for i, nome in enumerate(SEZIONI):
            b = QPushButton(nome)
            b.setObjectName("scheda")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, i=i: self._scegli(i))
            schede.addWidget(b)
            self._schede.append(b)
        schede.addStretch(1)
        colonna.addLayout(schede)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        colonna.addWidget(self._area, 1)

        chiudi = QHBoxLayout()
        chiudi.addStretch(1)
        fine = QPushButton("Chiudi")
        fine.clicked.connect(self.accept)
        chiudi.addWidget(fine)
        colonna.addLayout(chiudi)

        from Utility import AvanzamentoMedia
        canale = AvanzamentoMedia.canale()
        canale.avanza.connect(self._avanza)
        canale.finito.connect(self._finito)
        self.finished.connect(lambda _r: self._scollega(canale))
        self._scegli(0)

    def _scollega(self, canale) -> None:
        for segnale, slot in ((canale.avanza, self._avanza), (canale.finito, self._finito)):
            try:
                segnale.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    # --- stato -----------------------------------------------------------
    def e_aggiunto(self, voce: dict) -> bool:
        if voce["tipo"] == "pubblicazione":
            return False
        return self._pannello.e_aggiunto(voce)

    def e_scaricato(self, voce: dict) -> bool:
        if voce["tipo"] == "pubblicazione":
            pub = self._pub_di(voce)
            return pub is not None and self._pannello.pubblicazione_scaricata(pub)
        return self._pannello.e_scaricato(voce)

    def in_attesa(self, voce: dict) -> bool:
        return voce["tipo"] == "pubblicazione" and id(voce) in self._attesa_pub

    def aggiungi(self, voce: dict) -> None:
        self._pannello.aggiungi_media(voce)
        self._aggiorna_righe()

    def scarica(self, voce: dict) -> None:
        if voce["tipo"] == "pubblicazione":
            self._scarica_pubblicazione(voce)
            return
        # La risoluzione si sceglie con un menu che nasce da questa finestra.
        self._pannello.scarica_media_aggiunto(voce, self, self._aggiorna_righe)

    # --- pubblicazioni ----------------------------------------------------
    def _pub_di(self, voce: dict):
        """L'oggetto pubblicazione del catalogo per una voce dei preferiti."""
        if voce.get("_pub") is not None:
            return voce["_pub"]
        if self._catalogo_pub is None:
            from Utility.DBManager import DBManager
            from Utility import Lingua
            try:
                tutte = DBManager.get_publications(Lingua.da_simbolo(self._lingua))
            except Exception:  # noqa: BLE001
                tutte = []
            self._catalogo_pub = {}
            for pub in tutte:
                self._catalogo_pub.setdefault(pub.keySymbol, pub)
        voce["_pub"] = self._catalogo_pub.get(voce.get("sigla"))
        return voce["_pub"]

    def _scarica_pubblicazione(self, voce: dict) -> None:
        pub = self._pub_di(voce)
        if pub is None:
            return
        self._attesa_pub[id(voce)] = voce
        self._pannello.scarica_pubblicazione(pub)
        self._sonda.start()
        self._aggiorna_righe()

    def _controlla_pubblicazioni(self) -> None:
        for k, voce in list(self._attesa_pub.items()):
            if self.e_scaricato(voce):
                del self._attesa_pub[k]
        if not self._attesa_pub:
            self._sonda.stop()
        self._aggiorna_righe()

    # --- anteprime --------------------------------------------------------
    def carica_anteprima(self, riga, voce: dict) -> None:
        """Mette l'immagine sulla riga: subito se e' in cache, altrimenti dalla rete."""
        from Utility import Copertine
        if voce["tipo"] == "pubblicazione":
            pub = self._pub_di(voce)
            if pub is None:
                return
            dati = Copertine.dati_gia_in_cache(pub)
            cerca = lambda: Copertine.dati_copertina(pub)  # noqa: E731
        else:
            url = voce.get("miniatura_url") or ""
            if not url:
                return
            dati = Copertine.gia_in_cache(url)
            cerca = lambda: Copertine.scarica(url)  # noqa: E731
        if dati:
            self._applica_anteprima(riga, dati)
            return

        def lavoro() -> None:
            try:
                scaricati = cerca()
            except Exception:  # noqa: BLE001 - niente rete: resta l'icona
                return
            if scaricati:
                from Utility.Extensions.Ext_DispatchQueue import on_main
                on_main(lambda: self._applica_anteprima(riga, scaricati))

        _ANTEPRIME.submit(lavoro)

    @staticmethod
    def _applica_anteprima(riga, dati: bytes) -> None:
        from Utility import Copertine
        pixmap = Copertine.pixmap_da_dati(dati)
        if pixmap is None:
            return
        try:
            riga.metti_anteprima(pixmap)
        except RuntimeError:        # la riga non c'e' piu': la lista e' stata rifatta
            pass

    def _aggiorna_righe(self) -> None:
        for r in self._righe.values():
            r.aggiorna()

    def _chiave(self, voce: dict):
        from Utility import AvanzamentoMedia
        return AvanzamentoMedia.chiave_di(voce)

    def _avanza(self, k, scritti: int, totale: int) -> None:
        riga = self._righe.get(k)
        if riga is not None:
            riga.avanzamento(scritti, totale)

    def _finito(self, k, esito: str) -> None:
        riga = self._righe.get(k)
        if riga is not None:
            riga.finito(esito)

    # --- sezioni ---------------------------------------------------------
    def _scegli(self, i: int) -> None:
        self._sezione = i
        for n, b in enumerate(self._schede):
            b.setChecked(n == i)
        self._cerca.setEnabled(i != 2)
        self._riempi()

    def _testo_cambiato(self, _t: str) -> None:
        # Scrivere nella barra porta alla ricerca, da qualunque scheda.
        for b in self._schede:
            b.setChecked(False)
        self._ritardo.start()

    def _riempi(self) -> None:
        interno = QWidget()
        elenco = QVBoxLayout(interno)
        elenco.setContentsMargins(0, 0, 4, 8)
        elenco.setSpacing(6)
        self._righe = {}
        domanda = self._cerca.text().strip()
        if domanda:
            voci = cerca_nel_catalogo(domanda, self._lingua) + self._cerca_pubblicazioni(domanda)
            vuoto = "Niente con queste parole."
        elif self._sezione == 0:
            voci, vuoto = nuovi_contenuti(self._lingua), (
                "Il catalogo dei media non è ancora scaricato: aggiornalo dalle Impostazioni.")
        elif self._sezione == 1:
            voci, vuoto = preferiti(self._lingua), (
                "Non hai ancora niente fra i preferiti. Si aggiungono dalla sezione "
                "Pubblicazioni o Multimedia, con il tasto destro o il menu «…».")
        else:
            self._sezione_computer(elenco)
            elenco.addStretch(1)
            self._area.setWidget(interno)
            return
        if not domanda:
            for i, b in enumerate(self._schede):
                b.setChecked(i == self._sezione)
        if not voci:
            etichetta = QLabel(vuoto)
            etichetta.setWordWrap(True)
            etichetta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            etichetta.setStyleSheet(f"color: {self._colori['grigio']}; padding: 28px;")
            elenco.addWidget(etichetta)
        for v in voci:
            riga = _RigaCatalogo(v, self._colori, self)
            k = self._chiave(v)
            if k is not None:
                self._righe[k] = riga
            elenco.addWidget(riga)
        elenco.addStretch(1)
        self._area.setWidget(interno)

    def _cerca_pubblicazioni(self, domanda: str, massimo: int = 20) -> list[dict]:
        from Utility.DBManager import DBManager
        from Utility import Lingua
        try:
            trovate = DBManager.cerca_pubblicazioni(domanda, Lingua.da_simbolo(self._lingua))
        except Exception:  # noqa: BLE001
            return []
        voci = []
        for pub in trovate[:massimo]:
            voci.append({"tipo": "pubblicazione", "sigla": pub.keySymbol, "_pub": pub,
                         "lingua": self._lingua,
                         "titolo": getattr(pub, "issueTitle", "") or pub.title})
        return voci

    def _sezione_computer(self, elenco: QVBoxLayout) -> None:
        testo = QLabel(
            "Un file che non fa parte dell'app: immagine, video, audio, PDF, Word, Excel, "
            "LibreOffice. Si apre la finestra del sistema per sceglierlo; il file non viene "
            "copiato e resta dove è.")
        testo.setWordWrap(True)
        testo.setStyleSheet("padding: 8px 2px;")
        elenco.addWidget(testo)
        scegli = QPushButton("Scegli file dal computer…")
        scegli.setCursor(Qt.CursorShape.PointingHandCursor)
        scegli.clicked.connect(self._scegli_file)
        elenco.addWidget(scegli, 0, Qt.AlignmentFlag.AlignLeft)

    def _scegli_file(self) -> None:
        self.accept()
        QTimer.singleShot(0, self._pannello.scegli_file_esterni)
