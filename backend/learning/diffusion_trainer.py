"""Diffusion Trainer with output heads, noise schedules, and checkpointing (Task 4).

Components:
  - TrajectoryHeads: three Conv1d heads (pos, vel, event) on UNet features
  - Noise schedules: cosine (improved DDPM) and linear
  - DiffusionTrainer: single-step training with diffusion + auxiliary losses
  - save_checkpoint / load_checkpoint utilities
"""

from __future__ import annotations

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


# ==========================================================================
# 1. TrajectoryHeads -- auxiliary output heads
# ==========================================================================

class TrajectoryHeads(nn.Module):
    """Three output heads attached to the U-Net's penultimate features.

    Each head is a small Conv1d stack:
        pos_head:  base_ch -> base_ch//2 -> coord_dim
        vel_head:  base_ch -> base_ch//2 -> coord_dim
        event_head: base_ch -> base_ch//2 -> 4

    Input:  (B*N, base_ch, n_frames)
    Output: dict with keys "positions", "velocities", "events"
    """

    def __init__(self, coord_dim: int = 2, base_ch: int = 64):
        super().__init__()
        out_mid = base_ch // 2

        # ---- position head ----
        self.pos_head = nn.Sequential(
            nn.Conv1d(base_ch, out_mid, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv1d(out_mid, coord_dim, kernel_size=3, padding=1),
        )

        # ---- velocity head ----
        self.vel_head = nn.Sequential(
            nn.Conv1d(base_ch, out_mid, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv1d(out_mid, coord_dim, kernel_size=3, padding=1),
        )

        # ---- event head (4 classes: none, collision, pocket, cushion) ----
        self.event_head = nn.Sequential(
            nn.Conv1d(base_ch, out_mid, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv1d(out_mid, 4, kernel_size=3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """Forward pass.

        Args:
            x: (B*N, base_ch, n_frames)  U-Net features before output_conv

        Returns:
            dict with:
                "positions":  (B*N, coord_dim, n_frames)
                "velocities": (B*N, coord_dim, n_frames)
                "events":     (B*N, 4, n_frames)   logits, NOT softmaxed
        """
        return {
            "positions": self.pos_head(x),
            "velocities": self.vel_head(x),
            "events": self.event_head(x),
        }


# ==========================================================================
# 2. Noise schedules
# ==========================================================================

def cosine_beta_schedule(timesteps: int = 1000, s: float = 0.008) -> torch.Tensor:
    """Cosine noise schedule as in "Improved DDPM" (Nichol & Dhariwal, 2021).

    Args:
        timesteps: number of diffusion steps.
        s:         small offset to prevent beta from being too small near t=0.

    Returns:
        betas: (timesteps,) in [0, 1).
    """
    steps = timesteps + 1
    x = torch.linspace(0, timesteps, steps)
    alphas_cumprod = torch.cos(((x / timesteps) + s) / (1.0 + s) * math.pi * 0.5) ** 2
    alphas_cumprod = alphas_cumprod / alphas_cumprod[0]  # normalise so first is 1
    betas = 1.0 - alphas_cumprod[1:] / alphas_cumprod[:-1]
    return torch.clamp(betas, max=0.999)


def linear_beta_schedule(
    timesteps: int = 1000,
    beta_start: float = 1e-4,
    beta_end: float = 0.02,
) -> torch.Tensor:
    """Linear noise schedule (original DDPM).

    Args:
        timesteps:  number of diffusion steps.
        beta_start: beta at t=0.
        beta_end:   beta at t=T-1.

    Returns:
        betas: (timesteps,) linearly spaced from beta_start to beta_end.
    """
    return torch.linspace(beta_start, beta_end, timesteps)


# ==========================================================================
# 3. DiffusionTrainer
# ==========================================================================

class DiffusionTrainer:
    """Encapsulates the training logic for the diffusion trajectory model.

    Precomputes the diffusion schedule buffers (betas, alphas, alphas_cumprod,
    sqrt_alphas_cumprod, sqrt_one_minus_alphas_cumprod) and provides a
    single-step ``train_step(batch, table_image)`` method.

    Loss composition:
        L_total = L_diff + 0.1 * L_event + 0.05 * L_smooth

    where L_diff is the noise-prediction MSE, L_event is cross-entropy over
    the event head outputs, and L_smooth penalises acceleration (L1).
    """

    def __init__(
        self,
        unet: nn.Module,
        heads: nn.Module,
        condition_encoder: nn.Module,
        n_frames: int = 300,
        timesteps: int = 1000,
        lr: float = 1e-4,
        device: str = "cpu",
    ):
        self.device = torch.device(device)
        self.n_frames = n_frames
        self.timesteps = timesteps

        # ---- Models ----
        self.unet = unet
        self.heads = heads
        self.condition_encoder = condition_encoder

        # ---- Optimizer & scheduler ----
        params = (
            list(unet.parameters())
            + list(heads.parameters())
            + list(condition_encoder.parameters())
        )
        self.optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=1e-5)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=200,
        )

        # ---- Diffusion schedule buffers ----
        self._build_schedule()

        # Move everything to device
        self.to(device)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_schedule(self) -> None:
        """Precompute and register diffusion schedule buffers."""
        betas = cosine_beta_schedule(self.timesteps)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0)

        self.register_buffer("betas", betas)
        self.register_buffer("alphas", alphas)
        self.register_buffer("alphas_cumprod", alphas_cumprod)
        self.register_buffer("sqrt_alphas_cumprod", torch.sqrt(alphas_cumprod))
        self.register_buffer(
            "sqrt_one_minus_alphas_cumprod", torch.sqrt(1.0 - alphas_cumprod),
        )

    def register_buffer(self, name: str, tensor: torch.Tensor) -> None:
        """Register a tensor as a non-persistent instance attribute.

        Uses setattr + to(device) so it follows the trainer's device.
        """
        setattr(self, name, tensor.to(self.device))

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def to(self, device: str | torch.device) -> "DiffusionTrainer":
        """Move all models and buffers to *device*."""
        self.device = torch.device(device)
        self.unet.to(self.device)
        self.heads.to(self.device)
        self.condition_encoder.to(self.device)
        # Move any registered schedule buffers
        for name in (
            "betas", "alphas", "alphas_cumprod",
            "sqrt_alphas_cumprod", "sqrt_one_minus_alphas_cumprod",
        ):
            if hasattr(self, name):
                setattr(self, name, getattr(self, name).to(self.device))
        return self

    # ------------------------------------------------------------------
    # Forward diffusion (noise addition)
    # ------------------------------------------------------------------

    @torch.no_grad()
    def add_noise(
        self, x0: torch.Tensor, t: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward diffusion: add noise according to the schedule.

        xt = sqrt(alpha_cumprod[t]) * x0 + sqrt(1 - alpha_cumprod[t]) * noise

        Args:
            x0: (B, N, L, C) clean trajectory
            t:  (B,)          integer timesteps in [0, timesteps-1]

        Returns:
            (xt, noise)  both (B, N, L, C)
        """
        # Gather alpha_cumprod for each sample's timestep
        alpha_bar = self.alphas_cumprod[t]                     # (B,)
        alpha_bar = alpha_bar[:, None, None, None]              # (B, 1, 1, 1)
        sqrt_alpha_bar = torch.sqrt(alpha_bar)
        sqrt_one_minus_alpha_bar = torch.sqrt(1.0 - alpha_bar)

        noise = torch.randn_like(x0)
        xt = sqrt_alpha_bar * x0 + sqrt_one_minus_alpha_bar * noise
        return xt, noise

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------

    def train_step(
        self,
        batch: dict[str, torch.Tensor],
        table_image: torch.Tensor,
    ) -> dict[str, float]:
        """Single training step.

        Args:
            batch: dict with keys
                "trajectory":    (B, N, L, C)  ground-truth positions
                "initial_balls": (B, N, 8)     ball states
                "events":        (B, L)        event class indices 0-3
                "shot_params":   (B, 3)        (v0, phi, theta)
                "physics_path":  (B, 2, 8, 2)  cue/object ball path
            table_image: (B, 3, H, W) rendered table view

        Returns:
            loss_dict: {"total": ..., "diffusion": ..., "event": ..., "smooth": ...}
        """
        # ---- 1. Move data to device ----
        x0 = batch["trajectory"].to(self.device)            # (B, N, L, C)
        initial_balls = batch["initial_balls"].to(self.device)
        events_gt = batch["events"].to(self.device)          # (B, L) int64
        shot_params = batch["shot_params"].to(self.device)
        physics_path = batch["physics_path"].to(self.device)
        table = table_image.to(self.device)

        B, N, L, C = x0.shape
        device = self.device

        # ---- 2. Sample random timesteps ----
        t = torch.randint(0, self.timesteps, (B,), device=device)

        # ---- 3. Forward diffusion: add noise ----
        xt, noise = self.add_noise(x0, t)

        # ---- 4. Encode condition ----
        condition = self.condition_encoder(
            table, initial_balls, shot_params, physics_path,
        )  # (B, spatial_tokens, condition_dim)

        # ---- 5. UNet predicts noise (also get features for heads) ----
        noise_pred, unet_features = self.unet(
            xt, t, condition, return_features=True,
        )
        # noise_pred:      (B, N, L, C)
        # unet_features:   (B*N, base_ch, L)

        # ---- 6. Diffusion loss (MSE on noise) ----
        L_diff = F.mse_loss(noise_pred, noise)

        # ---- 7. Event loss via TrajectoryHeads ----
        head_outputs = self.heads(unet_features)
        # event_logits: (B*N, 4, L)
        event_logits = head_outputs["events"]
        event_logits = event_logits.reshape(B, N, 4, L).mean(dim=1)   # (B, 4, L)
        event_logits = event_logits.transpose(1, 2)                    # (B, L, 4)

        L_event = F.cross_entropy(
            event_logits.reshape(-1, 4), events_gt.reshape(-1),
        )

        # ---- 8. Smoothness loss (acceleration L1) ----
        # Estimate x0 from noise prediction
        alpha_bar = self.alphas_cumprod[t]                  # (B,)
        alpha_bar = alpha_bar[:, None, None, None]           # (B, 1, 1, 1)
        x0_pred = (
            xt - torch.sqrt(1.0 - alpha_bar) * noise_pred
        ) / torch.sqrt(alpha_bar)

        # Acceleration = 2nd finite difference along the time axis
        vel = x0_pred[:, :, 1:, :] - x0_pred[:, :, :-1, :]          # (B, N, L-1, C)
        acc = vel[:, :, 1:, :] - vel[:, :, :-1, :]                  # (B, N, L-2, C)
        L_smooth = acc.abs().mean()

        # ---- 9. Total loss ----
        loss_total = L_diff + 0.1 * L_event + 0.05 * L_smooth

        # ---- 10. Backward + clip grad norm + optimizer step ----
        self.optimizer.zero_grad()
        loss_total.backward()
        torch.nn.utils.clip_grad_norm_(
            list(self.unet.parameters())
            + list(self.heads.parameters())
            + list(self.condition_encoder.parameters()),
            max_norm=1.0,
        )
        self.optimizer.step()

        return {
            "total": loss_total.item(),
            "diffusion": L_diff.item(),
            "event": L_event.item(),
            "smooth": L_smooth.item(),
        }


# ==========================================================================
# 4. Checkpoint utilities
# ==========================================================================

def save_checkpoint(
    path: str,
    unet: nn.Module,
    heads: nn.Module,
    encoder: nn.Module,
    epoch: int = 0,
    loss: float = 0.0,
    extra: dict | None = None,
) -> None:
    """Save a training checkpoint.

    Args:
        path:    file path (e.g. "checkpoint.pt").
        unet:    TrajectoryUNet instance.
        heads:   TrajectoryHeads instance.
        encoder: ConditionEncoder instance.
        epoch:   current epoch.
        loss:    current loss value.
        extra:   optional extra metadata dict.
    """
    checkpoint: dict = {
        "unet": unet.state_dict(),
        "heads": heads.state_dict(),
        "encoder": encoder.state_dict(),
        "epoch": epoch,
        "loss": loss,
    }
    if extra is not None:
        checkpoint["extra"] = extra
    torch.save(checkpoint, path)


def load_checkpoint(
    path: str,
    unet: nn.Module,
    heads: nn.Module,
    encoder: nn.Module,
) -> dict:
    """Load a training checkpoint in-place.

    Args:
        path:    file path to the saved checkpoint.
        unet:    TrajectoryUNet instance (weights restored in-place).
        heads:   TrajectoryHeads instance (weights restored in-place).
        encoder: ConditionEncoder instance (weights restored in-place).

    Returns:
        metadata dict with keys "epoch", "loss", and optionally "extra".
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    unet.load_state_dict(checkpoint["unet"])
    heads.load_state_dict(checkpoint["heads"])
    encoder.load_state_dict(checkpoint["encoder"])
    return checkpoint
