"""Condition Encoder for the diffusion trajectory model (Task 2).

Fuses four heterogeneous inputs -- table image, ball states, shot parameters,
and optional physics path -- into a unified condition embedding of shape
(B, spatial_tokens, condition_dim).
"""

import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
# ResNet50 availability check
# ---------------------------------------------------------------------------
try:
    import torchvision.models as tv_models
    HAS_TORCHVISION = True
except ImportError:
    HAS_TORCHVISION = False


# ===================================================================
# Image encoder backbone (ResNet50 truncated at layer2, or fallback)
# ===================================================================

def _build_image_backbone(out_channels: int):
    """Return a nn.Module that maps (B,3,600,1200) -> (B, out_channels, 75, 150).

    Uses ResNet50 truncated after layer2 when torchvision is available;
    otherwise falls back to a simple Conv2d stack.
    """
    if HAS_TORCHVISION:
        rn50 = tv_models.resnet50(weights=None)

        # Truncate: keep everything up to (and including) layer2
        layers: list[nn.Module] = []
        for name in ["conv1", "bn1", "relu", "maxpool",
                     "layer1", "layer2"]:
            layers.append(getattr(rn50, name))

        backbone = nn.Sequential(*layers)

        # layer2 outputs 512 channels for ResNet50; if the caller wants a
        # different number we insert a 1x1 conv to adapt it.
        if out_channels == 512:
            return backbone
        else:
            return nn.Sequential(
                backbone,
                nn.Conv2d(512, out_channels, kernel_size=1),
            )

    # ------------------------------------------------------------------
    # Fallback: lightweight Conv2d stack
    # ------------------------------------------------------------------
    return nn.Sequential(
        nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3),   # 300x600
        nn.BatchNorm2d(64),
        nn.SiLU(),
        nn.MaxPool2d(kernel_size=3, stride=2, padding=1),        # 150x300
        nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1),  # 150x300
        nn.BatchNorm2d(128),
        nn.SiLU(),
        nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(256),
        nn.SiLU(),
        nn.Conv2d(256, 512, kernel_size=3, stride=1, padding=1),
        nn.BatchNorm2d(512),
        nn.SiLU(),
        nn.Conv2d(512, out_channels, kernel_size=3, stride=2, padding=1),  # 75x150
    )


# ===================================================================
# ConditionEncoder
# ===================================================================

class ConditionEncoder(nn.Module):
    """Fuse table image, ball states, shot params, and physics path into a
    unified condition embedding.

    Parameters
    ----------
    condition_dim : int
        Dimension of the per-token condition embedding (default 512).
    spatial_tokens : int
        Number of spatial tokens in the output (default 32, from 4x8 grid).
    d_ball_hidden : int
        Hidden dimension for the ball-state transformer (default 128).
    """

    def __init__(
        self,
        condition_dim: int = 512,
        spatial_tokens: int = 32,
        d_ball_hidden: int = 128,
    ):
        super().__init__()
        self.condition_dim = condition_dim
        self.spatial_tokens = spatial_tokens
        self.d_ball_hidden = d_ball_hidden

        # ---- 1. Table image encoder ---------------------------------
        self.image_backbone = _build_image_backbone(out_channels=condition_dim)
        self.image_pool = nn.AdaptiveAvgPool2d((4, 8))  # 32 spatial tokens

        # ---- 2. Ball states encoder --------------------------------
        # (B, 16, 8) -> project to d_ball_hidden
        self.ball_proj = nn.Linear(8, d_ball_hidden)

        # 2-layer TransformerEncoder (16 ball tokens)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_ball_hidden,
            nhead=4,
            batch_first=True,
            dim_feedforward=d_ball_hidden * 4,
        )
        self.ball_transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)

        # Mean-pool over balls + project to condition_dim
        self.ball_head = nn.Linear(d_ball_hidden, condition_dim)

        # ---- 3. Shot params encoder --------------------------------
        self.shot_net = nn.Sequential(
            nn.Linear(3, 64),
            nn.SiLU(),
            nn.Linear(64, condition_dim),
        )

        # ---- 4. Physics path encoder -------------------------------
        self.physics_net = nn.Sequential(
            nn.Linear(32, 64),  # 2*8*2 = 32
            nn.SiLU(),
            nn.Linear(64, condition_dim),
        )

        # ---- 5. Fusion head ----------------------------------------
        # concat 4 condition_dim features -> project
        self.fusion = nn.Sequential(
            nn.Linear(condition_dim * 4, 1024),
            nn.SiLU(),
            nn.Linear(1024, condition_dim),
        )

    # ------------------------------------------------------------------

    def forward(
        self,
        table_img: torch.Tensor,
        ball_states: torch.Tensor,
        shot_params: torch.Tensor,
        physics_path: torch.Tensor | None,
    ) -> torch.Tensor:
        """
        Args:
            table_img:    (B, 3, 600, 1200)  table image
            ball_states:  (B, 16, 8)         ball (x, y, vx, vy, class, radius, ...)
            shot_params:  (B, 3)             (v0, phi, theta)
            physics_path: (B, 2, 8, 2) or None  cue/object ball physics path

        Returns:
            condition: (B, spatial_tokens, condition_dim)
        """
        B = table_img.shape[0]

        # 1. Image features: (B, condition_dim, 4, 8) -> (B, 32, condition_dim)
        img_feat = self.image_backbone(table_img)          # (B, C, H', W')
        img_feat = self.image_pool(img_feat)               # (B, C, 4, 8)
        img_feat = img_feat.flatten(2).transpose(1, 2)     # (B, 32, C)

        # 2. Ball states: (B, 16, d_ball_hidden)
        ball_tokens = self.ball_proj(ball_states)                  # (B, 16, H)
        ball_tokens = self.ball_transformer(ball_tokens)           # (B, 16, H)
        ball_pooled = ball_tokens.mean(dim=1)                      # (B, H)
        ball_feat = self.ball_head(ball_pooled)                    # (B, C)
        ball_feat = ball_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 3. Shot params: (B, 3) -> (B, C) -> broadcast
        shot_feat = self.shot_net(shot_params)                     # (B, C)
        shot_feat = shot_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 4. Physics path: (B, 2, 8, 2) or None -> (B, C) -> broadcast
        if physics_path is not None:
            phys_flat = physics_path.reshape(B, -1)                # (B, 32)
            phys_feat = self.physics_net(phys_flat)                # (B, C)
        else:
            phys_feat = torch.zeros(B, self.condition_dim,
                                    device=table_img.device,
                                    dtype=table_img.dtype)
        phys_feat = phys_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 5. Fusion: concat along last dim -> project
        fused = torch.cat([img_feat, ball_feat, shot_feat, phys_feat], dim=-1)
        condition = self.fusion(fused)  # (B, 32, condition_dim)

        return condition
