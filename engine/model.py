# engine/model.py
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:
    raise ImportError(
        "PyTorch is required. Install it for ARM (Raspberry Pi) with:\n"
        "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
        "Or follow https://pytorch.org/get-started/locally/ for your platform."
    ) from exc

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Architecture constants — all tuned to keep total params < 10 000
# ---------------------------------------------------------------------------
#
# Input:  [batch, 4, 20]          (4 channels, 20 time steps per channel)
#
# Conv1 : in=4,  out=16, kernel=5, stride=1 → [batch, 16, 16]
#         params: 16*(4*5+1) = 336
# MaxPool(2)                       → [batch, 16,  8]
#
# Conv2 : in=16, out=32, kernel=3, stride=1 → [batch, 32,  6]
#         params: 32*(16*3+1) = 1 568
# MaxPool(2)                       → [batch, 32,  3]
#
# Flatten                          → [batch, 96]
#
# Linear1: 96 → 24                params: 96*24 + 24 = 2 328
# Linear2: 24 →  4                params:  24*4 +  4 = 100
#
# Total params: 336 + 1 568 + 2 328 + 100 = 4 332   ← well under 10 000
# ---------------------------------------------------------------------------

INPUT_LEN = 20        # samples per channel (was 40)
NUM_CLASSES = 4
NUM_CHANNELS = 4      # 4 time scales: 5min, 30min, 1h, 2h


class PowerNet(nn.Module):
    """
    Multi-scale 1D-CNN for 4-class power state classification.

    Input: [batch, 4, 20] — 4 channels (5min, 30min, 1h, 2h), 20 samples each.
    Downsampling from raw buffers uses block averaging to avoid aliasing.

    Architecture:
        Conv1d(4, 16, k=5) → MaxPool(2) → Conv1d(16, 32, k=3) → MaxPool(2)
        → Flatten(96) → Linear(96, 24) → Linear(24, 4)

    Total params: ~4332 (< 10K budget)
    """

    def __init__(
        self,
        class_weights: Optional[list[float]] = None,
    ) -> None:
        super().__init__()

        # --- Convolutional feature extractor ---
        self.conv1 = nn.Conv1d(in_channels=NUM_CHANNELS, out_channels=16, kernel_size=5)
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        self.conv2 = nn.Conv1d(in_channels=16, out_channels=32, kernel_size=3)
        self.pool2 = nn.MaxPool1d(kernel_size=2)

        # --- Classifier head ---
        # After conv+pool: 20 → 16 → 8 → 6 → 3; channels=32 → flat=96
        self.fc1 = nn.Linear(32 * 3, 24)
        self.fc2 = nn.Linear(24, NUM_CLASSES)

        # Store class weights for loss computation
        if class_weights is not None:
            self.register_buffer(
                "class_weights",
                torch.tensor(class_weights, dtype=torch.float32),
            )
        else:
            self.register_buffer("class_weights", None)

        self._verify_param_count()

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : Tensor of shape [batch, NUM_CHANNELS, INPUT_LEN]

        Returns
        -------
        Tensor of shape [batch, NUM_CLASSES]  (raw logits)
        """
        x = self.pool1(F.relu(self.conv1(x)))
        x = self.pool2(F.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)   # flatten
        x = F.relu(self.fc1(x))
        return self.fc2(x)

    # ------------------------------------------------------------------
    # Inference helper
    # ------------------------------------------------------------------

    def predict_with_confidence(
        self, multi_scale_channels: list[list[float]]
    ) -> tuple[int, float]:
        """
        Run inference on multi-scale channels.

        Parameters
        ----------
        multi_scale_channels : list of 4 lists, each of 20 floats (normalized)

        Returns
        -------
        (predicted_class, confidence) where confidence = 1 - normalized_entropy
        """
        self.set_eval_mode()
        with torch.no_grad():
            x = torch.tensor(
                multi_scale_channels, dtype=torch.float32
            ).unsqueeze(0)  # [1, 4, 20]
            logits = self(x)
            probs = F.softmax(logits, dim=-1).squeeze(0)

            pred_class = int(probs.argmax().item())

            # Normalised entropy: H / log(K), so confidence = 1 - H/log(K)
            eps = 1e-8
            entropy = -float((probs * (probs + eps).log()).sum().item())
            max_entropy = math.log(NUM_CLASSES)
            confidence = 1.0 - (entropy / max_entropy)

        return pred_class, confidence

    def set_eval_mode(self) -> None:
        """Switch to evaluation mode (disables dropout, batchnorm updates)."""
        nn.Module.eval(self)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _verify_param_count(self) -> None:
        total = sum(p.numel() for p in self.parameters())
        assert total < 10_000, (
            f"PowerNet has {total} parameters — exceeds 10 000 budget. "
            "Reduce architecture."
        )
        # Store for external inspection
        self._param_count = total

    @property
    def param_count(self) -> int:
        return self._param_count
