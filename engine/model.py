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
# Input:  [batch, 1, 40]          (1 channel, 40 time steps)
#
# Conv1 : in=1,  out=8,  kernel=5, stride=1 → [batch, 8,  36]
#         params: 8*(1*5+1) = 48
# MaxPool(2)                       → [batch, 8,  18]
#
# Conv2 : in=8,  out=16, kernel=3, stride=1 → [batch, 16, 16]
#         params: 16*(8*3+1) = 400
# MaxPool(2)                       → [batch, 16,  8]
#
# Flatten                          → [batch, 128]
#
# Linear1: 128 → 32               params: 128*32 + 32 = 4 128
# Linear2: 32  →  4               params:  32*4  +  4 = 132
#
# Total params: 48 + 400 + 4 128 + 132 = 4 708   ← well under 10 000
# ---------------------------------------------------------------------------

INPUT_LEN = 40
NUM_CLASSES = 4


class PowerNet(nn.Module):
    """
    Lightweight 1D-CNN for 4-class power state classification.

    Total trainable parameters: 4 708  (< 10 000 budget).
    """

    def __init__(
        self,
        class_weights: Optional[list[float]] = None,
    ) -> None:
        super().__init__()

        # --- Convolutional feature extractor ---
        self.conv1 = nn.Conv1d(in_channels=1, out_channels=8, kernel_size=5)
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        self.conv2 = nn.Conv1d(in_channels=8, out_channels=16, kernel_size=3)
        self.pool2 = nn.MaxPool1d(kernel_size=2)

        # --- Classifier head ---
        # After conv+pool: 40 → 36 → 18 → 16 → 8 ; channels 16 → flat 128
        self.fc1 = nn.Linear(16 * 8, 32)
        self.fc2 = nn.Linear(32, NUM_CLASSES)

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
        x : Tensor of shape [batch, 1, INPUT_LEN]

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

    def predict_with_confidence(self, window: list[float]) -> tuple[int, float]:
        """
        Run inference on a single normalised window.

        Parameters
        ----------
        window : list[float]
            Normalised wattage values of length INPUT_LEN.

        Returns
        -------
        (predicted_class, confidence)
            confidence = 1 - normalised_entropy  ∈ [0, 1]
        """
        self.eval()
        with torch.no_grad():
            x = torch.tensor(window, dtype=torch.float32).view(1, 1, -1)
            logits = self(x)
            probs = F.softmax(logits, dim=-1).squeeze(0)

            pred_class = int(probs.argmax().item())

            # Normalised entropy: H / log(K), so confidence = 1 − H/log(K)
            eps = 1e-8
            entropy = -float((probs * (probs + eps).log()).sum().item())
            max_entropy = math.log(NUM_CLASSES)
            confidence = 1.0 - (entropy / max_entropy)

        return pred_class, confidence

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
