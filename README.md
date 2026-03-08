# powermeter-active-learner

## Overview

A domestic NILM (Non-Intrusive Load Monitoring) system with semi-supervised continuous learning, designed to run on a Raspberry Pi 3. The system disaggregates an aggregated power signal from a single smart plug to identify which appliances are active, using human-in-the-loop labeling to improve over time.

## Problem Statement

A single smart plug with a built-in power meter feeds both a washing machine and a tumble dryer. The system receives only the combined wattage as a time series. The goal is to disaggregate this signal and classify the current state into one of four categories:

- **Idle** -- neither appliance is running
- **Washing machine only**
- **Tumble dryer only**
- **Both** -- washing machine and tumble dryer running simultaneously

In particular, the system detects start/stop events for each appliance cycle.

## Signal Model

The observed power signal is modeled as:

```
P_obs(t) = P_wm(t) + P_td(t) + ε(t),    ε ~ N(0, σ²)
```

where `P_wm(t)` is the washing machine contribution, `P_td(t)` is the tumble dryer contribution, and `ε(t)` is additive Gaussian measurement noise.

The disaggregation problem is tractable because the two loads are separable both spectrally and in amplitude: the washing machine exhibits characteristic periodic current bursts at frequencies driven by drum rotation and heating cycles, while the tumble dryer maintains a steadier high-wattage draw. This spectral and amplitude separation makes the four-class identification problem well-posed even from the single aggregated measurement.

## Architecture

The system is composed of two Raspberry Pi devices:

| Device | Role |
|---|---|
| **rpi-hassio** | Raspberry Pi running Home Assistant (hassio). Acts as the central home-automation hub and exposes real-time wattage readings from the smart plug. |
| **rpi-learner** | Raspberry Pi 3 running the ML model. Equipped with a GPIO display and physical buttons for labeling and feedback. |

**Data flow:**

1. The smart plug reports real-time wattage to Home Assistant on `rpi-hassio`.
2. `rpi-learner` polls or subscribes to the power readings from Home Assistant.
3. The ML model on `rpi-learner` processes incoming data, generates predictions, and displays results on the GPIO screen.
4. The user optionally provides labels or feedback via the physical buttons.
5. Labeled samples feed back into the model for continuous online learning.

## ML Approach

**Model constraints:**

- Less than 10K parameters -- must run inference and training on a Raspberry Pi 3 without GPU.
- Primary architecture: **1D-CNN** over temporal windows with a replay buffer (see Online Learning below).
- The **FHMM** (Factorial Hidden Markov Model) is retained as a theoretical reference: it explicitly models the additive structure of the signal and provides a principled probabilistic decomposition, but its online incremental implementation is non-trivial and it is not the primary deployment target.
- Online/continuous learning: the model keeps improving as new labeled data arrives, without requiring full retraining.

**Classification target:** 4-class state detection (idle, washing machine, dryer, both) with event-level start/stop detection.

### Baseline

Before any ML model is considered, a threshold-based baseline is established: an adaptive detector that flags state changes based on rolling mean and local variance computed within a sliding window. Any ML model must outperform this baseline on the held-out test set to justify the added complexity. This baseline also serves as a fallback during cold-start periods when the ML model has insufficient labeled data.

### Online Learning

The 1D-CNN is updated via mini-batch incremental learning with a fixed-size replay buffer. Newly labeled samples are appended to the buffer using a FIFO aging policy, evicting the oldest entries when capacity is reached. Each model update mixes recent samples with a random draw from the historical buffer, preventing catastrophic forgetting while keeping the model responsive to distribution shifts caused by appliance replacement or seasonal usage changes.

### Class Imbalance

The class distribution is inherently skewed: the Idle state dominates because appliances run for a fraction of total time. This is handled via class-weighted cross-entropy loss, with weights inversely proportional to class frequency. HITL feedback samples belonging to rare classes (washing machine, dryer, both) are prioritized during buffer sampling to ensure the model does not degenerate toward Idle prediction under low-feedback regimes.

## Human-in-the-Loop Labeling

Two complementary labeling modes:

### Proactive labeling

The user presses a physical button when starting or stopping an appliance. This is optional and opportunistic -- it provides ground truth when the user remembers to do it.

### Reactive feedback

When the model generates a prediction (e.g., "washing machine finished"), it is shown on the display. The user can confirm (OK) or reject (KO) within a configurable time window (5--10 minutes). If the window expires with no response, the sample remains unlabeled.

### Label treatment

| Outcome | Training usage |
|---|---|
| OK within window | Positive reinforcement |
| KO within window | Hard negative correction |
| No feedback (window expired) | Unlabeled sample -- excluded from supervised training |
| Proactive label (button press) | Direct ground truth |

## Confidence and Monitoring

The GPIO display shows model confidence metrics to give the user a sense of how reliable predictions are:

- **Prediction entropy** as a proxy for per-sample confidence. Raw entropy scores are calibrated via temperature scaling applied post-training, so that reported confidence values are better aligned with empirical accuracy.
- **Rolling accuracy** -- percentage of correct predictions over the last N evaluated samples (OK vs KO ratio).
- **Temporal decay** -- an exponential decay or sliding window over older samples ensures the model adapts to appliance replacements or behavioral changes over time.
- **Drift detection** -- a Page-Hinkley test runs continuously on the raw power signal to detect structural changes (e.g., appliance replacement, sensor drift). A detected change triggers a confidence penalty and prompts more aggressive HITL solicitation until sufficient new labeled data is collected.

### Start/Stop Debouncing

State transitions are not committed on a single window prediction. A change of state is confirmed only after k consecutive windows agree on the new state. This debouncing step prevents spurious start/stop events caused by transient signal oscillations (e.g., motor startup spikes, heating element cycling) from propagating to the user-facing display or the event log.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3 |
| Home automation | Home Assistant (hassio) |
| Inference/training hardware | Raspberry Pi 3 (ARM Cortex-A53, no GPU) |
| ML framework | PyTorch (CPU) — ARM wheel, no GPU |
| Display/IO | GPIO display + physical buttons on rpi-learner |
| Data source | Smart plug with power meter, exposed via Home Assistant |

Specific libraries and frameworks will be selected as implementation begins, following a minimal-dependency policy.

## Project Status

Core engine implemented. Modules: DataSource (abstract + mock), SignalWindow, BaselineDetector, PowerNet (1D-CNN, 4 708 params), ReplayBuffer (SQLite), LabelManager, Trainer (incremental mini-batch + replay buffer), ConfidenceTracker, DriftDetector (Page-Hinkley). Pending: hardware integration (GPIO display, physical buttons), real DataSource implementation, field testing.

## License

TBD
