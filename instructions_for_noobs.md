# How to use the power monitor

## The screen

The small screen on the device shows what's happening with your electricity usage. Here's what each part means:

```
+--------+-----------------------------------------+------+
| WASHER | PowerNet>Baseline           17:20:19    |      |
|  [ON]  | CPU:5%  42C  RAM:85%                    |      |
| DRYER  |-----------------------------------------|  0   |
|  [OFF] |                                         |  W   |
|  YES   |     ___/\___    /\  ← line chart (2h)   |      |
|        |    /        \__/  \                     | 0.1  |
|   NO   |-----------------------------------------| Wh   |
| x2=dbg | Prediction: IDLE                        |      |
| x3=off | Confidence: 82%                         |      |
|        | Is it right?  YES/NO 9:45               |      |
+--------+-----------------------------------------+------+
```

### Top area

| What you see | What it means |
|---|---|
| **PowerNet>Baseline** | Which brain the system is using (don't worry about this) |
| **17:20:19** | When the screen was last updated |
| **[!]** | Something went wrong reading the power (only shows when there's a problem) |
| **CPU / RAM / temperature** | The device monitors itself, no action needed from you |

### Middle area (the chart)

The line chart shows electricity usage over the last 2 hours. Peaks = high usage, flat = low usage. This helps you see when appliances turn on and off. If the device was off for a while, you'll see a gap in the line.

### Right side

| What you see | What it means |
|---|---|
| **0 W** | How much electricity is being used right now |
| **0.1 Wh** | Total energy used in the last 2 hours |

### Bottom area

| What you see | What it means |
|---|---|
| **Prediction: IDLE** | The system thinks nothing is running |
| **Prediction: WASHER** | The system thinks the washing machine is running |
| **Prediction: DRYER** | The system thinks the dryer is running |
| **Prediction: BOTH** | The system thinks both are running |
| **Confidence: 82%** | How sure the system is about its guess (higher = more confident) |
| **Is it right? YES/NO 9:45** | The system is asking for your feedback (you have 9 min 45 sec left to answer) |

---

## The 4 buttons (left side)

The buttons are on the left edge of the screen, from top to bottom:

### WASHER (top button)

Press this when you **start the washing machine**. Press it again when the washing machine **finishes**.

This teaches the system what a washing machine looks like on the power meter. The more you do this, the smarter the system gets.

The screen shows [ON] when you've told the system the washer is running, and [OFF] when it's not.

If you forget to press when it finishes — no problem! You just miss that one lesson. Nothing bad happens.

### DRYER (second button)

Same as WASHER, but for the **dryer**. Press when you start it, press again when it stops.

### YES (third button)

Sometimes the system will make a guess and show "Is it right?" with a countdown timer. If the guess is **correct**, press YES.

You have 10 minutes to respond. If you don't press anything, it's fine — the system just skips that one.

### NO (fourth button)

If the system's guess is **wrong**, press NO.

For example, if it says "Prediction: WASHER" but actually it's the dryer running, press NO. This helps the system learn from its mistakes.

---

## Turning off the device safely

**Do not just unplug it!** This can damage the memory card.

Instead: **press the NO button 3 times quickly**.

The screen will show:

```
    POWER OFF

  Unplug when green LED
      stops flashing
```

Wait until the small green light on the board stops blinking, then you can safely unplug the power cable.

---

## Stand-by mode

When no appliance is running for more than 5 minutes, the screen goes into stand-by to protect it from burn-in. You'll see "Stand-by mode" with the current time.

**The system keeps working in the background** — it's still reading power and listening for changes. The screen is just resting.

The screen wakes up automatically when:
- You press any button
- An appliance turns on (power goes above 15W)
- The system wants to ask you a question ("Is it right?")

You don't need to do anything — it takes care of itself.

---

## Debug screen (for advanced users)

**Double-click the NO button** to see a technical debug screen with detailed system information. Double-click NO again to return to the normal screen.

---

## Quick reference

| I want to... | Do this |
|---|---|
| Tell the system I started the washer | Press **WASHER** |
| Tell the system the washer stopped | Press **WASHER** again |
| Tell the system I started the dryer | Press **DRYER** |
| Tell the system the dryer stopped | Press **DRYER** again |
| Confirm the system guessed right | Press **YES** |
| Tell the system it guessed wrong | Press **NO** |
| See debug info | Double-click **NO** |
| Turn off the device safely | Press **NO** 3 times fast, wait for green LED to stop |
| Check current power usage | Look at the right side of the screen (W) |
| See recent usage history | Look at the line chart in the middle |

---

## Things you can ignore

You don't need to understand or worry about:

- **PowerNet / Baseline / Gate** — the system picks the best method automatically
- **Confidence: %** — higher is better, that's all you need to know
- **CPU / RAM / temperature** — the device monitors itself, no action needed from you
- **The system running at startup** — it starts automatically when you plug it in
