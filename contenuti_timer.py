"""Il pannello Contenuti del timer: i media dell'adunanza, divisi per parte.

Clone della schermata «Contenuti multimediali» di JW LibriX (SubViews/
ContenutiView.py), che resta com'e'.  Qui:
    - i media sono raggruppati per parte della scaletta (senza i tempi)
    - la parte in corso e' in chiaro, le altre sono scure: la scheda della
      parte in corso si clicca ovunque, le altre solo con i due tasti
    - quello che e' gia' stato mostrato torna scuro (si puo' rimostrare
      coi tasti)
    - giovedi' -> Guida per l'adunanza (mwb), fine settimana -> studio (w)
    - con la visita del sorvegliante i media dello studio biblico di
      congregazione non compaiono, perche' quella parte non si fa
    - i file esterni aggiunti si ricordano e stanno in fondo
    - il pannello si nasconde; con l'opzione "avvia in automatico", quando
      inizia una parte che e' un cantico parte il cantico
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import opzioni
from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QCheckBox, QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                             QToolButton, QVBoxLayout, QWidget)

VERDE = "#4ade80"
ARANCIO = "#fbbf24"
ROSSO = "#f87171"
ETICHETTA = {"immagine": "Immagine", "video": "Video", "audio": "Audio",
             "documento": "Documento"}


# ----------------------------------------------------------------------
# DA DOVE VENGONO I MEDIA
# ----------------------------------------------------------------------

def _giorno(meeting) -> date:
    d = meeting.date
    return d.date() if isinstance(d, datetime) else d


def trova_pagina(meeting):
    """(pub, documento) della settimana di questa adunanza, o None."""
    from SubViews import AdunanzeView as A
    from src.models.meeting import MeetingType

    giorno = _giorno(meeting)
    if meeting.meeting_type == MeetingType.MIDWEEK:
        for s in A.tutte_le_settimane():
            if s.contiene(giorno):
                return s.pub, s.documento
        return None
    return A.articolo_di_studio(giorno - timedelta(days=giorno.weekday()))


def chiave_voce(v: dict):
    """Cosa rende «la stessa» una voce (per sapere se e' gia' stata mostrata)."""
    if v.get("esterno"):
        return ("esterno", v.get("percorso"))
    from Utility import JWPubManager as J
    return J._chiave_media(v)


def pubblicazione_da_scaricare(meeting):
    """La riga del catalogo della pubblicazione che serve a questa adunanza, o None.

    Giovedi': il numero della Guida per l'adunanza (mwb) che contiene la
    settimana.  Fine settimana: il numero di Torre di Guardia (w) di studio.
    """
    from SubViews import AdunanzeView as A
    from src.models.meeting import MeetingType
    giorno = _giorno(meeting)
    if meeting.meeting_type == MeetingType.MIDWEEK:
        return A.numero_da_scaricare(giorno)
    return A.numero_studio_da_scaricare(giorno - timedelta(days=giorno.weekday()))


def richiesta_download(pub) -> dict:
    """Lo stesso dizionario che usa la sezione Adunanze per scaricare."""
    from Utility import Lingua
    from Utility.JWPubManager import pub_dir_name
    return {"sigla": pub.keySymbol, "lingua": Lingua.corrente_simbolo(),
            "numero": (pub_dir_name(pub).rsplit("_", 1)[-1] if pub.issueTagNumber else ""),
            "titolo": pub.issueTitle or pub.title, "apri": False}


def pubblicazioni_scadute() -> list:
    """Guide e studi scaricati le cui settimane sono tutte passate.

    Sono solo i pacchetti (testi e immagini della pagina): i video e gli audio,
    cantici compresi, non si toccano.
    """
    from SubViews import AdunanzeView as A
    oggi = date.today()
    lunedi = oggi - timedelta(days=oggi.weekday())
    scadute = []
    for sigla, campo in ((A.SIGLA, "title"), (A.SIGLA_STUDIO, "contextTitle")):
        for pub in A.pacchetti_scaricati(sigla):
            anno, mese = A._anno_mese(pub)
            inizi = []
            for d in A.JWPubManager.get_documents(pub):
                testo = getattr(d, campo, "") or ""
                if sigla == A.SIGLA and (d.ID == 0 or testo.lower().startswith("guida")):
                    continue
                if not testo:
                    continue
                i = A.inizio_settimana(testo, anno, mese)
                if i:
                    inizi.append(i)
            if inizi and max(inizi) + timedelta(days=6) < lunedi:
                scadute.append(pub)
    return scadute


def _tracce(v: dict):
    """I numeri con cui il file della voce si chiama sul disco.

    Un media di un periodico ha anche il numero dell'edizione: la voce dice
    `numero` 20260900 e `traccia` 2, il file e' `mwbv_I_202609_02_r720P.mp4`.
    Con la sola traccia `file_di` non lo trovava mai, e il video scaricato
    restava «solo streaming» per sempre.
    """
    numero = str(int(v.get("numero") or 0))
    if numero == "0":
        return v["traccia"]
    if numero.endswith("00"):
        numero = numero[:-2]
    return [int(numero), int(v["traccia"])]


def _prepara(v: dict, lingua: str) -> bool:
    from Utility import CatalogoMedia, MediaScaricati
    if v["tipo"] == "immagine":
        try:
            with open(v["file"], "rb") as f:
                dati = f.read()
        except OSError:
            return False
        v.update(dati=dati, miniatura=dati)
        return True
    sigla, traccia, numero = v["sigla"], v["traccia"], v["numero"]
    formato = "VIDEO" if v["tipo"] == "video" else "AUDIO"
    titolo = ""
    if not numero:
        titolo = (CatalogoMedia.voce_di(sigla, lingua, traccia) or {}).get("title") or ""
    v["titolo"] = v["titolo"] or titolo or f"{sigla} n. {traccia}"
    v["lingua"], v["formato"] = lingua, formato
    file = MediaScaricati.file_di(sigla, lingua, _tracce(v), formato)
    v["file"] = str(file) if file else ""
    v["scaricato"] = file is not None
    v["miniatura"] = None
    return True


def voci_della_pagina(pub, documento) -> list[dict]:
    from Utility import JWPubManager as J
    from Utility import Lingua
    lingua = Lingua.da_numero(getattr(pub, "mepsLanguageId", Lingua.PREDEFINITA))
    elenco = J.contenuti_del_documento(pub, documento.ID)
    elenco += J.contenuti_citati(pub, documento.ID, elenco)
    return [v for v in elenco if _prepara(v, lingua)]


def aggiorna_stato(voci: list[dict]) -> bool:
    """Rilegge dal disco cosa e' stato scaricato; True se qualcosa e' cambiato."""
    from Utility import MediaScaricati
    cambiato = False
    for v in voci:
        if v.get("esterno") or v["tipo"] not in ("video", "audio"):
            continue
        file = MediaScaricati.file_di(v["sigla"], v["lingua"], _tracce(v), v["formato"])
        ora = str(file) if file else ""
        if ora != v.get("file"):
            v["file"], v["scaricato"] = ora, file is not None
            cambiato = True
    return cambiato


def numero_cantico(titolo: str) -> int | None:
    """Il numero di un cantico dal titolo della parte («Cantico 125 e preghiera»)."""
    m = re.match(r"\s*(cantico|canto|song|cantique|lied|canci[oó]n|c[aâ]ntico)\b[^\d]*(\d{1,3})",
                 titolo or "", re.IGNORECASE)
    return int(m.group(2)) if m else None


def cantici_delle_parti(parti: list, pub) -> list[dict]:
    """Un video (o audio) del cantico per ogni parte che e' un cantico con numero."""
    from Utility import CatalogoMedia, Lingua
    lingua = Lingua.da_numero(getattr(pub, "mepsLanguageId", Lingua.PREDEFINITA))
    voci = []
    for i, parte in enumerate(parti):
        n = numero_cantico(parte.title)
        if n is None:
            continue
        formati = {f for (num, f) in CatalogoMedia.tracce_di("sjjm", lingua) if num == n}
        if not formati:
            continue
        tipo = "video" if "VIDEO" in formati else "audio"
        voce = {"tipo": tipo, "titolo": "", "sigla": "sjjm", "traccia": n, "numero": 0,
                "parte_indice": i}
        if _prepara(voce, lingua):
            voci.append(voce)
    return voci


# ----------------------------------------------------------------------
# A QUALE PARTE APPARTIENE OGNI MEDIA
# ----------------------------------------------------------------------

def _ordinali(pub, documento) -> tuple[dict, dict]:
    """(ordinale di paragrafo per media, ordinale per titolo di documento citato)."""
    from Utility import JWPubManager as J
    per_media: dict = {}
    per_citato: dict = {}
    c = J._connect(pub)
    if c is None:
        return per_media, per_citato
    try:
        for mime, percorso, sigla, traccia, numero, ordinale in c.execute(
                "SELECT m.MimeType, m.FilePath, m.KeySymbol, m.Track, m.IssueTagNumber, "
                "dm.BeginParagraphOrdinal FROM DocumentMultimedia dm "
                "JOIN Multimedia m USING (MultimediaId) WHERE dm.DocumentId = ?",
                (documento.ID,)):
            mime = str(mime or "")
            if mime.startswith("image/"):
                chiave = ("immagine", Path(str(percorso or "")).name)
            elif mime.startswith(("video/", "audio/")) and sigla:
                chiave = (str(sigla), int(traccia or 0), int(numero or 0),
                          "video" if mime.startswith("video/") else "audio")
            else:
                continue
            if ordinale is not None and (chiave not in per_media or per_media[chiave] is None):
                per_media[chiave] = int(ordinale)
            else:
                per_media.setdefault(chiave, None)
        collegamenti = c.execute(
            "SELECT h.Link, dh.BeginParagraphOrdinal FROM DocumentHyperlink dh "
            "JOIN Hyperlink h USING (HyperlinkId) WHERE dh.DocumentId = ? "
            "ORDER BY dh.DocumentHyperlinkId", (documento.ID,)).fetchall()
    except Exception:  # noqa: BLE001 - senza ordinali i media vanno in «altri»
        return per_media, per_citato
    finally:
        c.close()
    from Utility import RiferimentiLocali
    import sqlite3
    visti = set()
    for link, ordinale in collegamenti:
        m = re.match(r"^jwpub://p/[A-Za-z]+:(\d+)", str(link or ""))
        if not m or ordinale is None or m.group(1) in visti:
            continue
        visti.add(m.group(1))
        posto = RiferimentiLocali._pacchetto_del_documento(int(m.group(1)))
        if posto is None:
            continue
        db, locale = posto
        try:
            altra = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            titolo = altra.execute("SELECT Title FROM Document WHERE DocumentId = ?",
                                   (locale,)).fetchone()
            altra.close()
        except Exception:  # noqa: BLE001
            continue
        if titolo and titolo[0]:
            per_citato.setdefault(titolo[0], int(ordinale))
    return per_media, per_citato


def _intestazioni(documento) -> tuple[dict, list]:
    """({pid: posizione}, [(posizione, testo del titolo h3])]) della pagina scaricata."""
    from Utility.Extensions.Ext_FileManager import get_documents_directory
    file = get_documents_directory() / "Documents_I" / f"{documento.documentId}.html"
    try:
        html = file.read_text(encoding="utf-8")
    except OSError:
        return {}, []
    pid = {int(m.group(1)): m.start() for m in re.finditer(r'data-pid="(\d+)"', html)}
    titoli = [(m.start(), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip())
              for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", html, re.S)]
    return pid, titoli


def _numero_titolo(testo: str) -> int | None:
    m = re.match(r"\s*(\d+)\s*\.", testo or "")
    return int(m.group(1)) if m else None


def _e_cantico(titolo: str) -> bool:
    return bool(re.search(r"(?<![\d.])\d{1,3}(?![\d.])", titolo or "")) and not re.match(
        r"\s*\d+\s*\.", titolo or "")


def assegna_alle_parti(voci: list[dict], pub, documento, parti: list, co_attivo: bool,
                       settimanale: bool) -> list[dict]:
    """Per ogni media: l'indice della parte (o None) o la sua esclusione.

    Ritorna una lista di gruppi: {"indice": int|None, "titolo": str, "voci": [...]}.
    """
    titoli = [p.title for p in parti]
    per_media, per_citato = _ordinali(pub, documento)
    pid, intest = _intestazioni(documento)

    def titolo_h3_di(ordinale):
        if not intest:
            return None
        pos = 0
        if ordinale is not None and pid:
            if ordinale in pid:
                pos = pid[ordinale]
            else:
                piu_bassi = [n for n in pid if n <= ordinale]
                pos = pid[max(piu_bassi)] if piu_bassi else 0
        scelto = None
        for p, testo in intest:
            if p <= pos:
                scelto = testo
        return scelto if scelto is not None else intest[0][1]

    def parte_per_numero(n):
        for i, t in enumerate(titoli):
            if _numero_titolo(t) == n:
                return i
        return None

    def parte_cantico(n):
        for i, t in enumerate(titoli):
            if re.search(rf"(?<![\d.]){n}(?![\d.])", t) and _numero_titolo(t) is None:
                return i
        return None

    def parte_studio():
        # lo studio: la parte piu' lunga che non e' un cantico, ne' un discorso
        # del sorvegliante (con la visita dura 30 minuti come il discorso: a
        # parita' vale la prima)
        candidati = [(p.duration_minutes, i) for i, p in enumerate(parti)
                     if numero_cantico(p.title) is None and i > 1
                     and not re.search(r"sorveglian|overseer|surveillant|aufseher|superintend",
                                       p.title, re.IGNORECASE)]
        return max(candidati, key=lambda t: (t[0], -t[1]))[1] if candidati else None

    assegnati: dict = {}
    for v in voci:
        indice = None
        escludi = False
        if v.get("parte_indice") is not None:
            indice = v["parte_indice"]
        elif v["tipo"] in ("video", "audio") and v.get("sigla") == "sjjm":
            indice = parte_cantico(v["traccia"])
        elif settimanale:
            indice = parte_studio()
        else:
            ordinale = per_citato.get(v.get("gruppo")) if v.get("gruppo") \
                else per_media.get(chiave_voce(v))
            testo = titolo_h3_di(ordinale)
            n = _numero_titolo(testo or "")
            if n is not None:
                indice = parte_per_numero(n)
                if indice is None and co_attivo:
                    escludi = True          # parte che con la visita non si fa
        if not escludi:
            assegnati.setdefault(indice, []).append(v)
    gruppi = [{"indice": i, "titolo": titoli[i], "voci": assegnati[i]}
              for i in sorted(k for k in assegnati if k is not None)]
    if None in assegnati:
        gruppi.append({"indice": None, "titolo": "Altri contenuti", "voci": assegnati[None]})
    return gruppi


# ----------------------------------------------------------------------
# LA RIGA
# ----------------------------------------------------------------------

class _Riga(QFrame):
    LATO_W, LATO_H = 96, 54

    def __init__(self, voce: dict, colori: dict, pannello, attiva: bool, mostrata: bool,
                 cliccabile: bool | None = None, scarico=None) -> None:
        super().__init__()
        # `attiva` e' l'aspetto (chiara o scura); `cliccabile` dice se tutta la
        # scheda risponde al clic: lo fa per tutta la parte in corso, anche
        # per cio' che e' gia' stato mostrato (per rilanciarlo).
        self._voce, self._pannello = voce, pannello
        self._attiva = attiva if cliccabile is None else cliccabile
        cliccabile = self._attiva
        self.setObjectName("rigaContenuto")
        bordo = "#a77fd4" if attiva else colori["bordo"]
        sfondo = colori["pannello"] if attiva else colori["sfondo"]
        testo = colori["testo"] if attiva else colori["grigio"]
        self.setStyleSheet(
            f"#rigaContenuto {{ background-color: {sfondo};"
            f" border: {2 if attiva else 1}px solid {bordo}; border-radius: 8px; }}"
            f" #rigaContenuto:hover {{ background-color: "
            f"{colori['hover'] if attiva else sfondo}; }}"
            f" QLabel {{ background: transparent; color: {testo}; }}")
        if cliccabile:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        riga = QHBoxLayout(self)
        riga.setContentsMargins(10, 8, 10, 8)
        riga.setSpacing(10)

        miniatura = QLabel()
        miniatura.setFixedSize(self.LATO_W, self.LATO_H)
        miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        miniatura.setStyleSheet(f"background-color: {colori['griglia']}; border-radius: 6px;")
        pixmap = QPixmap()
        if voce.get("miniatura") and pixmap.loadFromData(voce["miniatura"]):
            miniatura.setPixmap(pixmap.scaled(
                self.LATO_W, self.LATO_H, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            from Utility.Stuff import icona_tabler
            icona = {"immagine": "image", "video": "video", "audio": "music",
                     "documento": "document-text"}[voce["tipo"]]
            miniatura.setPixmap(icona_tabler(icona, colori["icona"], 32).pixmap(32, 32))
        riga.addWidget(miniatura)

        testi = QVBoxLayout()
        testi.setSpacing(3)
        titolo = QLabel(voce.get("titolo") or ETICHETTA[voce["tipo"]])
        titolo.setWordWrap(True)
        titolo.setStyleSheet("font-weight: 600;")
        testi.addWidget(titolo)
        self._etichetta_stato = self._stato(voce, mostrata)
        testi.addWidget(self._etichetta_stato)
        # La barra di scaricamento: si vede solo mentre questo media scende.
        self._barra = QProgressBar()
        self._barra.setFixedHeight(14)
        self._barra.setTextVisible(True)
        self._barra.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {colori['bordo']}; border-radius: 4px;"
            f" background: {colori['sfondo']}; color: {colori['testo']}; font-size: 10px;"
            f" text-align: center; }}"
            " QProgressBar::chunk { background-color: #a77fd4; border-radius: 3px; }")
        self._barra.setVisible(False)
        testi.addWidget(self._barra)
        riga.addLayout(testi, 1)

        azioni = QVBoxLayout()
        azioni.setSpacing(4)
        riga.setSpacing(8)
        self.setStyleSheet(self.styleSheet() + " QPushButton { padding: 5px 8px; }")
        mostra = voce["tipo"] in ("immagine", "documento")
        apri = QPushButton("Mostra" if mostra else
                           ("Riproduci" if voce.get("scaricato") else "Riproduci online"))
        apri.setEnabled(not voce.get("mancante"))
        apri.clicked.connect(lambda: pannello.apri_voce(voce))
        azioni.addWidget(apri)
        self._scarica = None
        if voce["tipo"] in ("video", "audio") and not voce.get("scaricato"):
            self._scarica = QPushButton("Scarica")
            self._scarica.clicked.connect(lambda: pannello.scarica_voce(voce))
            azioni.addWidget(self._scarica)
        riga.addLayout(azioni)

        # I tasti per togliere stanno sempre in vista: la X toglie dall'elenco
        # (file esterni e contenuti aggiunti a mano: sul disco non si tocca
        # niente), il cestino cancella dal disco il file scaricato (chiede
        # conferma; e' lo stesso file che si vede in Scaricati).
        self._altro = None
        strumenti = QVBoxLayout()
        strumenti.setSpacing(4)
        from Utility.Stuff import icona_tabler

        def tasto(icona, suggerimento, azione):
            t = QToolButton()
            t.setCursor(Qt.CursorShape.PointingHandCursor)
            t.setIcon(icona_tabler(icona, colori["testo"], 16))
            t.setToolTip(suggerimento)
            t.clicked.connect(azione)
            t.setStyleSheet(
                f"QToolButton {{ border: 1px solid {colori['bordo']}; border-radius: 4px;"
                f" padding: 4px; background: transparent; }}"
                f" QToolButton:hover {{ border-color: {ROSSO}; }}")
            strumenti.addWidget(t)
            return t

        if voce.get("esterno") or voce.get("aggiunto"):
            tasto("close", "Toglie dall'elenco dell'adunanza (non cancella nessun file)",
                  lambda: pannello.rimuovi_voce(voce))
        if (not voce.get("esterno") and voce["tipo"] in ("video", "audio")
                and voce.get("scaricato")):
            self._altro = tasto("trash", "Elimina il file scaricato dal disco "
                                "(sparisce anche da Scaricati)",
                                lambda: pannello.elimina_voce(voce))
        if strumenti.count():
            riga.addLayout(strumenti)

        if scarico is not None:
            self.mostra_scarico(scarico)

    def mostra_scarico(self, scarico) -> None:
        """("attesa",) · ("corso", scritti, totale) · ("errore",)."""
        tipo = scarico[0]
        if tipo == "errore":
            self._barra.setVisible(False)
            self._etichetta_stato.setText("Scaricamento non riuscito: riprova ⚠")
            self._etichetta_stato.setStyleSheet(
                f"color: {ROSSO}; font-size: 12px; font-weight: 600;")
            if self._scarica is not None:
                self._scarica.setEnabled(True)
                self._scarica.setText("Riprova")
            return
        if self._scarica is not None:
            self._scarica.setEnabled(False)
            self._scarica.setText("In corso…")
        self._barra.setVisible(True)
        if tipo == "attesa":
            self._barra.setRange(0, 0)          # si muove: sta per partire
            self._barra.setFormat("")
            self._etichetta_stato.setText(f"{ETICHETTA[self._voce['tipo']]} · in coda per lo scaricamento…")
            return
        scritti, totale = scarico[1], scarico[2]
        mb = 1024 * 1024
        if totale > 0:
            per_cento = min(100, int(scritti * 100 / totale))
            self._barra.setRange(0, 100)
            self._barra.setValue(per_cento)
            self._barra.setFormat(f"{per_cento}%")
            testo = f"scaricamento {per_cento}% · {scritti / mb:.1f} di {totale / mb:.1f} MB"
        else:
            self._barra.setRange(0, 0)
            self._barra.setFormat("")
            testo = f"scaricamento · {scritti / mb:.1f} MB"
        self._etichetta_stato.setText(f"{ETICHETTA[self._voce['tipo']]} · {testo}")
        self._etichetta_stato.setStyleSheet(
            "color: #a77fd4; font-size: 12px; font-weight: 600;")

    @staticmethod
    def _stato(voce: dict, mostrata: bool) -> QLabel:
        genere = ETICHETTA[voce["tipo"]]
        if voce.get("esterno"):
            if voce.get("mancante"):
                testo, colore = f"{genere} · file esterno non trovato", ROSSO
            else:
                testo, colore = f"{genere} · file esterno", VERDE
        elif voce["tipo"] == "immagine":
            testo, colore = f"{genere} · pronta", VERDE
        elif voce.get("scaricato"):
            testo, colore = f"{genere} · ✔ scaricato sul disco", VERDE
        else:
            testo, colore = f"{genere} · solo streaming (non scaricato)", ARANCIO
        if mostrata:
            testo += " · già mostrato"
        etichetta = QLabel(testo)
        etichetta.setWordWrap(True)
        etichetta.setStyleSheet(f"color: {colore}; font-size: 12px; font-weight: 600;")
        return etichetta

    def mousePressEvent(self, e) -> None:  # noqa: N802
        # Tutta la scheda e' cliccabile solo se e' la parte in corso.
        if (self._attiva and e.button() == Qt.MouseButton.LeftButton
                and not self._voce.get("mancante")):
            self._pannello.apri_voce(self._voce)
            return
        super().mousePressEvent(e)


# ----------------------------------------------------------------------
# IL PANNELLO
# ----------------------------------------------------------------------

class PannelloContenuti(QWidget):
    def __init__(self, finestra) -> None:
        super().__init__()
        from Utility import tema
        self._finestra = finestra
        self._colori = tema.colori(tema.tema_attivo())
        self._meeting = None
        self._pagina = None          # (pub, documento)
        self._chiave = None          # chiave dei file esterni
        self._voci: list[dict] = []
        self._gruppi: list[dict] = []
        self._mostrati: set = set()
        self._attiva = 0             # indice della parte in corso
        self._velo = None
        self._titoli_gruppo: dict = {}
        self._ultimo_indice = -1     # ultima parte per cui e' arrivato il segnale
        # Gli scaricamenti: chiave -> ("attesa",) | ("corso", scritti, totale) | ("errore",)
        self._scarichi: dict = {}
        self._coda: list[dict] = []           # «Scarica tutti»: chi aspetta il suo turno
        self._lotto: dict = {}                # chiave -> (scritti, totale, finito) per la barra generale
        self._righe: dict = {}                # chiave -> _Riga visibile adesso
        self._aggiunti: list[dict] = []       # media dell'app aggiunti a mano
        self._proposte: set = set()           # pubblicazioni di cui si e' gia' chiesto
        self._elimina_dopo = False            # appena arriva la nuova, via le vecchie
        self._dalla_coda: set = set()         # chiavi partite dalla coda e non finite

        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(6, 4, 6, 6)
        colonna.setSpacing(4)
        self._titolo = QLabel("Contenuti dell'adunanza")
        self._titolo.setStyleSheet("font-size: 14px; font-weight: 700;")
        self._titolo.setWordWrap(True)
        colonna.addWidget(self._titolo)
        self._in_corso = QLabel("")
        self._in_corso.setWordWrap(True)
        self._in_corso.setStyleSheet(
            "font-weight: 700; padding: 6px 8px; border-radius: 6px;"
            " background-color: #64398b; color: #ffffff;")
        self._in_corso.setVisible(False)
        colonna.addWidget(self._in_corso)
        self._avvisi = QVBoxLayout()
        self._avvisi.setSpacing(6)
        colonna.addLayout(self._avvisi)
        self._scadute: list = []
        testata = QHBoxLayout()
        self._quanti = QLabel("")
        self._quanti.setStyleSheet(f"color: {self._colori['grigio']};")
        testata.addWidget(self._quanti, 1)
        self._scarica_tutti = QPushButton("Scarica tutti")
        self._scarica_tutti.setToolTip(
            "Scarica sul disco tutti i video e gli audio non ancora scaricati")
        self._scarica_tutti.clicked.connect(self.scarica_tutti)
        testata.addWidget(self._scarica_tutti)
        self._elimina_tutti = QPushButton("Elimina tutti")
        self._elimina_tutti.setToolTip(
            "Cancella dal disco tutti i video e gli audio scaricati di questa lista "
            "(i cantici compresi). Si possono riscaricare. Per toglierne solo alcuni "
            "usa il cestino sulla riga.")
        self._elimina_tutti.clicked.connect(self.elimina_tutti)
        testata.addWidget(self._elimina_tutti)
        colonna.addLayout(testata)

        # La barra generale: si vede finche' c'e' qualcosa che scende, e dice
        # quanti file sono arrivati e quanto manca in tutto.
        self._generale = QWidget()
        g = QVBoxLayout(self._generale)
        g.setContentsMargins(0, 0, 0, 2)
        g.setSpacing(2)
        self._generale_testo = QLabel("")
        self._generale_testo.setStyleSheet("color: #a77fd4; font-weight: 700;")
        g.addWidget(self._generale_testo)
        self._generale_barra = QProgressBar()
        self._generale_barra.setFixedHeight(18)
        self._generale_barra.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {self._colori['bordo']}; border-radius: 5px;"
            f" background: {self._colori['sfondo']}; color: {self._colori['testo']};"
            f" text-align: center; font-weight: 600; }}"
            " QProgressBar::chunk { background-color: #64398b; border-radius: 4px; }")
        g.addWidget(self._generale_barra)
        self._generale.setVisible(False)
        colonna.addWidget(self._generale)
        self._nascondi_generale = QTimer(self)
        self._nascondi_generale.setSingleShot(True)
        self._nascondi_generale.setInterval(4000)
        self._nascondi_generale.timeout.connect(self._fine_lotto)

        from Utility import AvanzamentoMedia
        canale = AvanzamentoMedia.canale()
        canale.iniziato.connect(self._scarico_iniziato)
        canale.avanza.connect(self._scarico_avanza)
        canale.finito.connect(self._scarico_finito)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        colonna.addWidget(self._area, 1)

        # i media scaricati si accorgono da soli: ogni tanto si rilegge il disco
        self._giro = QTimer(self)
        self._giro.setInterval(3000)
        self._giro.timeout.connect(self._rileggi)
        self._giro.start()
        # La parte in corso si controlla anche a intervalli: saltando in fretta
        # da una parte all'altra i segnali possono perdersi.
        self._sincro = QTimer(self)
        self._sincro.setInterval(400)
        self._sincro.timeout.connect(self._sincronizza_parte)
        self._sincro.start()

        finestra.timer_controller.part_changed.connect(self._parte_cambiata)
        finestra.timer_controller.meeting_ended.connect(self._adunanza_finita)
        finestra.timer_controller.timer.state_changed.connect(self._stato_timer)

    # --- parte in corso ---------------------------------------------------
    def _parte_cambiata(self, parte, indice) -> None:
        indice = int(indice)
        # Il cantico parte da solo solo se il timer e' in corso e si e' passati
        # a una parte NUOVA.  Modificare una parte (per esempio il numero del
        # cantico) non deve far partire niente.
        in_corso = getattr(self._finestra.timer_controller, "current_part_index", -1) >= 0
        nuova = in_corso and indice != self._ultimo_indice
        if in_corso:
            self._ultimo_indice = indice
        self._attiva = max(0, indice)
        self._ricostruisci(vai_alla_parte=True)
        if nuova and in_corso and self._avvio_automatico():
            self._avvia_primo_della_parte()

    def _sincronizza_parte(self) -> None:
        corrente = getattr(self._finestra.timer_controller, "current_part_index", -1)
        if corrente >= 0 and corrente != self._attiva and self._gruppi:
            self._attiva = corrente
            self._ricostruisci(vai_alla_parte=True)
        elif corrente < 0 and self._attiva != 0 and self._gruppi:
            self._riparti_da_capo()          # fermato senza che sia arrivato il segnale

    def _aggiorna_in_corso(self) -> None:
        """La riga «Parte in corso»: c'e' sempre, anche se quella parte non ha contenuti."""
        parti = [p for s in (self._meeting.sections if self._meeting else []) for p in s.parts]
        if not parti or not 0 <= self._attiva < len(parti):
            self._in_corso.setText("")
            self._in_corso.setVisible(False)
            return
        ha = any(g["indice"] == self._attiva for g in self._gruppi)
        iniziata = getattr(self._finestra.timer_controller, "current_part_index", -1) >= 0
        testo = ("Parte in corso: " if iniziata else "Si comincia da: ") + parti[self._attiva].title
        if not ha:
            testo += "  ·  nessun contenuto per questa parte"
        self._in_corso.setText(testo)
        self._in_corso.setVisible(True)

    def _adunanza_finita(self) -> None:
        self._riparti_da_capo()

    def _stato_timer(self, stato) -> None:
        from src.models.timer import TimerState
        if stato == TimerState.STOPPED:
            self._riparti_da_capo()

    def _riparti_da_capo(self) -> None:
        """Timer fermo: l'evidenziazione torna alla prima parte, pronta a ripartire."""
        self._ultimo_indice = -1
        if self._attiva != 0 and self._gruppi:
            self._attiva = 0
            self._ricostruisci(vai_alla_parte=True)
        else:
            self._aggiorna_in_corso()

    @staticmethod
    def _avvio_automatico() -> bool:
        import opzioni
        return opzioni.avvio_automatico()

    def _avvia_primo_della_parte(self) -> None:
        for g in self._gruppi:
            if g["indice"] != self._attiva:
                continue
            for v in g["voci"]:
                # solo i cantici partono da soli (sigla «sjjm» = Cantiamo a Geova)
                if (v["tipo"] in ("video", "audio") and v.get("sigla") == "sjjm"
                        and chiave_voce(v) not in self._mostrati):
                    self.apri_voce(v)
                    return

    # --- adunanza scelta ------------------------------------------------
    def imposta_adunanza(self, meeting, mantieni: bool = False) -> None:
        """`mantieni`: si e' solo cambiata una parte, quello gia' mostrato resta tale."""
        self._meeting = meeting
        self._pagina = trova_pagina(meeting) if meeting is not None else None
        self._chiave = None
        self._aggiunti = []
        mostrati = set(self._mostrati) if mantieni else set()
        self._voci, self._gruppi, self._mostrati = [], [], mostrati
        self._attiva = max(0, getattr(self._finestra.timer_controller,
                                      "current_part_index", 0))
        if meeting is None:
            self._messaggio("Nessuna adunanza scelta.")
            return
        self._titolo.setText(f"Contenuti — {meeting.title}")
        try:
            self._scadute = pubblicazioni_scadute()
        except Exception:  # noqa: BLE001 - l'avviso delle scadute non deve fermare il pannello
            self._scadute = []
        self._mostra_avvisi()
        if self._pagina is None:
            self._messaggio(
                "La pagina di questa settimana non e' scaricata, quindi non ci sono "
                "immagini e video da mostrare.")
            if not mantieni:
                self._finestra.esegui_quando_visibile(self._proponi_la_nuova, 400)
            return
        from Utility import FileEsterni
        from src.models.meeting import MeetingType
        pub, documento = self._pagina
        self._chiave = FileEsterni.chiave(pub, documento)
        self._carica_aggiunti()
        parti = [p for s in meeting.sections for p in s.parts]
        # I cantici seguono le parti della scaletta, non la pagina: se cambi a
        # mano il numero del cantico, cambia anche il video che compare qui.
        self._voci = [v for v in voci_della_pagina(pub, documento)
                      if v.get("sigla") != "sjjm"]
        self._voci += cantici_delle_parti(parti, pub)
        try:
            co = bool(self._finestra.settings_controller.is_co_visit_active())
        except Exception:  # noqa: BLE001
            co = False
        self._gruppi = assegna_alle_parti(
            self._voci, pub, documento, parti, co,
            meeting.meeting_type == MeetingType.WEEKEND)
        self._ricostruisci()

    def _riquadro(self, testo: str, tasto: str, azione, tooltip: str = "") -> None:
        riquadro = QFrame()
        riquadro.setObjectName("avvisoContenuti")
        riquadro.setStyleSheet(
            f"#avvisoContenuti {{ background-color: {self._colori['lavato']};"
            f" border: 1px solid #a77fd4; border-radius: 8px; }}"
            f" QLabel {{ background: transparent; }}")
        riga = QHBoxLayout(riquadro)
        riga.setContentsMargins(10, 8, 10, 8)
        etichetta = QLabel(testo)
        etichetta.setWordWrap(True)
        riga.addWidget(etichetta, 1)
        pulsante = QPushButton(tasto)
        if tooltip:
            pulsante.setToolTip(tooltip)
        pulsante.clicked.connect(lambda: azione(pulsante))
        riga.addWidget(pulsante)
        self._avvisi.addWidget(riquadro)

    def _mostra_avvisi(self) -> None:
        while self._avvisi.count():
            elemento = self._avvisi.takeAt(0)
            if elemento.widget() is not None:
                elemento.widget().deleteLater()
        if self._meeting is None:
            return
        if self._pagina is None:
            try:
                pub = pubblicazione_da_scaricare(self._meeting)
            except Exception:  # noqa: BLE001
                pub = None
            if pub is not None:
                nome = pub.issueTitle or pub.title
                self._riquadro(
                    f"Per vedere i contenuti di questa adunanza serve scaricare "
                    f"«{nome}».", "Scarica", lambda b: self._scarica_pubblicazione(pub, b))
            else:
                self._riquadro(
                    "Per vedere i contenuti serve la pubblicazione della settimana, ma non "
                    "la trovo nel catalogo. Aggiorna il catalogo dalle Impostazioni.",
                    "Ok", lambda b: None)
        if self._scadute:
            quante = len(self._scadute)
            self._riquadro(
                f"{quante} pubblicazion{'e scaduta' if quante == 1 else 'i scadute'} "
                f"(settimane già passate).", "Elimina scadute…", lambda b: self.elimina_scadute(),
                "Elimina Guide e studi delle settimane passate. I cantici e gli altri "
                "video non si toccano.")

    def _scarica_pubblicazione(self, pub, pulsante=None) -> None:
        if pulsante is not None:
            pulsante.setEnabled(False)
            pulsante.setText("Scaricamento…")
        self._finestra.pubblicazioneRichiesta.emit(richiesta_download(pub))

    def _proponi_la_nuova(self) -> None:
        """«Vuoi scaricare la nuova?»: quando serve una pubblicazione che non c'e'.

        Finito il mese (o il numero della Torre di Guardia) la pagina della
        settimana e' in un'altra pubblicazione, e senza non ci sono video,
        immagini e cantici da mostrare.  Si chiede una volta per pubblicazione,
        con la scelta di cancellare le vecchie appena e' scaricata.
        """
        meeting = self._meeting
        if meeting is None or self._pagina is not None:
            return
        # Arriva da `esegui_quando_visibile`: parte solo quando nessun altro
        # pop-up e' aperto (due uno sopra l'altro bloccavano l'app).
        try:
            pub = pubblicazione_da_scaricare(meeting)
        except Exception:  # noqa: BLE001
            pub = None
        if pub is None:
            return
        nome = pub.issueTitle or pub.title
        if nome in self._proposte:
            return
        self._proposte.add(nome)
        scatola = QMessageBox(self._finestra)
        scatola.setWindowTitle("Nuova pubblicazione")
        scatola.setIcon(QMessageBox.Icon.Question)
        scatola.setText(f"Per questa adunanza serve «{nome}», che non è ancora scaricata.")
        scatola.setInformativeText(
            "Senza non si vedono i video, le immagini e i cantici della settimana.\n\n"
            "Vuoi scaricarla adesso?")
        vecchie = QCheckBox("Dopo il download elimina le pubblicazioni vecchie (scadute)")
        vecchie.setChecked(opzioni.elimina_vecchie_dopo_download())
        scatola.setCheckBox(vecchie)
        si = scatola.addButton("Sì, scarica", QMessageBox.ButtonRole.YesRole)
        scatola.addButton("No", QMessageBox.ButtonRole.NoRole)
        scatola.setDefaultButton(si)
        scatola.exec()
        opzioni.imposta_elimina_vecchie_dopo_download(vecchie.isChecked())
        if scatola.clickedButton() is not si:
            return
        self._elimina_dopo = vecchie.isChecked()
        self._scarica_pubblicazione(pub)

    def elimina_scadute(self, conferma: bool = True) -> None:
        import shutil

        from Utility.JWPubManager import pub_dir
        if not self._scadute:
            return
        elenco = "\n".join(f"• {p.issueTitle or p.title}" for p in self._scadute)
        if conferma:
            risposta = QMessageBox.question(
                self._finestra, "Eliminare le pubblicazioni scadute?",
                f"Verranno eliminate dal computer:\n\n{elenco}\n\n"
                "Sono le settimane già passate. I cantici e gli altri video non si toccano. "
                "Potrai riscaricarle quando vuoi.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if risposta != QMessageBox.StandardButton.Yes:
                return
        for pub in self._scadute:
            try:
                shutil.rmtree(pub_dir(pub), ignore_errors=True)
            except OSError:
                pass
        self.imposta_adunanza(self._meeting, mantieni=True)

    def _messaggio(self, testo: str) -> None:
        etichetta = QLabel(testo)
        etichetta.setWordWrap(True)
        etichetta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        etichetta.setStyleSheet(f"color: {self._colori['grigio']}; padding: 24px;")
        self._area.setWidget(etichetta)
        self._quanti.setText("")
        self._scarica_tutti.setVisible(False)
        self._elimina_tutti.setVisible(False)

    def _esterni(self) -> list[dict]:
        if not self._chiave:
            return []
        from Utility import FileEsterni
        return [FileEsterni.voce(p) for p in FileEsterni.leggi(self._chiave)]

    def _voci_visibili(self) -> list[dict]:
        return [v for g in self._gruppi for v in g["voci"]] + self._aggiunti

    def _carica_aggiunti(self) -> None:
        """I media dell'app aggiunti a mano a questa pagina, con lo stato del disco."""
        from Utility import FileEsterni
        self._aggiunti = []
        if not self._chiave:
            return
        for scheda in FileEsterni.leggi_media(self._chiave):
            v = dict(scheda, aggiunto=True)
            if v.get("tipo") in ("video", "audio") and _prepara(v, v.get("lingua") or "I"):
                self._aggiunti.append(v)

    def _ricostruisci(self, vai_alla_parte: bool = False) -> None:
        self._aggiorna_in_corso()
        barra = self._area.verticalScrollBar()
        posizione = barra.value()
        interno = QWidget()
        elenco = QVBoxLayout(interno)
        elenco.setContentsMargins(0, 0, 4, 8)
        elenco.setSpacing(6)
        self._titoli_gruppo = {}
        self._righe = {}
        esterni = self._esterni()
        gruppi = list(self._gruppi)
        if esterni or self._aggiunti:
            gruppi.append({"indice": None, "titolo": "Aggiunti a mano",
                           "voci": self._aggiunti + esterni, "esterni": True})
        for g in gruppi:
            e_corrente = g["indice"] == self._attiva and g["indice"] is not None
            intestazione = QLabel(g["titolo"])
            intestazione.setWordWrap(True)
            if e_corrente:
                intestazione.setStyleSheet(
                    "font-weight: 700; padding: 8px 6px; border-radius: 6px;"
                    " background-color: #64398b; color: #ffffff;")
            else:
                intestazione.setStyleSheet(
                    f"font-weight: 600; padding: 8px 6px 2px 6px;"
                    f" color: {self._colori['grigio']};")
            elenco.addWidget(intestazione)
            if g["indice"] is not None:
                self._titoli_gruppo[g["indice"]] = intestazione
            gruppo_citato = None
            for voce in g["voci"]:
                if voce.get("gruppo") and voce.get("gruppo") != gruppo_citato:
                    gruppo_citato = voce["gruppo"]
                    etichetta = QLabel(f"Dal documento citato: {gruppo_citato}")
                    etichetta.setWordWrap(True)
                    etichetta.setStyleSheet(
                        f"font-size: 12px; color: {self._colori['grigio']}; padding: 2px 4px;")
                    elenco.addWidget(etichetta)
                attiva = bool(g.get("esterni")) or e_corrente
                mostrata = chiave_voce(voce) in self._mostrati
                k = self._chiave_scarico(voce)
                # Gia' mostrato: tornano scuri e la scheda NON risponde piu' al
                # clic; si rilancia solo col tasto Mostra / Riproduci.
                riga = _Riga(voce, self._colori, self, attiva and not mostrata, mostrata,
                             attiva and not mostrata,
                             None if voce.get("scaricato") else self._scarichi.get(k))
                if k is not None:
                    self._righe[k] = riga
                elenco.addWidget(riga)
        elenco.addStretch(1)
        self._area.setWidget(interno)
        QTimer.singleShot(0, lambda: barra.setValue(posizione))
        if vai_alla_parte and self._attiva in self._titoli_gruppo:
            # Due giri: il primo appena il layout e' pronto, il secondo per
            # quando la barra di scorrimento ha preso la sua altezza finale.
            QTimer.singleShot(30, self._porta_la_parte_in_cima)
            QTimer.singleShot(150, self._porta_la_parte_in_cima)
        visibili = self._voci_visibili()
        media = [v for v in visibili if v["tipo"] in ("video", "audio")]
        da_scaricare = [v for v in media if not v.get("scaricato")]
        self._quanti.setText(
            f"{len(visibili) + len(esterni)} elementi · "
            f"{len(media) - len(da_scaricare)}/{len(media)} video e audio scaricati")
        self._scarica_tutti.setVisible(bool(da_scaricare))
        # Un tasto solo, nello stesso posto: «Scarica tutti» finche' manca qualcosa,
        # «Elimina tutti» quando e' tutto scaricato.
        self._elimina_tutti.setVisible(
            not da_scaricare and any(v.get("scaricato") and not v.get("esterno")
                                     for v in media))
        in_corso = [v for v in da_scaricare
                    if self._scarichi.get(self._chiave_scarico(v), ("",))[0] in ("attesa", "corso")]
        self._scarica_tutti.setEnabled(len(in_corso) < len(da_scaricare))

    def _porta_la_parte_in_cima(self) -> None:
        """Scorre l'elenco finche' il titolo della parte in corso e' in cima.

        Cosi' i contenuti di quella parte, che stanno SOTTO il titolo, si
        vedono tutti (o quanti ne stanno nel pannello).  Prima si portava in
        vista solo il titolo: se era in fondo, i video da mostrare restavano
        fuori dallo schermo.
        """
        titolo = self._titoli_gruppo.get(self._attiva)
        interno = self._area.widget()
        if titolo is None or interno is None:
            return
        try:
            if interno.layout() is not None:
                interno.layout().activate()
            y = titolo.mapTo(interno, titolo.rect().topLeft()).y()
            self._area.verticalScrollBar().setValue(max(0, y - 4))
        except RuntimeError:        # elenco rifatto nel frattempo
            pass

    def _rileggi(self) -> None:
        if not self.isVisible():
            return
        if self._pagina is None and self._meeting is not None:
            # la pubblicazione potrebbe essere appena stata scaricata
            if trova_pagina(self._meeting) is not None:
                self.imposta_adunanza(self._meeting, mantieni=True)
                if self._elimina_dopo:
                    # Scaricata la nuova (l'utente l'aveva chiesto): via le vecchie.
                    self._elimina_dopo = False
                    self.elimina_scadute(conferma=False)
            return
        if (self._voci or self._aggiunti) and aggiorna_stato(self._voci + self._aggiunti):
            self._ricostruisci()

    # --- azioni ---------------------------------------------------------
    def aggiungi_file(self) -> None:
        """Apre la finestra «Aggiungi contenuti» (nuovi, preferiti, cerca, dal computer)."""
        if not self._chiave:
            QMessageBox.information(
                self._finestra, "Aggiungi contenuti",
                "Scegli prima un'adunanza di cui è scaricata la pagina della settimana.")
            return
        from aggiungi_dialogo import DialogoAggiungi
        DialogoAggiungi(self, self._finestra).exec()

    # --- i media dell'app aggiunti a mano ---------------------------------
    def _trova_aggiunto(self, voce: dict):
        for v in self._aggiunti:
            if (v["sigla"], int(v["traccia"]), int(v.get("numero") or 0), v["tipo"]) == (
                    voce["sigla"], int(voce["traccia"]), int(voce.get("numero") or 0),
                    voce["tipo"]):
                return v
        return None

    def e_aggiunto(self, voce: dict) -> bool:
        return self._trova_aggiunto(voce) is not None

    def e_scaricato(self, voce: dict) -> bool:
        from Utility import MediaScaricati
        formato = "VIDEO" if voce["tipo"] == "video" else "AUDIO"
        return MediaScaricati.file_di(voce["sigla"], voce.get("lingua") or "I",
                                      _tracce(voce), formato) is not None

    def aggiungi_media(self, voce: dict) -> None:
        if not self._chiave or self.e_aggiunto(voce):
            return
        from Utility import FileEsterni
        FileEsterni.aggiungi_media(self._chiave, voce)
        self._carica_aggiunti()
        self._ricostruisci()

    def scarica_media_aggiunto(self, voce: dict, genitore=None, dopo=None) -> None:
        """Dal pop up: sceglie la risoluzione, e solo se scegli aggiunge e scarica."""
        def scelto(altezza: int) -> None:
            self.aggiungi_media(voce)
            v = self._trova_aggiunto(voce)
            if v is not None and not v.get("scaricato"):
                self._scarica_con(v, altezza)
            if dopo:
                dopo()

        if voce["tipo"] == "video" and not self.e_scaricato(voce):
            self._chiedi_risoluzione(voce, scelto, genitore or self)
        else:
            scelto(0)

    def pubblicazione_scaricata(self, pub) -> bool:
        from Utility.JWPubManager import pub_db_path
        try:
            return pub_db_path(pub).is_file()
        except Exception:  # noqa: BLE001
            return False

    def scarica_pubblicazione(self, pub) -> None:
        """Scarica il pacchetto di una pubblicazione, senza aprirla."""
        self._finestra.pubblicazioneRichiesta.emit(richiesta_download(pub))

    def scegli_file_esterni(self) -> None:
        """La finestra di sistema per un file che non fa parte dell'app."""
        if not self._chiave:
            return
        from Utility import FileEsterni
        formati = sorted(FileEsterni.IMMAGINI | FileEsterni.VIDEO | FileEsterni.AUDIO
                         | FileEsterni.PDF | FileEsterni.OFFICE)
        filtro = ("File supportati (" + " ".join(f"*{e}" for e in formati)
                  + ");;Tutti i file (*)")
        scelti, _ = QFileDialog.getOpenFileNames(self._finestra, "Aggiungi file", "", filtro)
        if not scelti:
            return
        scartati = FileEsterni.aggiungi(self._chiave, scelti)
        self._ricostruisci()
        if scartati:
            QMessageBox.information(self._finestra, "Formato non supportato",
                                    "Questi file non sono stati aggiunti:\n" + "\n".join(scartati))

    def rimuovi_voce(self, voce: dict) -> None:
        from Utility import FileEsterni
        if voce.get("aggiunto"):
            FileEsterni.togli_media(self._chiave, voce)
            self._carica_aggiunti()
        else:
            FileEsterni.togli(self._chiave, voce["percorso"])
        self._ricostruisci()

    @staticmethod
    def _cancella_file(voce: dict) -> None:
        """Cancella dal disco il file di un media, in tutte le risoluzioni."""
        from Utility import MediaScaricati
        if voce.get("file"):
            Path(voce["file"]).unlink(missing_ok=True)
        # Se ce n'e' piu' di una risoluzione, vanno via tutte: altrimenti il
        # video risulterebbe ancora scaricato.
        for _ in range(8):
            altro = MediaScaricati.file_di(voce["sigla"], voce.get("lingua") or "I",
                                           _tracce(voce), voce["formato"])
            if altro is None:
                break
            altro.unlink(missing_ok=True)

    def elimina_voce(self, voce: dict) -> None:
        """Toglie dal disco un video o audio scaricato, dopo conferma."""
        risposta = QMessageBox.question(
            self._finestra, "Eliminare dal disco?",
            f"Eliminare dal computer il file scaricato?\n\n{voce.get('titolo') or ''}\n\n"
            "Si potrà riscaricare o guardare in streaming.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if risposta != QMessageBox.StandardButton.Yes or not voce.get("file"):
            return
        try:
            self._cancella_file(voce)
        except OSError as errore:
            QMessageBox.warning(self._finestra, "Non riesco a eliminarlo", str(errore))
            return
        aggiorna_stato(self._voci + self._aggiunti)
        self._ricostruisci()

    def elimina_tutti(self) -> None:
        """Cancella dal disco tutti i video e audio scaricati della lista, con una conferma."""
        da_togliere = [v for v in self._voci_visibili()
                       if v["tipo"] in ("video", "audio") and v.get("scaricato")
                       and not v.get("esterno")]
        if not da_togliere:
            return
        risposta = QMessageBox.question(
            self._finestra, "Eliminare tutti i file scaricati?",
            f"Verranno cancellati dal computer {len(da_togliere)} file scaricati "
            "(video e audio di questa lista, cantici compresi).\n\n"
            "Si possono riscaricare o guardare in streaming. I file aggiunti dal "
            "computer non si toccano.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if risposta != QMessageBox.StandardButton.Yes:
            return
        non_riusciti = 0
        for v in da_togliere:
            try:
                self._cancella_file(v)
            except OSError:
                non_riusciti += 1
        aggiorna_stato(self._voci + self._aggiunti)
        self._ricostruisci()
        if non_riusciti:
            QMessageBox.warning(self._finestra, "Eliminazione",
                                f"{non_riusciti} file non si sono potuti cancellare.")

    def apri_voce(self, voce: dict) -> None:
        self._mostrati.add(chiave_voce(voce))
        QTimer.singleShot(0, self._ricostruisci)
        if voce.get("esterno") and voce["tipo"] in ("immagine", "documento"):
            self._velo_().apri(voce["file"], voce.get("titolo") or "")
            return
        if voce["tipo"] == "immagine":
            pixmap = QPixmap()
            if voce.get("dati") and pixmap.loadFromData(voce["dati"]):
                self._velo_().mostra(pixmap)
            return
        self._finestra.mediaRichiesto.emit(voce)

    # --- scaricamenti ---------------------------------------------------
    #: Quanti file scendono insieme con «Scarica tutti»: due bastano, dieci
    #: insieme si rubano la banda e nessuno finisce.
    INSIEME = 2

    @staticmethod
    def _chiave_scarico(voce: dict):
        if voce.get("esterno") or voce.get("tipo") not in ("video", "audio"):
            return None
        from Utility import AvanzamentoMedia
        return AvanzamentoMedia.chiave_di(voce)

    def _metti_stato(self, k, stato) -> None:
        if stato is None:
            self._scarichi.pop(k, None)
        else:
            self._scarichi[k] = stato
        riga = self._righe.get(k)
        if riga is not None and stato is not None:
            try:
                riga.mostra_scarico(stato)
            except RuntimeError:            # riga gia' distrutta da un rifacimento
                self._righe.pop(k, None)

    def _entra_nel_lotto(self, k) -> None:
        self._nascondi_generale.stop()
        if k not in self._lotto or self._lotto[k][2]:
            self._lotto[k] = (0, 0, False)
        self._aggiorna_generale()

    def scarica_voce(self, voce: dict, genitore=None, dopo=None) -> None:
        """Scarica un media.  Un video chiede la risoluzione con un menu del timer.

        Il menu lo apre il timer e non la finestra principale: quella sta dietro
        il timer e un menu che nasce li' non si vede.  Scelta la risoluzione, la
        richiesta parte con `altezza` e `automatico`, cosi' la finestra
        principale non ne apre un secondo.
        """
        k = self._chiave_scarico(voce)
        if k is not None and self._scarichi.get(k, ("",))[0] in ("attesa", "corso"):
            return
        if voce.get("tipo") == "video" and not voce.get("automatico"):
            self._chiedi_risoluzione(
                voce, lambda h: (self._scarica_con(voce, h), dopo() if dopo else None),
                genitore or self)
            return
        self._scarica_con(voce, 0)
        if dopo:
            dopo()

    def _scarica_con(self, voce: dict, altezza: int) -> None:
        k = self._chiave_scarico(voce)
        if k is not None:
            self._metti_stato(k, ("attesa",))
            self._entra_nel_lotto(k)
        if voce.get("tipo") == "video":
            voce = dict(voce, automatico=True, altezza=altezza)
        self._finestra.scaricaRichiesta.emit(voce)

    def scarica_tutti(self) -> None:
        """Chiede UNA risoluzione, poi scarica tutto con quella."""
        da = []
        for v in self._voci_visibili():
            if v["tipo"] not in ("video", "audio") or v.get("scaricato"):
                continue
            k = self._chiave_scarico(v)
            if k is None or self._scarichi.get(k, ("",))[0] in ("attesa", "corso"):
                continue
            da.append(v)
        if not da:
            return
        video = [v for v in da if v["tipo"] == "video"]
        if not video:
            self._avvia_lotto(da, 0)               # solo audio: niente da scegliere
            return
        self._chiedi_risoluzione(video[0], lambda altezza: self._avvia_lotto(da, altezza))

    def _avvia_lotto(self, voci: list, altezza: int) -> None:
        for v in voci:
            k = self._chiave_scarico(v)
            if k is None or self._scarichi.get(k, ("",))[0] in ("attesa", "corso"):
                continue
            self._metti_stato(k, ("attesa",))
            self._entra_nel_lotto(k)
            self._coda.append(dict(v, automatico=True, altezza=altezza))
        self._ricostruisci()
        self._avanza_coda()

    def _chiedi_risoluzione(self, esempio: dict, avanti, genitore=None, punto=None) -> None:
        """Menu con le risoluzioni che il server ha per questo video.

        Si sceglie una volta e vale per tutti i video: se un video non ha
        quella risoluzione prende la migliore sotto.  «La più alta» = 0.
        """
        import opzioni
        from Utility.Extensions.Ext_DispatchQueue import background
        altezze: list[int] = []

        def lavoro() -> None:
            from Utility import MepsAPI
            try:
                numero = int(esempio.get("numero") or 0)
                voci = (MepsAPI.media(esempio["sigla"], esempio["lingua"], str(numero))
                        if numero else
                        MepsAPI.media(esempio["sigla"], esempio["lingua"],
                                      traccia=int(esempio["traccia"])))
            except Exception:  # noqa: BLE001 - senza rete: si scarica alla piu' alta
                voci = []
            for voce in voci:
                if (MepsAPI.traccia_numero(voce) == int(esempio["traccia"])
                        and str(voce.get("mimetype") or "").startswith("video/")
                        and voce.get("frameHeight")):
                    altezze.append(int(voce["frameHeight"]))
            altezze[:] = sorted(set(altezze), reverse=True)

        def arrivati() -> None:
            if not altezze:
                avanti(0)
                return
            ultima = opzioni.risoluzione_scaricamento()
            menu = QMenu(genitore or self)
            menu.setToolTipsVisible(True)
            menu.addSection("Risoluzione per tutti i video" if punto is None and genitore is None
                            else "Scegli la risoluzione")
            for h in altezze:
                testo = f"{h}p" + ("   ✓ ultima scelta" if h == ultima else "")
                menu.addAction(testo).triggered.connect(
                    lambda _c=False, h=h: (opzioni.imposta_risoluzione_scaricamento(h), avanti(h)))
            menu.addSeparator()
            menu.addAction("La più alta disponibile").triggered.connect(
                lambda _c=False: (opzioni.imposta_risoluzione_scaricamento(0), avanti(0)))
            self._menu_risoluzione = menu
            from PyQt6.QtGui import QCursor
            if genitore is not None:
                dove = QCursor.pos()
            else:
                dove = self._scarica_tutti.mapToGlobal(self._scarica_tutti.rect().bottomLeft())
            menu.exec(dove)

        background(lavoro, completion=arrivati)

    def _avanza_coda(self) -> None:
        while self._coda and len(self._dalla_coda) < self.INSIEME:
            v = self._coda.pop(0)
            self._dalla_coda.add(self._chiave_scarico(v))
            self._finestra.scaricaRichiesta.emit(v)

    def _scarico_iniziato(self, k, totale: int) -> None:
        # Arriva anche per scaricamenti partiti da fuori (la pagina dei
        # contenuti): se il media e' in questo pannello, si vede lo stesso.
        self._nascondi_generale.stop()
        self._metti_stato(k, ("corso", 0, int(totale)))
        self._lotto[k] = (0, int(totale), False)
        self._aggiorna_generale()

    def _scarico_avanza(self, k, scritti: int, totale: int) -> None:
        self._metti_stato(k, ("corso", int(scritti), int(totale)))
        if k in self._lotto:
            self._lotto[k] = (int(scritti), int(totale), False)
            self._aggiorna_generale()

    def _scarico_finito(self, k, esito: str) -> None:
        self._dalla_coda.discard(k)
        # "annullato" = menu' delle risoluzioni chiuso senza scegliere
        self._metti_stato(k, ("errore",) if esito == "errore" else None)
        if k in self._lotto:
            scritti, totale, _ = self._lotto[k]
            if esito == "annullato":
                del self._lotto[k]
            else:
                self._lotto[k] = (totale or scritti, totale or scritti, True)
        self._aggiorna_generale()
        self._avanza_coda()
        aggiorna_stato(self._voci + self._aggiunti)
        self._ricostruisci()

    def _aggiorna_generale(self) -> None:
        if not self._lotto:
            self._generale.setVisible(False)
            return
        quanti = len(self._lotto)
        finiti = sum(1 for (_, _, f) in self._lotto.values() if f)
        errori = sum(1 for k, (_, _, f) in self._lotto.items()
                     if f and self._scarichi.get(k, ("",))[0] == "errore")
        noti = [(s, t) for (s, t, _) in self._lotto.values() if t > 0]
        if noti and len(noti) == quanti:
            per_cento = int(sum(s for s, _ in noti) * 100 / max(1, sum(t for _, t in noti)))
        else:
            # i pesi non si sanno tutti: conta i file e la parte del file in corso
            parziale = sum((s / t if t else 0) if not f else 1
                           for (s, t, f) in self._lotto.values())
            per_cento = int(parziale * 100 / quanti)
        per_cento = max(0, min(100, per_cento))
        self._generale_barra.setRange(0, 100)
        self._generale_barra.setValue(per_cento)
        self._generale_barra.setFormat(f"{per_cento}%")
        if finiti < quanti:
            testo = f"⬇ Scaricamento in corso: {finiti} di {quanti} file · {per_cento}%"
        elif errori:
            testo = f"Finito: {quanti - errori} scaricati, {errori} non riusciti ⚠"
        else:
            testo = f"✔ Scaricati tutti ({quanti} file)"
        self._generale_testo.setText(testo)
        self._generale.setVisible(True)
        if finiti == quanti:
            self._nascondi_generale.start()

    def _fine_lotto(self) -> None:
        if all(f for (_, _, f) in self._lotto.values()):
            self._lotto = {}
            self._generale.setVisible(False)

    def _velo_(self):
        if self._velo is None:
            from SubViews.VeloImmagine import VeloImmagine
            self._velo = VeloImmagine(self._finestra)
        return self._velo


# ----------------------------------------------------------------------
# DENTRO LA FINESTRA DEL TIMER
# ----------------------------------------------------------------------

def installa(finestra) -> PannelloContenuti:
    """Pannello nascondibile a destra, tasti in barra e voce nel menu Visualizza."""
    from PyQt6.QtWidgets import QToolBar

    class Dock(QDockWidget):
        def closeEvent(self, evento):  # noqa: N802
            # La X del pannello: e' una scelta dell'utente, si ricorda.
            if finestra.isVisible():
                opzioni.imposta_pannello_aperto(False)
            super().closeEvent(evento)

    pannello = PannelloContenuti(finestra)
    dock = Dock("Contenuti", finestra)
    dock.setObjectName("dockContenuti")
    dock.setWidget(pannello)
    # Niente barra del titolo sopra il pannello: ripeterebbe il titolo che c'e'
    # gia' dentro e mangia spazio.  Si apre e si chiude dal tasto «Contenuti».
    dock.setTitleBarWidget(QWidget())
    dock.setMinimumWidth(250)      # a mezzo schermo deve starci (accanto a Zoom)
    # Quando la finestra si stringe e' il pannello a cedere, non l'orologio e
    # la scaletta: sotto questa larghezza non si leggerebbero piu'.
    if finestra.centralWidget() is not None:
        finestra.centralWidget().setMinimumWidth(320)
    dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                     | QDockWidget.DockWidgetFeature.DockWidgetMovable)
    finestra.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    finestra.dock_contenuti = dock
    dock.setVisible(opzioni.pannello_aperto())

    # Quando il timer torna visibile (si e' stati in un'altra sezione) il
    # pannello si rimette come l'utente l'ha lasciato.
    class Riapplica(QObject):
        def eventFilter(self, oggetto, evento):  # noqa: N802
            if evento.type() == QEvent.Type.Show:
                QTimer.singleShot(0, lambda: dock.setVisible(opzioni.pannello_aperto()))
            return False

    riapplica = Riapplica(finestra)
    finestra.installEventFilter(riapplica)

    barra = finestra.findChild(QToolBar)
    if barra is not None:
        prima = next((a for a in barra.actions()
                      if barra.widgetForAction(a) is getattr(finestra, "prev_button", None)), None)
        aggiungi = QPushButton("Aggiungi file")
        aggiungi.setToolTip("Immagini, video, audio, PDF, Word, Excel, LibreOffice: "
                            "si aggiungono a questa adunanza e si ricordano")
        aggiungi.clicked.connect(pannello.aggiungi_file)
        mostra = QPushButton("Contenuti")
        mostra.setCheckable(True)
        mostra.setChecked(opzioni.pannello_aperto())
        mostra.setToolTip("Mostra o nasconde il pannello dei contenuti "
                          "(resta come lo lasci)")
        mostra.clicked.connect(lambda v: (opzioni.imposta_pannello_aperto(v),
                                          dock.setVisible(v)))
        dock.visibilityChanged.connect(
            lambda v: mostra.setChecked(opzioni.pannello_aperto()))
        if prima is not None:
            barra.insertWidget(prima, aggiungi)
            barra.insertWidget(prima, mostra)
            barra.insertSeparator(prima)
        else:
            barra.addWidget(aggiungi)
            barra.addWidget(mostra)

    for azione in finestra.menuBar().actions():
        if azione.menu() is not None and azione.text().replace("&", "") in ("Visualizza", "View"):
            azione.menu().addAction(dock.toggleViewAction())
            dock.toggleViewAction().triggered.connect(
                lambda v: opzioni.imposta_pannello_aperto(bool(v)))
    return pannello
