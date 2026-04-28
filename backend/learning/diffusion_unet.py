"""Denoising U-Net for the diffusion trajectory model (Task 3).

6-level encoder-decoder with skip connections, time embeddings, self-attention,
and cross-attention to conditioning tokens.

Input:  noise trajectory (B, N_balls, N_frames, coord_dim)
        timestep t (B,)
        condition (B, spatial_tokens, condition_dim)
Output: predicted noise (B, N_balls, N_frames, coord_dim)
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


# =====================================================================
# Helper
# =====================================================================

def _gn_groups(ch: int, max_groups: int = 8) -> int:
    """Return the largest number of groups <= max_groups that divides ch."""
    for g in range(max_groups, 0, -1):
        if ch % g == 0:
            return g
    return 1


# =====================================================================
# 1. Time embedding
# =====================================================================

class TimeEmbed(nn.Module):
    """Sinusoidal time embedding followed by a 2-layer MLP.

    Mirrors the standard diffusion Transformer / U-Net timestep encoding:
        t -> sin/cos embedding -> Linear(256->1024) -> SiLU -> Linear(1024->256)
    """

    def __init__(self, dim: int = 256):
        super().__init__()
        self.dim = dim
        self.mlp = nn.Sequential(
            nn.Linear(dim, 1024),
            nn.SiLU(),
            nn.Linear(1024, dim),
        )

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        """*t*: (B,) integer timesteps.  Returns (B, dim)."""
        half = self.dim // 2
        freqs = torch.exp(
            -math.log(10000)
            * torch.arange(0, half, dtype=torch.float32, device=t.device)
            / half
        )
        args = t.float().unsqueeze(1) * freqs.unsqueeze(0)  # (B, half)
        emb = torch.cat([torch.sin(args), torch.cos(args)], dim=-1)  # (B, dim)
        return self.mlp(emb)


# =====================================================================
# 2. ResBlock1D
# =====================================================================

class ResBlock1D(nn.Module):
    """1D residual block with GroupNorm, SiLU, and time embedding injection.

        norm1 -> silu -> conv1 -> + time_proj(t_emb) -> norm2 -> silu -> dropout -> conv2
        residual connection: x + conv2(...)
    """

    def __init__(self, ch: int, time_dim: int, dropout: float = 0.1):
        super().__init__()
        groups = _gn_groups(ch)
        self.norm1 = nn.GroupNorm(groups, ch)
        self.conv1 = nn.Conv1d(ch, ch, kernel_size=3, padding=1)
        self.time_proj = nn.Linear(time_dim, ch)
        self.norm2 = nn.GroupNorm(groups, ch)
        self.dropout = nn.Dropout(dropout)
        self.conv2 = nn.Conv1d(ch, ch, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor, t_emb: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x:     (B, C, L)
            t_emb: (B, time_dim)
        Returns:
            (B, C, L)
        """
        h = self.norm1(x)
        h = F.silu(h)
        h = self.conv1(h)
        # Inject time embedding -- broadcast (B, C, 1) over the time dim
        h = h + self.time_proj(t_emb)[:, :, None]
        h = self.norm2(h)
        h = F.silu(h)
        h = self.dropout(h)
        h = self.conv2(h)
        return x + h


# =====================================================================
# 3. SelfAttention1D
# =====================================================================

class SelfAttention1D(nn.Module):
    """Self-attention over the time (sequence) dimension.

        LayerNorm(x) -> MultiheadAttention(x, x, x) with skip connection.
        Input / output are both (B, C, L).
    """

    def __init__(self, ch: int, n_heads: int = 8):
        super().__init__()
        assert ch % n_heads == 0, f"ch={ch} must be divisible by n_heads={n_heads}"
        self.norm = nn.LayerNorm(ch)
        self.attn = nn.MultiheadAttention(ch, n_heads, batch_first=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # (B, C, L) -> (B, L, C)  (MHA expects batch_first with feature dim last)
        h = x.transpose(1, 2)
        h_norm = self.norm(h)
        h_attn, _ = self.attn(h_norm, h_norm, h_norm)
        h = h + h_attn
        return h.transpose(1, 2)  # (B, L, C) -> (B, C, L)


# =====================================================================
# 4. CrossAttention1D
# =====================================================================

class CrossAttention1D(nn.Module):
    """Cross-attention between trajectory features and condition tokens.

    Q comes from the trajectory (x), K/V come from the condition.
    The condition is expanded per ball via repeat_interleave.
    """

    def __init__(self, ch: int, cond_dim: int, n_heads: int = 8):
        super().__init__()
        assert ch % n_heads == 0, f"ch={ch} must be divisible by n_heads={n_heads}"
        self.norm_x = nn.LayerNorm(ch)
        self.norm_cond = nn.LayerNorm(cond_dim)
        self.attn = nn.MultiheadAttention(
            ch, n_heads, kdim=cond_dim, vdim=cond_dim, batch_first=True
        )

    def forward(
        self, x: torch.Tensor, cond: torch.Tensor, n_balls: int
    ) -> torch.Tensor:
        """
        Args:
            x:       (B*N, C, L)   trajectory features
            cond:    (B, S, cond_dim)  condition tokens
            n_balls: N
        Returns:
            (B*N, C, L)
        """
        BN, C, L = x.shape
        B = BN // n_balls

        # Expand condition per ball: (B, S, D) -> (B*N, S, D)
        cond_expanded = cond.repeat_interleave(n_balls, dim=0)

        # (B*N, C, L) -> (B*N, L, C)
        h = x.transpose(1, 2)
        h_norm = self.norm_x(h)
        cond_norm = self.norm_cond(cond_expanded)

        h_attn, _ = self.attn(h_norm, cond_norm, cond_norm)
        h = h + h_attn
        return h.transpose(1, 2)  # (B*N, L, C) -> (B*N, C, L)


# =====================================================================
# 5. DownBlock
# =====================================================================

class DownBlock(nn.Module):
    """Down-sampling block: ResBlock -> SelfAttn -> (opt)CrossAttn -> Conv1d(stride=2).

    Returns both the down-sampled output and the intermediate skip.
    """

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        time_dim: int,
        cond_dim: int,
        has_cross: bool,
    ):
        super().__init__()
        self.res = ResBlock1D(in_ch, time_dim)
        self.self_attn = SelfAttention1D(in_ch)
        self.cross_attn = (
            CrossAttention1D(in_ch, cond_dim) if has_cross else None
        )
        self.downsample = nn.Conv1d(
            in_ch, out_ch, kernel_size=3, stride=2, padding=1
        )

    def forward(
        self, x: torch.Tensor, t_emb: torch.Tensor,
        cond: torch.Tensor, n_balls: int,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            (downsampled_output, skip_before_downsample)
        """
        x = self.res(x, t_emb)
        x = self.self_attn(x)
        if self.cross_attn is not None:
            x = self.cross_attn(x, cond, n_balls)
        skip = x
        x = self.downsample(x)
        return x, skip


# =====================================================================
# 6. UpBlock
# =====================================================================

class UpBlock(nn.Module):
    """Up-sampling block: ConvTranspose1d -> concat skip -> ResBlock -> SelfAttn
    -> (opt)CrossAttn -> Conv1d compress.
    """

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        skip_ch: int,
        time_dim: int,
        cond_dim: int,
        has_cross: bool,
    ):
        super().__init__()
        self.upsample = nn.ConvTranspose1d(
            in_ch, out_ch, kernel_size=3, stride=2, padding=1, output_padding=1
        )
        merged_ch = out_ch + skip_ch
        self.res = ResBlock1D(merged_ch, time_dim)
        self.self_attn = SelfAttention1D(merged_ch)
        self.cross_attn = (
            CrossAttention1D(merged_ch, cond_dim) if has_cross else None
        )
        self.compress = nn.Conv1d(merged_ch, out_ch, kernel_size=3, padding=1)

    def forward(
        self,
        x: torch.Tensor,
        skip: torch.Tensor,
        t_emb: torch.Tensor,
        cond: torch.Tensor,
        n_balls: int,
    ) -> torch.Tensor:
        x = self.upsample(x)
        # Align spatial length if ConvTranspose output != skip length
        if x.shape[-1] != skip.shape[-1]:
            x = F.interpolate(x, size=skip.shape[-1], mode="nearest")
        x = torch.cat([x, skip], dim=1)  # concat along channel dim
        x = self.res(x, t_emb)
        x = self.self_attn(x)
        if self.cross_attn is not None:
            x = self.cross_attn(x, cond, n_balls)
        x = self.compress(x)
        return x


# =====================================================================
# 7. Bottleneck
# =====================================================================

class Bottleneck(nn.Module):
    """Bottleneck with cross-attention (16 heads) and an FFN residual block.

        ResBlock -> CrossAttn(16 heads) -> Conv1d(ch->ch*2,1)->GELU->Conv1d(ch*2->ch,1)
    """

    def __init__(self, ch: int, time_dim: int, cond_dim: int):
        super().__init__()
        self.res = ResBlock1D(ch, time_dim)
        self.cross_attn = CrossAttention1D(ch, cond_dim, n_heads=16)
        self.ffn = nn.Sequential(
            nn.Conv1d(ch, ch * 2, kernel_size=1),
            nn.GELU(),
            nn.Conv1d(ch * 2, ch, kernel_size=1),
        )

    def forward(
        self, x: torch.Tensor, t_emb: torch.Tensor,
        cond: torch.Tensor, n_balls: int,
    ) -> torch.Tensor:
        x = self.res(x, t_emb)
        x = self.cross_attn(x, cond, n_balls)
        x = x + self.ffn(x)  # residual FFN
        return x


# =====================================================================
# 8. TrajectoryUNet  (complete U-Net)
# =====================================================================

class TrajectoryUNet(nn.Module):
    """Denoising U-Net that predicts the noise added to a trajectory.

    Parameters
    ----------
    n_balls : int
        Number of balls (16).
    n_frames : int
        Number of time frames (300).
    coord_dim : int
        Coordinate dimension (2 for x, y).
    condition_dim : int
        Dimension of the per-token condition embedding (512).
    spatial_tokens : int
        Number of spatial tokens in the condition (32).
    base_ch : int
        Base channel count (64).
    time_dim : int
        Time embedding dimension (256).
    """

    def __init__(
        self,
        n_balls: int = 16,
        n_frames: int = 300,
        coord_dim: int = 2,
        condition_dim: int = 512,
        spatial_tokens: int = 32,
        base_ch: int = 64,
        time_dim: int = 256,
    ):
        super().__init__()
        self.n_balls = n_balls
        self.n_frames = n_frames
        self.coord_dim = coord_dim

        # ---- Time embedding ----
        self.time_embed = TimeEmbed(dim=time_dim)

        # ---- Input projection ----
        self.input_proj = nn.Conv1d(coord_dim, base_ch, kernel_size=3, padding=1)

        # ---- Channel multipliers ----
        ch_mult = (1, 2, 4, 4, 6, 8)
        channels = [base_ch * m for m in ch_mult]  # [64, 128, 256, 256, 384, 512]

        # ---- Down blocks (5 blocks for 6 levels) ----
        self.down_blocks = nn.ModuleList()
        for i in range(len(ch_mult) - 1):
            in_ch = channels[i]
            out_ch = channels[i + 1]
            has_cross = (i >= 2)  # cross-attention from L2 onward
            self.down_blocks.append(
                DownBlock(in_ch, out_ch, time_dim, condition_dim, has_cross)
            )

        # ---- Bottleneck ----
        self.bottleneck = Bottleneck(channels[-1], time_dim, condition_dim)

        # ---- Up blocks (reverse order) ----
        self.up_blocks = nn.ModuleList()
        for i in range(len(ch_mult) - 1, 0, -1):
            in_ch = channels[i]       # from below / bottleneck
            out_ch = channels[i - 1]  # target channel count
            skip_ch = channels[i - 1] # skip from corresponding down block
            has_cross = (i - 1 >= 2)
            self.up_blocks.append(
                UpBlock(in_ch, out_ch, skip_ch, time_dim, condition_dim, has_cross)
            )

        # ---- Output convolution ----
        out_mid = base_ch // 2  # 32
        self.output_conv = nn.Sequential(
            nn.GroupNorm(_gn_groups(base_ch), base_ch),
            nn.SiLU(),
            nn.Conv1d(base_ch, out_mid, kernel_size=3, padding=1),
            nn.GroupNorm(_gn_groups(out_mid), out_mid),
            nn.SiLU(),
            nn.Conv1d(out_mid, coord_dim, kernel_size=3, padding=1),
        )

    # ------------------------------------------------------------------

    def forward(
        self,
        x: torch.Tensor,
        t: torch.Tensor,
        condition: torch.Tensor,
        return_features: bool = False,
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x:         (B, N_balls, N_frames, coord_dim)  noisy trajectory
            t:         (B,)                                timestep indices
            condition: (B, spatial_tokens, condition_dim)  conditioning
            return_features: if True, also return the features before
                             output_conv (B*N, base_ch, n_frames).

        Returns:
            predicted noise: (B, N_balls, N_frames, coord_dim)
            (features, noise_pred) if return_features is True
        """
        B, N, L, C = x.shape
        assert N == self.n_balls, f"Expected {self.n_balls} balls, got {N}"
        assert C == self.coord_dim, f"Expected {self.coord_dim} coords, got {C}"

        # ---- Flatten batch and balls -----
        # (B, N, L, C) -> (B*N, C, L)
        h = x.reshape(B * N, C, L)

        # ---- Time embedding (expanded per ball) ----
        t_emb = self.time_embed(t)  # (B, time_dim)
        t_emb = t_emb.repeat_interleave(N, dim=0)  # (B*N, time_dim)

        # ---- Input projection ----
        h = self.input_proj(h)  # (B*N, base_ch, L)

        # ---- Down pass ----
        skips: list[torch.Tensor] = []
        for down in self.down_blocks:
            h, skip = down(h, t_emb, condition, N)
            skips.append(skip)

        # ---- Bottleneck ----
        h = self.bottleneck(h, t_emb, condition, N)

        # ---- Up pass ----
        for up in self.up_blocks:
            skip = skips.pop()
            h = up(h, skip, t_emb, condition, N)

        # ---- Output convolution ----
        features = h  # (B*N, base_ch, L)  saved before final conv
        h = self.output_conv(h)  # (B*N, coord_dim, L)

        # ---- Reshape back ----
        h = h.reshape(B, N, L, C)

        if return_features:
            return h, features
        return h
