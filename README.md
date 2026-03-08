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
- Candidate architectures: **1D-CNN** over temporal windows, or **FHMM** (Factorial Hidden Markov Model).
- Online/continuous learning: the model keeps improving as new labeled data arrives, without requiring full retraining.

**Classification target:** 4-class state detection (idle, washing machine, dryer, both) with event-level start/stop detection.

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

- **Prediction entropy** as a proxy for per-sample confidence.
- **Rolling accuracy** -- percentage of correct predictions over the last N evaluated samples (OK vs KO ratio).
- **Temporal decay** -- an exponential decay or sliding window over older samples ensures the model adapts to appliance replacements or behavioral changes over time.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3 |
| Home automation | Home Assistant (hassio) |
| Inference/training hardware | Raspberry Pi 3 (ARM Cortex-A53, no GPU) |
| ML framework | TBD |
| Display/IO | GPIO display + physical buttons on rpi-learner |
| Data source | Smart plug with power meter, exposed via Home Assistant |

Specific libraries and frameworks will be selected as implementation begins, following a minimal-dependency policy.

## Project Status

Early stage -- architecture and ML approach defined, implementation pending.

## License

TBD
