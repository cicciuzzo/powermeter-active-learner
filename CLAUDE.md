# Progetto: powermeter-active-learner

## Contesto generale

Progetto di domotica domestica per il disaggregamento dei consumi elettrici (NILM — Non-Intrusive Load Monitoring) con apprendimento continuo semi-supervisionato.

### Dispositivi

- **rpi-hassio**: Raspberry Pi con Home Assistant (hassio). Hub centrale domotica. Espone i dati della presa smart (W realtime).
- **rpi-learner**: Raspberry Pi 3. Esegue il modello ML, ha un display GPIO con tasti fisici per labeling/feedback.

### Setup fisico

- Una **presa smart con powermeter** alimenta lavatrice + asciugatrice (somma dei consumi).
- Il segnale in ingresso al modello è un singolo valore W nel tempo (serie temporale aggregata).

## Architettura ML

### Obiettivo

Disaggregare il segnale W aggregato per classificare 4 stati: {nulla, solo lavatrice, solo asciugatrice, entrambe}. Rilevare in particolare eventi di inizio/fine ciclo per ciascun apparecchio.

### Modello

- Rete neurale piccola (< 10K parametri), eseguibile su RPi 3 senza GPU.
- Candidati: 1D-CNN su finestre temporali oppure FHMM (Factorial Hidden Markov Model).
- **Online/continuous learning**: il modello continua ad apprendere nel tempo.

### Labeling (input umano)

Due modalità complementari:

1. **Labeling proattivo**: l'utente preme un tasto quando avvia/ferma un apparecchio (facoltativo, quando se ne ricorda).
2. **Feedback reattivo**: quando il modello genera una predizione (es. "lavatrice finita"), l'utente può confermare (OK) o negare (KO) entro una **finestra temporale** (5-10 min). Dopo la scadenza → sample non etichettato.

### Trattamento label

| Esito | Uso nel training |
|---|---|
| OK entro finestra | Rinforzo positivo |
| KO entro finestra | Correzione forte (hard negative) |
| Nessun feedback | Sample non etichettato — non entra nel training supervisionato |
| Label proattivo (tasto) | Ground truth diretta |

### Confidenza e display

- Mostrare sul display il livello di confidenza del modello (entropia predizioni, rapporto OK/KO recenti).
- Metrica comprensibile: % di predizioni corrette sulle ultime N valutate.

### Decay temporale

- Exponential decay o finestra mobile sui sample vecchi, per adattarsi a cambi di apparecchio o variazioni nel tempo.

## Convenzioni di naming interno

| Alias interno | Descrizione reale |
|---|---|
| `rpi-hassio` | Raspberry Pi con Home Assistant |
| `rpi-learner` | Raspberry Pi 3 con modello ML + display + tasti |

## Convenzioni di sviluppo

- Seguire le regole globali in `~/.claude/CLAUDE.md` (dipendenze, Python 3, branching, ecc.)
- **README.md**: va aggiornato ad ogni commit significativo. Prima di committare, verificare se il README necessita di aggiornamento.
- Repo GitHub: **privato** (regola globale).
