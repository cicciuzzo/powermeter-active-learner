# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contesto generale

Progetto di domotica domestica per il disaggregamento dei consumi elettrici (NILM — Non-Intrusive Load Monitoring) con apprendimento continuo semi-supervisionato.

### Dispositivi

- **rpi-hassio**: Raspberry Pi con Home Assistant (hassio). Hub centrale domotica. Espone i dati della presa smart (W realtime).
- **rpi-learner**: Raspberry Pi 3. Esegue il modello ML, ha un display GPIO con tasti fisici per labeling/feedback.

### Setup fisico

- Una **presa smart con powermeter** alimenta lavatrice + asciugatrice (somma dei consumi).
- Il segnale in ingresso al modello è un singolo valore W nel tempo (serie temporale aggregata).

## Comandi di sviluppo

```bash
# Installare dipendenze (standard — x86/x64)
pip install -r requirements.txt   # torch, numpy

# Installare PyTorch su ARM/Raspberry Pi (URL diverso da quello standard)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Avviare il loop principale (15s tick, Ctrl-C per stop con salvataggio checkpoint)
python3 main.py

# Eseguire un singolo modulo per test rapidi
python3 -c "from engine.model import PowerNet; m = PowerNet(); print(m.param_count)"
```

Non ci sono test automatizzati, linter o CI configurati al momento.

PyTorch è opzionale a runtime: se manca, `main.py` parte in modalità baseline-only (soglie adattive).

**Configurare la simulazione**: in `main.py:91` si istanzia `MockDataSource(washer=True, dryer=False)` — cambiare i flag per simulare scenari diversi (solo asciugatrice, entrambe accese, ecc.).

**Artefatti runtime** creati nella directory di lavoro: `replay_buffer.db` (SQLite, FIFO 1000 samples) e `powernet_checkpoint.pt` (pesi modello + stato ottimizzatore).

## Architettura del codice

### Pipeline dati (un tick = 15 secondi)

```
DataSource.read_watts()
  → SignalWindow.add()          # finestra scorrevole di 40 campioni (~10 min)
  → SignalWindow.get_normalised()  # min-max normalizzazione adattiva
  → PowerNet / BaselineDetector    # classificazione 4 classi
  → LabelManager                   # gestione labeling proattivo/reattivo
  → ReplayBuffer                   # persistenza SQLite (FIFO, max 1000 samples)
  → Trainer.maybe_train()          # mini-batch incrementale dal buffer
```

### Moduli `engine/`

| Modulo | Responsabilità |
|---|---|
| `__init__.py` | Costanti di stato condivise: `IDLE=0, WASHER=1, DRYER=2, BOTH=3` |
| `data_source.py` | `DataSource` (ABC) + `MockDataSource` (profili realistici lavatrice/asciugatrice) |
| `signal_pipeline.py` | `SignalWindow` (finestra scorrevole + normalizzazione) e `BaselineDetector` (soglie + isteresi) |
| `model.py` | `PowerNet` — 1D-CNN, 4 708 parametri. Input: `[B, 1, 40]`, output: 4 logits. Assertion `< 10K params` |
| `replay_buffer.py` | `ReplayBuffer` — SQLite persistente con campionamento stratificato per classe |
| `label_manager.py` | `LabelManager` — ciclo di vita label proattive (ground truth) e reattive (OK/KO con timeout 10 min) |
| `trainer.py` | `Trainer` — AdamW + CrossEntropyLoss pesata. Checkpoint save/load (`powernet_checkpoint.pt`) |
| `confidence.py` | `ConfidenceTracker` (rolling accuracy) + `DriftDetector` (Page-Hinkley test) |

### Punti chiave dell'architettura

- **Cold start**: sotto `COLD_START_MIN=100` campioni nel buffer, si usa `BaselineDetector` invece della CNN.
- **Class weights**: `[0.3, 1.5, 1.5, 2.0]` — IDLE sottopesato perché domina (~70% del tempo).
- **Confidenza**: `1 - entropia_normalizzata` sulle probabilità softmax.
- **Persistenza**: il replay buffer è su SQLite (`replay_buffer.db`), il checkpoint modello su file `.pt`.
- Il `main.py` gestisce SIGINT per salvare il checkpoint prima di uscire.
- **Gap noto**: `ConfidenceTracker.update()` non è ancora chiamato in `main.py` — `roll_acc` è sempre 0.0 finché non sarà integrato il feedback GPIO/reattivo.

## Architettura ML

### Obiettivo

Disaggregare il segnale W aggregato per classificare 4 stati: {nulla, solo lavatrice, solo asciugatrice, entrambe}. Rilevare in particolare eventi di inizio/fine ciclo per ciascun apparecchio.

### Modello

- Rete neurale piccola (< 10K parametri), eseguibile su RPi 3 senza GPU.
- **Implementato**: `PowerNet` — 1D-CNN su finestre temporali (4 708 parametri).
- **Alternativa futura valutata ma non implementata**: FHMM (Factorial Hidden Markov Model).
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

## Subagenti di progetto

- **roberto-caltech** (`~/.claude/agents/roberto-caltech.md`): invocare SEMPRE per decisioni sulla parte ML/reti neurali (scelta architettura, iperparametri, strategie di training, valutazioni di fattibilità, debug del modello).
