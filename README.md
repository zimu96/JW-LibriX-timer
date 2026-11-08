# JW-LibriX-timer

Plugin **Timer adunanze** per [JW-LibriX](https://github.com/zimu96/JW-LibriX),
l'app JW Library per Linux.

Basato su OnTime Meeting Timer 1.0.9 (MIT), adattato a JW-LibriX.

## Com'è

![Timer adunanze dentro JW-LibriX](docs/immagini/timer.png)

## Cosa fa

- Conto alla rovescia delle parti dell'adunanza, con le durate prese dal programma.
- Monitor secondario a schermo intero (anche su un altro schermo o in rete) con il tempo, l'orologio e la parte successiva.
- Si accende e si spegne dalle Impostazioni: quando è acceso compare il tasto con l'orologio nella barra viola.

## Installare

Non serve scaricare niente a mano. In JW-LibriX:

**Impostazioni > Plugin > Installa**

Il plugin viene scaricato da qui e salvato nella cartella dei dati, in
`plugin/timer/`. Lo stesso tasto diventa **Aggiorna** quando c'è una versione nuova.

Installazione manuale: copia il contenuto di questo repository in `plugin/timer/`
dentro la cartella dei dati di JW-LibriX.

## Versioni

Le versioni sono i tag `vX.Y.Z`; l'app scarica lo zip del tag `v1.0.0` (indirizzo
fisso nell'app). Per questo il tag `v1.0.0` punta sempre al codice più recente.

### 1.0.0.1 — correzioni

Sostituisce la 1.0.0 (chi premeva «Aggiorna» scarica già questa).

- **Partenza in ritardo**: se l'adunanza inizia dopo l'ora fissata il tasto «Inizia» funziona
  normalmente e il ritardo viene tolto, a pochi secondi per volta, dalle parti ancora da fare
  (mai da cantici e preghiere), così si finisce in orario. Un avviso dice quanto è stato tolto.
- **Pop-up dentro l'app**: avvisi e domande stanno al centro della finestra dell'app, qualunque
  sia la sua grandezza (anche a mezzo schermo), e non finiscono più sotto Zoom.
- **Italiano**: «Sì / No / Annulla» al posto di Yes / No / Cancel, «Ritardo» nella barra in
  basso, editor delle adunanze e avvisi ancora in inglese.
- **Precedente / Successivo**: nel minuto del presidente «Precedente» non fa più saltare una
  parte; il lampeggio del tasto non resta acceso e il tasto non sparisce più.
- **Adunanza scelta dall'elenco**: il timer usa davvero quella scelta (prima restava su quella
  di prima, e contenuti e parti non coincidevano).
- **A mezzo schermo**: le scritte sotto le cifre si rimpiccioliscono per starci intere; il
  pannello Contenuti, il titolo e la barra in basso non allargano più la finestra.
- Il monitor del timer torna da solo sullo schermo scelto (anche se lo schermo compare dopo).

### 1.0.0

Prima versione.

## Licenza

MIT, vedi `LICENSE`.
