"""DiffusionTrajectoryModel -- main model class with lifecycle management (Task 5).

Orchestrates ConditionEncoder, TrajectoryUNet, TrajectoryHeads, and DiffusionTrainer.
Provides training (pretrain + finetune), DDIM inference, checkpoint persistence,
and async background training.
"""

from __future__ import annotations

import json
import math
import os
import threading

import numpy as np
import torch
import torch.nn as nn

from .diffusion_condition import ConditionEncoder
from .diffusion_unet import TrajectoryUNet
from .diffusion_trainer import (
    TrajectoryHeads,
    DiffusionTrainer,
    cosine_beta_schedule,
    save_checkpoint,
    load_checkpoint,
)
from .synthetic_data import SyntheticDataGenerator


class DiffusionTrajectoryModel:
    """Diffusion trajectory prediction model -- lifecycle management.

    Wraps ConditionEncoder, TrajectoryUNet, and TrajectoryHeads into a single
    trainable / inferable model.  Handles pretraining on synthetic data,
    fine-tuning on real data, DDIM-accelerated sampling, async background
    training, and checkpoint persistence.

    Parameters
    ----------
    model_dir : str
        Directory for saving checkpoints and config JSON.
    config : dict or None
        Optional overrides for the default configuration.
    """

    def __init__(self, model_dir: str = "", config: dict | None = None):
        # ---- default config ------------------------------------------------
        default_config = {
            "n_balls": 16,
            "n_frames": 300,
            "coord_dim": 2,
            "condition_dim": 512,
            "spatial_tokens": 32,
            "base_ch": 64,
            "timesteps": 1000,
            "ddim_steps": 60,
        }
        self.config: dict = {**default_config, **(config or {})}

        # ---- sub-modules ---------------------------------------------------
        self.encoder = ConditionEncoder(
            condition_dim=self.config["condition_dim"],
            spatial_tokens=self.config["spatial_tokens"],
        )
        self.unet = TrajectoryUNet(
            n_balls=self.config["n_balls"],
            n_frames=self.config["n_frames"],
            coord_dim=self.config["coord_dim"],
            condition_dim=self.config["condition_dim"],
            spatial_tokens=self.config["spatial_tokens"],
            base_ch=self.config["base_ch"],
        )
        self.heads = TrajectoryHeads(
            coord_dim=self.config["coord_dim"],
            base_ch=self.config["base_ch"],
        )

        # ---- device --------------------------------------------------------
        from learning.gpu_device import get_device
        self._device = get_device()
        self.to(self._device)

        # ---- state ---------------------------------------------------------
        self._is_trained = False
        self._train_count = 0
        self._total_count = 0

        # ---- paths ---------------------------------------------------------
        self._base_path = (
            os.path.join(model_dir, "diffusion_model.pt") if model_dir else ""
        )
        self._ckpt_path = ""

        # ---- trainer ref (set during training) -----------------------------
        self._trainer: DiffusionTrainer | None = None

    # ==================================================================
    # Device
    # ==================================================================

    def to(self, device: str | torch.device) -> "DiffusionTrajectoryModel":
        """Move all sub-modules to *device* and return self."""
        self._device = torch.device(device)
        self.encoder.to(self._device)
        self.unet.to(self._device)
        self.heads.to(self._device)
        return self

    # ==================================================================
    # Inference
    # ==================================================================

    @torch.no_grad()
    def predict(
        self,
        table_image: np.ndarray,
        initial_balls: np.ndarray,
        shot_params: np.ndarray,
        physics_path: np.ndarray | None = None,
        condition_physics: bool = True,
        ddim_steps: int | None = None,
    ) -> np.ndarray:
        """Predict full trajectory via DDIM accelerated sampling.

        Parameters
        ----------
        table_image : np.ndarray
            (600, 1200, 3)  overhead table view (HWC).
        initial_balls : np.ndarray
            (16, 8)  ball states.
        shot_params : np.ndarray
            (3,)  [power, spin_x, spin_y].
        physics_path : np.ndarray or None
            (2, 8, 2)  physics-engine path, or None.
        condition_physics : bool
            Whether to feed *physics_path* into the encoder.  When False the
            physics conditioning is disabled even if *physics_path* is given.
        ddim_steps : int or None
            Number of DDIM steps; falls back to ``config["ddim_steps"]``.

        Returns
        -------
        np.ndarray
            (16, 300, 2)  predicted ball positions over time.
        """
        self.encoder.eval()
        self.unet.eval()
        self.heads.eval()

        device = self._device
        cfg = self.config

        # ---- convert numpy to tensors ----------------------------------
        # table_image: (H, W, 3) -> (1, 3, H, W)
        table_tensor = (
            torch.from_numpy(np.asarray(table_image, dtype=np.float32))
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(device)
        )

        # initial_balls: (16, 8) -> (1, 16, 8)
        balls_tensor = (
            torch.from_numpy(np.asarray(initial_balls, dtype=np.float32))
            .unsqueeze(0)
            .to(device)
        )

        # shot_params: (3,) -> (1, 3)
        shot_tensor = (
            torch.from_numpy(np.asarray(shot_params, dtype=np.float32))
            .unsqueeze(0)
            .to(device)
        )

        # physics_path: (2, 8, 2) or None -> (1, 2, 8, 2) or None
        phys_tensor = None
        if condition_physics and physics_path is not None:
            phys_tensor = (
                torch.from_numpy(np.asarray(physics_path, dtype=np.float32))
                .unsqueeze(0)
                .to(device)
            )

        # ---- encode condition ------------------------------------------
        condition = self.encoder(table_tensor, balls_tensor, shot_tensor, phys_tensor)
        # (1, spatial_tokens, condition_dim)

        # ---- DDIM sample -----------------------------------------------
        steps = ddim_steps if ddim_steps is not None else cfg["ddim_steps"]
        trajectory = self._ddim_sample(condition, steps)  # (1, 16, 300, 2)

        return trajectory.squeeze(0).cpu().numpy()

    # ------------------------------------------------------------------
    # DDIM sampler
    # ------------------------------------------------------------------

    @torch.no_grad()
    def _ddim_sample(
        self, condition: torch.Tensor, steps: int
    ) -> torch.Tensor:
        """DDIM accelerated sampling (deterministic).

        Parameters
        ----------
        condition : torch.Tensor
            (B, spatial_tokens, condition_dim)  encoded condition.
        steps : int
            Number of DDIM steps.

        Returns
        -------
        torch.Tensor
            (B, n_balls, n_frames, coord_dim)  predicted clean trajectory.
        """
        B = condition.shape[0]
        device = next(self.unet.parameters()).device
        cfg = self.config

        total = cfg["timesteps"]
        step_ratio = total // steps
        times = list(reversed(range(0, total, step_ratio)))

        # Start from pure noise
        x = torch.randn(
            B, cfg["n_balls"], cfg["n_frames"], cfg["coord_dim"], device=device
        )

        # Build schedule on device
        betas = cosine_beta_schedule(total)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0).to(device)

        for i, t in enumerate(times):
            t_tensor = torch.full((B,), t, dtype=torch.long, device=device)
            noise_pred = self.unet(x, t_tensor, condition)

            alpha_t = alphas_cumprod[t]
            alpha_prev = (
                alphas_cumprod[times[i + 1]]
                if i + 1 < len(times)
                else torch.tensor(1.0, device=device)
            )

            # Predict x0 from current xt and predicted noise
            x0_pred = (x - (1.0 - alpha_t).sqrt() * noise_pred) / alpha_t.sqrt()

            # DDIM: deterministic forward to x_{t-1}
            dir_xt = (1.0 - alpha_prev).sqrt() * noise_pred
            x = alpha_prev.sqrt() * x0_pred + dir_xt

        return x

    # ==================================================================
    # Training
    # ==================================================================

    def pretrain(
        self,
        synthetic_dataset: list[dict],
        epochs: int = 200,
        batch_size: int = 16,
        callback: callable | None = None,
    ) -> dict:
        """Pretrain on synthetic data.

        Uses black table images (``torch.zeros``) since synthetic samples have
        no real overhead camera views.

        Parameters
        ----------
        synthetic_dataset : list[dict]
            List of sample dicts from ``SyntheticDataGenerator.generate()``.
        epochs : int
            Number of training epochs (default 200).
        batch_size : int
            Mini-batch size (default 16).
        callback : callable or None
            Optional ``callback(epoch, avg_loss)`` called after each epoch.

        Returns
        -------
        dict
            Stats with keys ``"epochs"``, ``"final_loss"``, ``"loss_history"``,
            ``"lr_history"``.
        """
        self.encoder.train()
        self.unet.train()
        self.heads.train()

        cfg = self.config
        N = len(synthetic_dataset)
        if N == 0:
            raise ValueError("synthetic_dataset is empty")

        # Create trainer
        trainer = DiffusionTrainer(
            unet=self.unet,
            heads=self.heads,
            condition_encoder=self.encoder,
            n_frames=cfg["n_frames"],
            timesteps=cfg["timesteps"],
            lr=1e-4,
            device=str(self._device),
        )
        self._trainer = trainer

        # Shared generator for to_tensors conversion
        tensor_gen = SyntheticDataGenerator(num_frames=cfg["n_frames"])

        loss_history: list[float] = []
        lr_history: list[float] = []

        for epoch in range(1, epochs + 1):
            # Shuffle
            perm = torch.randperm(N)
            epoch_losses: list[float] = []

            for start in range(0, N, batch_size):
                indices = perm[start : start + batch_size].tolist()
                batch_samples = [synthetic_dataset[i] for i in indices]

                batch = tensor_gen.to_tensors(batch_samples)
                B_actual = len(batch_samples)

                # Black table images -- synthetic data has no real tables
                table_image = torch.zeros(
                    B_actual, 3, 600, 1200, device=self._device
                )

                loss_dict = trainer.train_step(batch, table_image)
                epoch_losses.append(loss_dict["total"])

                self._total_count += B_actual

            avg_loss = float(np.mean(epoch_losses))
            loss_history.append(avg_loss)
            lr_history.append(trainer.optimizer.param_groups[0]["lr"])

            trainer.scheduler.step()

            if callback is not None:
                callback(epoch, avg_loss)

        self._is_trained = True
        self._train_count += 1

        return {
            "epochs": epochs,
            "final_loss": loss_history[-1] if loss_history else float("inf"),
            "loss_history": loss_history,
            "lr_history": lr_history,
        }

    # ------------------------------------------------------------------

    def finetune(
        self,
        real_dataset: list[dict],
        epochs: int = 50,
        batch_size: int = 8,
        lr: float = 1e-5,
    ) -> dict:
        """Fine-tune on real-world data.

        Freezes the deeper U-Net encoder layers (down_blocks 2-4) and the
        bottleneck, then trains with a lower learning rate.  All parameters
        are unfrozen at the end.

        Parameters
        ----------
        real_dataset : list[dict]
            List of real sample dicts.
        epochs : int
            Number of fine-tuning epochs (default 50).
        batch_size : int
            Mini-batch size (default 8).
        lr : float
            Learning rate (default 1e-5).

        Returns
        -------
        dict
            Stats with keys ``"epochs"``, ``"final_loss"``, ``"loss_history"``.
        """
        self.encoder.train()
        self.unet.train()
        self.heads.train()

        cfg = self.config
        N = len(real_dataset)
        if N == 0:
            raise ValueError("real_dataset is empty")

        # ---- freeze deeper encoder layers + bottleneck -----------------
        frozen_params: list[str] = []
        for name, param in self.unet.named_parameters():
            if (
                any(f"down_blocks.{i}" in name for i in range(2, 5))
                or "bottleneck" in name
            ):
                param.requires_grad = False
                frozen_params.append(name)

        # ---- create trainer --------------------------------------------
        trainer = DiffusionTrainer(
            unet=self.unet,
            heads=self.heads,
            condition_encoder=self.encoder,
            n_frames=cfg["n_frames"],
            timesteps=cfg["timesteps"],
            lr=lr,
            device=str(self._device),
        )
        self._trainer = trainer

        tensor_gen = SyntheticDataGenerator(num_frames=cfg["n_frames"])

        loss_history: list[float] = []

        for epoch in range(1, epochs + 1):
            perm = torch.randperm(N)
            epoch_losses: list[float] = []

            for start in range(0, N, batch_size):
                indices = perm[start : start + batch_size].tolist()
                batch_samples = [real_dataset[i] for i in indices]

                batch = tensor_gen.to_tensors(batch_samples)
                B_actual = len(batch_samples)
                table_image = torch.zeros(
                    B_actual, 3, 600, 1200, device=self._device
                )

                loss_dict = trainer.train_step(batch, table_image)
                epoch_losses.append(loss_dict["total"])

                self._total_count += B_actual

            avg_loss = float(np.mean(epoch_losses))
            loss_history.append(avg_loss)
            trainer.scheduler.step()

        # ---- restore: unfreeze all parameters --------------------------
        for name, param in self.unet.named_parameters():
            param.requires_grad = True

        self._is_trained = True
        self._train_count += 1

        return {
            "epochs": epochs,
            "final_loss": loss_history[-1] if loss_history else float("inf"),
            "loss_history": loss_history,
        }

    # ------------------------------------------------------------------

    def train_async(self, dataset: list[dict], **kwargs) -> threading.Thread:
        """Launch background training in a daemon thread.

        Automatically selects ``pretrain`` or ``finetune`` based on
        ``self._is_trained``.  Extra keyword arguments are forwarded to the
        selected method.

        Parameters
        ----------
        dataset : list[dict]
            Training samples.
        **kwargs
            Forwarded to ``pretrain()`` or ``finetune()``.

        Returns
        -------
        threading.Thread
            The running daemon thread.
        """
        target = self.finetune if self._is_trained else self.pretrain
        thread = threading.Thread(
            target=target,
            args=(dataset,),
            kwargs=kwargs,
            daemon=True,
        )
        thread.start()
        return thread

    # ==================================================================
    # Status
    # ==================================================================

    def is_trained(self) -> bool:
        """Return whether the model has completed at least one training run."""
        return self._is_trained

    def get_param_count(self) -> int:
        """Return the total number of trainable parameters."""
        return sum(
            p.numel()
            for module in (self.encoder, self.unet, self.heads)
            for p in module.parameters()
        )

    def get_status(self) -> dict:
        """Return a status snapshot suitable for API / debug output."""
        return {
            "is_trained": self._is_trained,
            "train_count": self._train_count,
            "total_samples": self._total_count,
            "param_count": self.get_param_count(),
            "device": str(self._device),
            "config": self.config,
        }

    # ==================================================================
    # Persistence
    # ==================================================================

    def save(self, path: str = "") -> None:
        """Save a full checkpoint (weights + metadata).

        Parameters
        ----------
        path : str
            Target file path.  Falls back to ``_base_path`` (derived from
            *model_dir*), then to ``_ckpt_path``.
        """
        path = path or self._ckpt_path or self._base_path
        if not path:
            return

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        extra = {
            "config": self.config,
            "is_trained": self._is_trained,
            "train_count": self._train_count,
            "total_count": self._total_count,
        }
        save_checkpoint(path, self.unet, self.heads, self.encoder, extra=extra)
        self._ckpt_path = path

    def load(self, path: str = "") -> bool:
        """Load a checkpoint, restoring weights and metadata in-place.

        Tries *path*, then ``_ckpt_path``, then ``_base_path``.

        Parameters
        ----------
        path : str
            Preferred checkpoint path.

        Returns
        -------
        bool
            ``True`` if a checkpoint was loaded successfully.
        """
        path = path or self._ckpt_path or self._base_path
        if not path or not os.path.isfile(path):
            return False

        metadata = load_checkpoint(path, self.unet, self.heads, self.encoder)

        extra = metadata.get("extra", {})
        if isinstance(extra, dict):
            if "config" in extra:
                self.config.update(extra["config"])
            self._is_trained = extra.get("is_trained", True)
            self._train_count = extra.get("train_count", 0)
            self._total_count = extra.get("total_count", 0)

        self._ckpt_path = path
        self.to(self._device)
        return True

    def _save_config(self) -> None:
        """Write config + training stats as a JSON sidecar file."""
        if not self._base_path:
            return
        json_path = self._base_path.replace(".pt", "_config.json")
        data = {
            "config": self.config,
            "is_trained": self._is_trained,
            "train_count": self._train_count,
            "total_count": self._total_count,
        }
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
