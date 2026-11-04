"""Le opzioni del timer che non sono nelle impostazioni originali.

Si ricordano in `opzioni.json`, nella cartella dei dati del timer.
"""
import json
import os
from pathlib import Path


def _file() -> Path:
    return Path(os.environ.get("ONTIME_DATA_DIR", ".")) / "opzioni.json"


def _leggi() -> dict:
    try:
        dati = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _scrivi(chiave: str, valore) -> None:
    dati = _leggi()
    dati[chiave] = valore
    try:
        _file().write_text(json.dumps(dati, indent=2), encoding="utf-8")
    except OSError:
        pass


def avvio_automatico() -> bool:
    """All'inizio di una parte parte da solo il suo primo video o audio."""
    return bool(_leggi().get("avvio_automatico", False))


def imposta_avvio_automatico(valore: bool) -> None:
    _scrivi("avvio_automatico", bool(valore))


CAMPI_VISITA = ("servizio", "pubblico", "finale")


def titoli_visita(settimana: str | None) -> dict:
    """I titoli scritti a mano per la visita, validi solo per quella settimana.

    `settimana` e' il lunedi' (ISO) in cui la visita e' stata accesa.  Finita la
    settimana i titoli non valgono piu': non si rischia di rivederli la volta dopo.
    """
    dati = _leggi().get("visita") or {}
    if not settimana or dati.get("settimana") != settimana:
        return {c: "" for c in CAMPI_VISITA}
    titoli = dati.get("titoli") or {}
    return {c: str(titoli.get(c, "") or "").strip() for c in CAMPI_VISITA}


def imposta_titoli_visita(settimana: str | None, titoli: dict) -> None:
    _scrivi("visita", {"settimana": settimana,
                       "titoli": {c: str(titoli.get(c, "") or "").strip()
                                  for c in CAMPI_VISITA}})


def pannello_aperto() -> bool:
    """Il pannello Contenuti: aperto o chiuso come l'hai lasciato (di partenza aperto)."""
    return bool(_leggi().get("pannello_contenuti_aperto", True))


def imposta_pannello_aperto(valore: bool) -> None:
    _scrivi("pannello_contenuti_aperto", bool(valore))


def passaggio_presidente() -> bool:
    """Dopo ogni parte, con Successivo, un minuto di «passaggio del presidente».

    Spento di partenza: Successivo passa subito alla parte dopo.
    """
    return bool(_leggi().get("passaggio_presidente", False))


def imposta_passaggio_presidente(valore: bool) -> None:
    _scrivi("passaggio_presidente", bool(valore))


def risoluzione_scaricamento() -> int:
    """L'ultima risoluzione scelta per «Scarica tutti» (0 = la piu' alta)."""
    try:
        return int(_leggi().get("risoluzione_scaricamento", 0) or 0)
    except (TypeError, ValueError):
        return 0


def imposta_risoluzione_scaricamento(altezza: int) -> None:
    _scrivi("risoluzione_scaricamento", int(altezza or 0))


def elimina_vecchie_dopo_download() -> bool:
    """Scaricata la pubblicazione nuova, si cancellano le vecchie (scelta ricordata)."""
    return bool(_leggi().get("elimina_vecchie_dopo_download", True))


def imposta_elimina_vecchie_dopo_download(valore: bool) -> None:
    _scrivi("elimina_vecchie_dopo_download", bool(valore))
