# engine/trainer.py
from pathlib import Path
from typing import Optional

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError as exc:
    raise ImportError(
        "PyTorch is required. Install it for ARM (Raspberry Pi) with:\n"
        "  pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
        "Or follow https://pytorch.org/get-started/locally/ for your platform."
    ) from exc

from engine.model import PowerNet
from engine.replay_buffer import ReplayBuffer

CHECKPOINT_PATH = Path("powernet_checkpoint.pt")
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
MIN_SAMPLES_DEFAULT = 32


class Trainer:
    """
    Manages incremental mini-batch training of PowerNet.

    Uses AdamW optimiser with class-weighted CrossEntropyLoss.
    Checkpoints are saved to disk so the model survives restarts.
    """

    def __init__(
        self,
        model: PowerNet,
        class_weights: Optional[list[float]] = None,
        checkpoint_path: Path | str = CHECKPOINT_PATH,
        learning_rate: float = LEARNING_RATE,
        weight_decay: float = WEIGHT_DECAY,
    ) -> None:
        self._model = model
        self._checkpoint_path = Path(checkpoint_path)
        self._optimizer = optim.AdamW(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay,
        )

        if class_weights is not None:
            weights = torch.tensor(class_weights, dtype=torch.float32)
        elif model.class_weights is not None:
            weights = model.class_weights
        else:
            weights = None

        self._criterion = nn.CrossEntropyLoss(weight=weights)
        self._steps_done: int = 0

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def step(self, batch: list[dict]) -> float:
        """
        Execute one mini-batch gradient step.

        Parameters
        ----------
        batch : list[dict]
            Each dict must have keys 'window' (list[float]) and 'label' (int),
            as returned by ReplayBuffer.sample_batch().

        Returns
        -------
        float
            Scalar loss value for this step.
        """
        self._model.train()

        windows = torch.tensor(
            [s["window"] for s in batch], dtype=torch.float32
        ).unsqueeze(1)  # [B, 1, W]
        labels = torch.tensor([s["label"] for s in batch], dtype=torch.long)

        self._optimizer.zero_grad()
        try:
            logits = self._model(windows)
        except RuntimeError:
            # Shape mismatch — likely old replay buffer data incompatible
            # with current model architecture. Skip this batch silently.
            return 0.0
        loss = self._criterion(logits, labels)
        loss.backward()
        self._optimizer.step()

        # Free the computation graph immediately
        loss_val = float(loss.item())
        del loss, logits, windows, labels

        self._steps_done += 1
        return loss_val

    def maybe_train(
        self,
        replay_buffer: ReplayBuffer,
        min_samples: int = MIN_SAMPLES_DEFAULT,
    ) -> Optional[float]:
        """
        Perform a training step if the buffer has at least min_samples entries.

        Returns the loss, or None if training was skipped.
        """
        if replay_buffer.size() < min_samples:
            return None
        batch = replay_buffer.sample_batch(min_samples)
        if not batch:
            return None
        return self.step(batch)

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    def save_checkpoint(self) -> None:
        """Persist model weights and optimiser state to disk."""
        torch.save(
            {
                "model_state": self._model.state_dict(),
                "optimizer_state": self._optimizer.state_dict(),
                "steps_done": self._steps_done,
            },
            str(self._checkpoint_path),
        )

    def load_checkpoint(self) -> bool:
        """
        Load the latest checkpoint if available.

        Returns True on success, False if no checkpoint exists.
        """
        if not self._checkpoint_path.exists():
            return False
        try:
            checkpoint = torch.load(str(self._checkpoint_path), map_location="cpu")
            self._model.load_state_dict(checkpoint["model_state"])
            self._optimizer.load_state_dict(checkpoint["optimizer_state"])
            self._steps_done = checkpoint.get("steps_done", 0)
            return True
        except (RuntimeError, KeyError) as exc:
            print(
                f"  Checkpoint incompatible with current architecture — starting fresh\n"
                f"  ({exc})"
            )
            return False

    @property
    def steps_done(self) -> int:
        return self._steps_done
