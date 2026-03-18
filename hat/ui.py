#!/usr/bin/env python3
"""
hat/ui.py — Stateless e-ink UI renderer for the powermeter display.

Produces a 264x176 (landscape) 1-bit image from a UIState snapshot.
The image is passed to EinkDisplay.show_image() which handles rotation
and anti-burn-in.
"""
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from hat.epd import LANDSCAPE_W, LANDSCAPE_H

# --- Layout constants ---
BTN_COL_W = 60        # left column for button labels
MAIN_X = BTN_COL_W + 1
MAIN_W = LANDSCAPE_W - MAIN_X - 1

# Right sidebar for live W + kWh (to the right of the chart)
SIDEBAR_W = 50
CHART_RIGHT = LANDSCAPE_W - SIDEBAR_W - 2

# Button zones: first 3 zones 42px, NO zone gets remaining space (50px)
BTN_ZONE_H = 42
BTN_NO_Y = BTN_ZONE_H * 3  # NO zone starts at 126, gets 176-126=50px

# Vertical zones in main area
HEADER_Y = 2
HEADER_H = 30
CHART_Y = HEADER_H + 4
CHART_H = 65
BOTTOM_Y = CHART_Y + CHART_H + 14
BOTTOM2_Y = BOTTOM_Y + 14
BOTTOM3_Y = BOTTOM2_Y + 14

# --- Fonts (minimum 11px for e-ink readability) ---
_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
try:
    FONT_LG_BOLD = ImageFont.truetype(_FONT_BOLD_PATH, 18)
    FONT_MD = ImageFont.truetype(_FONT_PATH, 14)
    FONT_MD_BOLD = ImageFont.truetype(_FONT_BOLD_PATH, 14)
    FONT_SM = ImageFont.truetype(_FONT_PATH, 11)
    FONT_SM_BOLD = ImageFont.truetype(_FONT_BOLD_PATH, 11)
except OSError:
    _def = ImageFont.load_default()
    FONT_LG_BOLD = FONT_MD = FONT_MD_BOLD = FONT_SM = FONT_SM_BOLD = _def

# --- State names ---
STATE_DISPLAY = {
    0: "IDLE",
    1: "WASHER",
    2: "DRYER",
    3: "BOTH",
}


@dataclass
class UIState:
    """Snapshot of all values needed to render one frame."""
    watts: float = 0.0
    state: int = 0
    confidence: float = 0.0
    has_pending: bool = False
    pending_state: int = 0
    pending_remaining_s: float = 0.0
    washer_on: bool = False
    dryer_on: bool = False
    timestamp: str = ""
    has_error: bool = False
    cpu_percent: float = 0.0
    temperature: float = 0.0
    ram_percent: float = 0.0
    model_loaded: str = "Baseline"
    model_active: str = "Baseline"
    watt_history: list[float] = field(default_factory=list)
    feedback_msg: str = ""


@dataclass
class DebugState:
    """Snapshot of debug/developer info for the debug screen."""
    # Class distribution in replay buffer
    class_counts: dict[int, int] = field(default_factory=dict)
    buffer_size: int = 0
    buffer_max: int = 1000
    # Cold start progress
    cold_start_ready: bool = False
    classes_needed: int = 2
    class_min_samples: int = 5
    # Training
    last_loss: float | None = None
    training_count: int = 0
    # Confidence tracker
    rolling_accuracy: float = 0.0
    evaluated_count: int = 0
    # Drift
    drift_detected: bool = False
    # Model
    model_loaded: str = "Baseline"
    model_active: str = "Baseline"
    # System
    timestamp: str = ""
    uptime_s: float = 0.0


def render_frame(state: UIState) -> Image.Image:
    """Render one e-ink frame from UIState. Returns 264x176 1-bit image."""
    img = Image.new("1", (LANDSCAPE_W, LANDSCAPE_H), 255)
    draw = ImageDraw.Draw(img)

    # Vertical separator (button column)
    draw.line([(BTN_COL_W, 0), (BTN_COL_W, LANDSCAPE_H)], fill=0, width=1)

    _draw_buttons(draw, state)
    _draw_header(draw, state)
    draw.line([(MAIN_X, CHART_Y - 2), (LANDSCAPE_W - 1, CHART_Y - 2)], fill=0)
    _draw_line_chart(draw, state)
    _draw_sidebar(draw, state)
    draw.line([(MAIN_X, BOTTOM_Y - 4), (LANDSCAPE_W - 1, BOTTOM_Y - 4)], fill=0)
    _draw_bottom(draw, state)

    return img


def _draw_buttons(draw: ImageDraw.ImageDraw, s: UIState) -> None:
    """Draw 4 button zones: WASHER, DRYER, YES, NO."""
    for y_sep in [BTN_ZONE_H, BTN_ZONE_H * 2, BTN_NO_Y]:
        draw.line([(0, y_sep), (BTN_COL_W - 1, y_sep)], fill=0)

    _draw_toggle_zone(draw, 0, "WASHER", s.washer_on)
    _draw_toggle_zone(draw, 1, "DRYER", s.dryer_on)

    # Zone 2: YES (42px tall)
    y2 = 2 * BTN_ZONE_H + 10
    draw.text((8, y2), "YES", font=FONT_MD_BOLD, fill=0)

    # Zone 3: NO (50px tall — extra room for hints)
    y3 = BTN_NO_Y + 3
    draw.text((12, y3), "NO", font=FONT_MD_BOLD, fill=0)
    draw.text((3, y3 + 18), "x2=dbg", font=FONT_SM, fill=0)
    draw.text((3, y3 + 30), "x3=off", font=FONT_SM, fill=0)


def _draw_toggle_zone(draw: ImageDraw.ImageDraw, zone: int, label: str,
                      is_on: bool) -> None:
    """Draw a toggle button zone with label and ON/OFF pill."""
    y = zone * BTN_ZONE_H + 4
    draw.text((4, y), label, font=FONT_SM_BOLD, fill=0)
    pill_y = y + 16
    pill_w, pill_h = 38, 16
    if is_on:
        draw.rounded_rectangle(
            [(4, pill_y), (4 + pill_w, pill_y + pill_h)], radius=4, fill=0,
        )
        draw.text((10, pill_y + 1), "ON", font=FONT_SM_BOLD, fill=255)
    else:
        draw.rounded_rectangle(
            [(4, pill_y), (4 + pill_w, pill_y + pill_h)], radius=4, outline=0,
        )
        draw.text((8, pill_y + 1), "OFF", font=FONT_SM_BOLD, fill=0)


def _draw_header(draw: ImageDraw.ImageDraw, s: UIState) -> None:
    """Draw 2-line header: model+timestamp, metrics+error."""
    x = MAIN_X + 3
    # Line 1: model (left) + timestamp (right)
    model_str = s.model_active
    if s.model_loaded != s.model_active:
        model_str = f"{s.model_loaded}>{s.model_active}"
    draw.text((x, HEADER_Y), model_str, font=FONT_SM_BOLD, fill=0)
    time_str = s.timestamp
    t_bbox = draw.textbbox((0, 0), time_str, font=FONT_SM)
    draw.text((LANDSCAPE_W - (t_bbox[2] - t_bbox[0]) - 4, HEADER_Y),
              time_str, font=FONT_SM, fill=0)

    # Line 2: CPU + temp + RAM (left) + error icon (right, under timestamp)
    y2 = HEADER_Y + 14
    metrics = f"CPU:{s.cpu_percent:.0f}%  {s.temperature:.0f}C  RAM:{s.ram_percent:.0f}%"
    draw.text((x, y2), metrics, font=FONT_SM, fill=0)
    if s.has_error:
        err_str = "[!]"
        e_bbox = draw.textbbox((0, 0), err_str, font=FONT_SM_BOLD)
        draw.text((LANDSCAPE_W - (e_bbox[2] - e_bbox[0]) - 4, y2),
                  err_str, font=FONT_SM_BOLD, fill=0)


def _draw_line_chart(draw: ImageDraw.ImageDraw, s: UIState) -> None:
    """Draw watt consumption line chart (last 2 hours).

    Data is right-aligned: "Now" is always the right edge, "-2h" the left.
    None values in history represent gaps (downtime) — the line breaks there.
    """
    chart_x = MAIN_X + 3
    chart_w = CHART_RIGHT - chart_x - 2
    chart_y = CHART_Y
    chart_h = CHART_H - 14

    if not s.watt_history:
        draw.text((chart_x + chart_w // 3, chart_y + chart_h // 2),
                  "No data yet", font=FONT_SM, fill=0)
        return

    data = s.watt_history
    valid_vals = [v for v in data if v is not None]
    if not valid_vals:
        draw.text((chart_x + chart_w // 3, chart_y + chart_h // 2),
                  "No data yet", font=FONT_SM, fill=0)
        return

    max_w = max(valid_vals)
    if max_w < 10:
        max_w = 10

    max_samples = 480
    n = len(data)

    # Downsample if needed
    if n > chart_w:
        step = n / chart_w
        sampled = [data[int(i * step)] for i in range(int(chart_w))]
        plot_w = chart_w
    else:
        sampled = list(data)
        plot_w = int(chart_w * n / max_samples) if n < max_samples else chart_w
        plot_w = max(plot_w, 2)

    x_offset = chart_x + chart_w - plot_w

    # Build points, draw segments (break at None)
    num_pts = len(sampled)
    segment: list[tuple[int, int]] = []
    for i, val in enumerate(sampled):
        px = x_offset + int(i * plot_w / max(num_pts - 1, 1))
        if val is None:
            # End current segment
            if len(segment) >= 2:
                draw.line(segment, fill=0, width=1)
            segment = []
        else:
            py = chart_y + chart_h - int((val / max_w) * chart_h)
            py = max(chart_y, min(chart_y + chart_h, py))
            segment.append((px, py))
    # Draw last segment
    if len(segment) >= 2:
        draw.line(segment, fill=0, width=1)

    # Baseline
    draw.line([(chart_x, chart_y + chart_h),
               (chart_x + chart_w, chart_y + chart_h)], fill=0)

    # Axis labels
    label_y = chart_y + chart_h + 1
    draw.text((chart_x, label_y), "-2h", font=FONT_SM, fill=0)
    now_bbox = draw.textbbox((0, 0), "Now", font=FONT_SM)
    draw.text((chart_x + chart_w - (now_bbox[2] - now_bbox[0]), label_y),
              "Now", font=FONT_SM, fill=0)

    # Max scale
    draw.text((chart_x, chart_y), f"{max_w:.0f}W", font=FONT_SM, fill=0)


def _draw_sidebar(draw: ImageDraw.ImageDraw, s: UIState) -> None:
    """Draw live watts and kWh to the right of the chart."""
    x = CHART_RIGHT + 4
    y = CHART_Y + 8

    # Live watts (large)
    watts_str = f"{s.watts:.0f}"
    draw.text((x, y), watts_str, font=FONT_MD_BOLD, fill=0)
    draw.text((x, y + 16), "W", font=FONT_SM, fill=0)

    # kWh over the 2h window
    y_kwh = y + 34
    if s.watt_history:
        # Energy = sum of (watts * 15s) for each sample, converted to kWh
        total_wh = sum(v for v in s.watt_history if v is not None) * 15.0 / 3600.0
        if total_wh < 100:
            kwh_str = f"{total_wh:.1f}"
        else:
            kwh_str = f"{total_wh:.0f}"
    else:
        kwh_str = "0"
    draw.text((x, y_kwh), kwh_str, font=FONT_MD_BOLD, fill=0)
    draw.text((x, y_kwh + 16), "Wh", font=FONT_SM, fill=0)


def _draw_bottom(draw: ImageDraw.ImageDraw, s: UIState) -> None:
    """Draw bottom: prediction, confidence, feedback prompt."""
    x = MAIN_X + 3

    # Row 1: prediction
    state_text = STATE_DISPLAY.get(s.state, "???")
    draw.text((x, BOTTOM_Y), f"Prediction: {state_text}", font=FONT_SM, fill=0)

    # Row 2: confidence or feedback message
    conf_pct = s.confidence * 100
    if s.feedback_msg:
        draw.text((x, BOTTOM2_Y), s.feedback_msg, font=FONT_SM_BOLD, fill=0)
    else:
        draw.text((x, BOTTOM2_Y), f"Confidence: {conf_pct:.0f}%", font=FONT_SM, fill=0)

    # Row 3: "Is it right? YES/NO 9:45" when pending
    if s.has_pending:
        mins = int(s.pending_remaining_s) // 60
        secs = int(s.pending_remaining_s) % 60
        draw.text((x, BOTTOM3_Y), f"Is it right?  YES/NO {mins}:{secs:02d}",
                  font=FONT_SM_BOLD, fill=0)


# -----------------------------------------------------------------------
# Debug screen
# -----------------------------------------------------------------------

def render_debug_frame(d: DebugState) -> Image.Image:
    """Render the developer debug screen. Returns 264x176 1-bit image."""
    img = Image.new("1", (LANDSCAPE_W, LANDSCAPE_H), 255)
    draw = ImageDraw.Draw(img)

    x = 4
    y = 2
    LH = 14  # line height

    # Title
    draw.text((x, y), "DEBUG", font=FONT_MD_BOLD, fill=0)
    draw.text((100, y + 2), d.timestamp, font=FONT_SM, fill=0)
    model_str = d.model_active
    if d.model_loaded != d.model_active:
        model_str = f"{d.model_loaded}>{d.model_active}"
    m_bbox = draw.textbbox((0, 0), model_str, font=FONT_SM)
    draw.text((LANDSCAPE_W - (m_bbox[2] - m_bbox[0]) - 4, y + 2),
              model_str, font=FONT_SM, fill=0)
    y += LH + 4
    draw.line([(0, y), (LANDSCAPE_W, y)], fill=0)
    y += 3

    # Class distribution
    draw.text((x, y), "Replay buffer:", font=FONT_SM_BOLD, fill=0)
    y += LH
    for cls_id, cls_name in STATE_DISPLAY.items():
        count = d.class_counts.get(cls_id, 0)
        # Visual bar (max width ~120px)
        max_count = max(d.class_counts.values()) if d.class_counts else 1
        bar_w = int(count / max(max_count, 1) * 100) if count > 0 else 0
        draw.text((x, y), f"{cls_name[:5]:>5}:{count:>4}", font=FONT_SM, fill=0)
        draw.rectangle([(80, y + 2), (80 + bar_w, y + LH - 3)], fill=0)
        y += LH
    fill_pct = d.buffer_size / max(d.buffer_max, 1) * 100
    draw.text((x, y), f"Fill: {d.buffer_size}/{d.buffer_max} ({fill_pct:.0f}%)",
              font=FONT_SM, fill=0)
    y += LH + 2

    # Cold start status
    if not d.cold_start_ready:
        draw.text((x, y), "Cold start: waiting for class diversity",
                  font=FONT_SM, fill=0)
        y += LH
        non_idle_progress = []
        for cls_id, cls_name in STATE_DISPLAY.items():
            if cls_id == 0:
                continue
            count = d.class_counts.get(cls_id, 0)
            status = "OK" if count >= d.class_min_samples else f"{count}/{d.class_min_samples}"
            non_idle_progress.append(f"{cls_name[:5]}:{status}")
        draw.text((x, y), "  ".join(non_idle_progress), font=FONT_SM, fill=0)
        y += LH
    else:
        draw.text((x, y), "Cold start: CNN active", font=FONT_SM_BOLD, fill=0)
        y += LH

    # Training stats
    loss_str = f"{d.last_loss:.4f}" if d.last_loss is not None else "n/a"
    draw.text((x, y), f"Loss: {loss_str}", font=FONT_SM, fill=0)
    y += LH

    # Rolling accuracy
    draw.text((x, y), f"Accuracy: {d.evaluated_count} eval, "
              f"{d.rolling_accuracy * 100:.0f}%", font=FONT_SM, fill=0)
    y += LH

    # Drift
    drift_str = "YES" if d.drift_detected else "no"
    draw.text((x, y), f"Drift: {drift_str}", font=FONT_SM, fill=0)

    # Footer hint
    draw.text((4, LANDSCAPE_H - 14), "NOx2=back  NOx3=off", font=FONT_SM, fill=0)

    return img
