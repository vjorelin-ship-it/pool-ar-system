"""Tests for the diffusion trajectory model pipeline (Tasks 1-4)."""

import os
import numpy as np


def test_synthetic_trajectory_shape():
    """Single synthetic trajectory has correct shapes and value ranges."""
    from learning.synthetic_data import SyntheticDataGenerator

    gen = SyntheticDataGenerator(num_frames=300, seed=42)
    sample = gen.generate_one()

    assert sample is not None, "Should generate at least one valid sample"

    assert sample["initial_balls"].shape == (16, 8), \
        f"initial_balls shape {sample['initial_balls'].shape} != (16, 8)"
    assert sample["trajectory"].shape == (16, 300, 2), \
        f"trajectory shape {sample['trajectory'].shape} != (16, 300, 2)"
    assert sample["events"].shape == (300, 4), \
        f"events shape {sample['events'].shape} != (300, 4)"
    assert len(sample["shot_params"]) == 3, \
        f"shot_params length {len(sample['shot_params'])} != 3"
    assert sample["physics_path"].shape == (2, 8, 2), \
        f"physics_path shape {sample['physics_path'].shape} != (2, 8, 2)"

    # Trajectory values should be in normalised [0, 1] range
    tmin = sample["trajectory"].min()
    tmax = sample["trajectory"].max()
    assert 0.0 <= tmin <= tmax <= 1.0, \
        f"trajectory values out of [0,1]: min={tmin:.4f}, max={tmax:.4f}"

    # Events should be one-hot (each row sums to 1)
    event_sums = sample["events"].sum(axis=1)
    assert np.allclose(event_sums, 1.0), \
        f"events not one-hot: row sums = {np.unique(event_sums)}"


def test_synthetic_dataset_size():
    """Generated dataset produces samples close to the requested count."""
    from learning.synthetic_data import SyntheticDataGenerator

    gen = SyntheticDataGenerator(num_frames=100, seed=0)
    dataset = gen.generate(num_samples=20)
    assert len(dataset) > 0, "Should produce at least one valid sample"
    assert len(dataset) >= 10, \
        f"Expected >=10 valid samples, got {len(dataset)}"

    # Every sample should have the correct shapes
    for i, s in enumerate(dataset):
        assert s["initial_balls"].shape == (16, 8), f"sample {i} initial_balls"
        assert s["trajectory"].shape == (16, 100, 2), f"sample {i} trajectory"
        assert s["events"].shape == (100, 4), f"sample {i} events"


def test_trajectory_perturbation():
    """Two independently generated samples have different trajectories."""
    from learning.synthetic_data import SyntheticDataGenerator

    gen = SyntheticDataGenerator(num_frames=100, seed=123)
    s1 = gen.generate_one()
    s2 = gen.generate_one()

    assert s1 is not None, "s1 should be valid"
    assert s2 is not None, "s2 should be valid"

    diff = np.abs(s1["trajectory"] - s2["trajectory"]).sum()
    assert diff > 1e-6, \
        f"Trajectories should differ (perturbation not applied). diff={diff:.8f}"

    # Also verify ball positions differ (different random layouts)
    pos_diff = np.abs(
        s1["initial_balls"][:, :2] - s2["initial_balls"][:, :2]
    ).sum()
    assert pos_diff > 1e-6, \
        f"Ball positions should differ. diff={pos_diff:.8f}"


# ======================================================================
# Task 2: Condition Encoder tests
# ======================================================================

def test_condition_encoder_output_shape():
    """ConditionEncoder produces (B, spatial_tokens, condition_dim)."""
    import torch
    from learning.diffusion_condition import ConditionEncoder

    encoder = ConditionEncoder(condition_dim=512, spatial_tokens=32)
    table = torch.randn(1, 3, 600, 1200)
    balls = torch.randn(1, 16, 8)
    shot = torch.randn(1, 3)
    phys = torch.randn(1, 2, 8, 2)
    cond = encoder(table, balls, shot, phys)
    assert cond.shape == (1, 32, 512), f"Expected (1,32,512), got {cond.shape}"


def test_condition_encoder_no_physics():
    """ConditionEncoder works with physics_path=None."""
    import torch
    from learning.diffusion_condition import ConditionEncoder

    encoder = ConditionEncoder()
    cond = encoder(
        torch.randn(1, 3, 600, 1200),
        torch.randn(1, 16, 8),
        torch.randn(1, 3),
        None,
    )
    assert cond.shape == (1, 32, 512)


# ======================================================================
# Task 3: Denoising U-Net tests
# ======================================================================

def test_unet_forward_shape():
    """TrajectoryUNet outputs noise predictions with the same shape as input."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet

    B, N_BALLS, N_FRAMES, COORD = 2, 16, 300, 2
    unet = TrajectoryUNet(
        n_balls=N_BALLS, n_frames=N_FRAMES, coord_dim=COORD,
        condition_dim=512, spatial_tokens=32,
    )
    x = torch.randn(B, N_BALLS, N_FRAMES, COORD)
    t = torch.randint(0, 1000, (B,))
    condition = torch.randn(B, 32, 512)
    out = unet(x, t, condition)
    assert out.shape == x.shape, f"Expected {x.shape}, got {out.shape}"


def test_unet_denoising_behavior():
    """UNet output is non-zero and differs from the noisy input."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet

    unet = TrajectoryUNet(n_balls=16, n_frames=300)
    unet.train()
    x_noisy = torch.randn(1, 16, 300, 2)
    t = torch.tensor([500], dtype=torch.long)
    cond = torch.randn(1, 32, 512)
    out = unet(x_noisy, t, cond)
    assert out.abs().sum() > 0.01, "Output should be non-trivial"
    assert not torch.allclose(out, x_noisy, atol=1e-3), \
        "UNet should predict noise different from the input"


def test_unet_subcomponents():
    """Verify each building block runs without error."""
    import torch
    from learning.diffusion_unet import (
        TimeEmbed, ResBlock1D, SelfAttention1D,
        CrossAttention1D, DownBlock, UpBlock, Bottleneck,
    )

    B, ch, L, time_dim, cond_dim, N = 2, 64, 100, 256, 512, 16
    device = torch.device("cpu")

    # --- TimeEmbed ---
    te = TimeEmbed(dim=time_dim).to(device)
    t = torch.randint(0, 1000, (B,), device=device)
    t_emb = te(t)
    assert t_emb.shape == (B, time_dim), f"TimeEmbed: {t_emb.shape}"

    # --- ResBlock1D ---
    rb = ResBlock1D(ch, time_dim).to(device)
    x = torch.randn(B, ch, L, device=device)
    y = rb(x, t_emb)
    assert y.shape == x.shape, f"ResBlock1D: {y.shape}"

    # --- SelfAttention1D ---
    sa = SelfAttention1D(ch, n_heads=8).to(device)
    y = sa(x)
    assert y.shape == x.shape, f"SelfAttention1D: {y.shape}"

    # --- CrossAttention1D ---
    ca = CrossAttention1D(ch, cond_dim, n_heads=8).to(device)
    x_flat = torch.randn(B * N, ch, L, device=device)
    cond = torch.randn(B, 32, cond_dim, device=device)
    y = ca(x_flat, cond, n_balls=N)
    assert y.shape == x_flat.shape, f"CrossAttention1D: {y.shape}"

    # --- DownBlock ---
    db = DownBlock(ch, ch * 2, time_dim, cond_dim, has_cross=True).to(device)
    x = torch.randn(B * N, ch, L, device=device)
    t_emb_expanded = t_emb.repeat_interleave(N, dim=0)  # (B*N, time_dim)
    y, skip = db(x, t_emb_expanded, cond, N)
    expected_out_len = (L - 1) // 2 + 1  # Conv1d stride=2, k=3, p=1
    assert y.shape == (B * N, ch * 2, expected_out_len), f"DownBlock out: {y.shape}"
    assert skip.shape == x.shape, f"DownBlock skip: {skip.shape}"

    # --- UpBlock ---
    ub = UpBlock(ch * 2, ch, ch, time_dim, cond_dim, has_cross=True).to(device)
    y_up = ub(y, skip, t_emb_expanded, cond, N)
    assert y_up.shape == skip.shape, f"UpBlock: {y_up.shape}"

    # --- Bottleneck ---
    bn = Bottleneck(ch * 2, time_dim, cond_dim).to(device)
    y_bn = bn(y, t_emb_expanded, cond, N)
    assert y_bn.shape == y.shape, f"Bottleneck: {y_bn.shape}"


def test_unet_odd_length():
    """UNet handles odd-length trajectories (e.g. 299 frames)."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet

    unet = TrajectoryUNet(n_balls=16, n_frames=299)
    x = torch.randn(1, 16, 299, 2)
    t = torch.tensor([100], dtype=torch.long)
    cond = torch.randn(1, 32, 512)
    out = unet(x, t, cond)
    assert out.shape == x.shape, f"Odd-length: expected {x.shape}, got {out.shape}"


def test_unet_gradient_flow():
    """Gradients flow through all parameters of the U-Net."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet

    unet = TrajectoryUNet(n_balls=16, n_frames=100)  # shorter for speed
    x = torch.randn(1, 16, 100, 2, requires_grad=False)
    t = torch.tensor([500], dtype=torch.long)
    cond = torch.randn(1, 32, 512, requires_grad=False)

    out = unet(x, t, cond)
    loss = out.mean()
    loss.backward()

    grads = 0
    nograds = 0
    for name, p in unet.named_parameters():
        if p.grad is not None and p.grad.abs().sum() > 0:
            grads += 1
        else:
            nograds += 1

    assert grads > 0, f"No parameters received gradients"
    assert nograds == 0, f"{nograds} parameters have zero/null gradient"


# ======================================================================
# Task 4: Diffusion Trainer + Output Heads tests
# ======================================================================

def test_trajectory_heads_output_shapes():
    """TrajectoryHeads produce correct output shapes."""
    import torch
    from learning.diffusion_trainer import TrajectoryHeads

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    # Simulated U-Net features: (B*N, base_ch, n_frames)
    B_times_N = 32  # e.g. B=2, N=16
    feats = torch.randn(B_times_N, 64, 100)
    outputs = heads(feats)

    assert outputs["positions"].shape == (B_times_N, 2, 100), \
        f"positions shape: {outputs['positions'].shape}"
    assert outputs["velocities"].shape == (B_times_N, 2, 100), \
        f"velocities shape: {outputs['velocities'].shape}"
    assert outputs["events"].shape == (B_times_N, 4, 100), \
        f"events shape: {outputs['events'].shape}"


def test_noise_schedules():
    """Cosine and linear schedules produce valid betas."""
    import torch
    from learning.diffusion_trainer import cosine_beta_schedule, linear_beta_schedule

    for ts in [10, 100, 1000]:
        betas = cosine_beta_schedule(timesteps=ts)
        assert betas.shape == (ts,), f"cosine shape mismatch for {ts}"
        assert (betas >= 0).all(), "cosine betas must be >= 0"
        assert (betas < 1).all(), "cosine betas must be < 1"
        assert torch.isfinite(betas).all(), "cosine betas contain inf/nan"

        betas = linear_beta_schedule(timesteps=ts)
        assert betas.shape == (ts,), f"linear shape mismatch for {ts}"
        assert (betas >= 0).all(), "linear betas must be >= 0"
        assert (betas < 1).all(), "linear betas must be < 1"
        assert torch.isfinite(betas).all(), "linear betas contain inf/nan"


def test_noise_addition_statistics():
    """add_noise produces xt with expected variance."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import (
        DiffusionTrainer, TrajectoryHeads,
    )

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    unet = TrajectoryUNet(n_balls=16, n_frames=100)
    encoder = ConditionEncoder()
    trainer = DiffusionTrainer(
        unet=unet, heads=heads, condition_encoder=encoder,
        n_frames=100, timesteps=1000,
    )

    x0 = torch.randn(4, 16, 100, 2)

    # At t=0, xt should be very close to x0 (only beta[0] noise added)
    t0 = torch.zeros(4, dtype=torch.long)
    xt0, noise0 = trainer.add_noise(x0, t0)
    # With cosine schedule, beta[0] is very small and
    # sqrt(alpha_cumprod[0]) ≈ 0.99995, so the diff is tiny.
    diff_frac = (xt0 - x0).abs().max() / x0.abs().max()
    assert diff_frac < 0.05, \
        f"at t=0, xt should be very close to x0. max diff frac: {diff_frac:.6f}"

    # At t=999 (near end), xt should be almost pure noise
    t999 = torch.full((4,), 999, dtype=torch.long)
    xt999, noise999 = trainer.add_noise(x0, t999)
    # The variance of xt should be close to 1
    xt999_std = xt999.std().item()
    assert 0.5 < xt999_std < 2.0, \
        f"xt at t=999 should be nearly pure noise (std={xt999_std:.4f})"


def test_training_loss_decreases():
    """Training steps should reduce loss (compare initial vs final average)."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import DiffusionTrainer, TrajectoryHeads

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    unet = TrajectoryUNet(n_balls=16, n_frames=100)
    encoder = ConditionEncoder()
    trainer = DiffusionTrainer(
        unet=unet, heads=heads, condition_encoder=encoder,
        n_frames=100, lr=1e-3,
    )

    batch = {
        "trajectory": torch.randn(2, 16, 100, 2),
        "initial_balls": torch.randn(2, 16, 8),
        "events": torch.randint(0, 4, (2, 100)),
        "shot_params": torch.randn(2, 3),
        "physics_path": torch.randn(2, 2, 8, 2),
    }
    table = torch.randn(2, 3, 600, 1200)

    losses = []
    for _ in range(30):
        loss_dict = trainer.train_step(batch, table)
        losses.append(loss_dict["total"])

    # Average of first 5 vs average of last 5 should show improvement
    first_avg = sum(losses[:5]) / 5
    last_avg = sum(losses[-5:]) / 5
    assert last_avg <= first_avg, \
        f"Loss should decrease (first5_avg={first_avg:.4f}, last5_avg={last_avg:.4f})"


def test_train_step_loss_keys():
    """train_step returns all expected loss keys."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import DiffusionTrainer, TrajectoryHeads

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    unet = TrajectoryUNet(n_balls=16, n_frames=100)
    encoder = ConditionEncoder()
    trainer = DiffusionTrainer(
        unet=unet, heads=heads, condition_encoder=encoder,
        n_frames=100, timesteps=100, lr=1e-3,
    )

    batch = {
        "trajectory": torch.randn(2, 16, 100, 2),
        "initial_balls": torch.randn(2, 16, 8),
        "events": torch.randint(0, 4, (2, 100)),
        "shot_params": torch.randn(2, 3),
        "physics_path": torch.randn(2, 2, 8, 2),
    }
    table = torch.randn(2, 3, 600, 1200)

    loss_dict = trainer.train_step(batch, table)
    for key in ("total", "diffusion", "event", "smooth"):
        assert key in loss_dict, f"Missing loss key: {key}"
        assert isinstance(loss_dict[key], float), \
            f"{key} should be float, got {type(loss_dict[key])}"


def test_checkpoint_save_load():
    """Checkpoint roundtrip preserves weights."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import (
        TrajectoryHeads, save_checkpoint, load_checkpoint,
    )

    unet = TrajectoryUNet(n_balls=16, n_frames=100)
    heads = TrajectoryHeads(base_ch=64)
    encoder = ConditionEncoder()

    path = os.path.join(os.path.dirname(__file__), "_test_ckpt.pt")
    try:
        save_checkpoint(path, unet, heads, encoder, epoch=5, loss=0.123)

        # Fresh models
        unet2 = TrajectoryUNet(n_balls=16, n_frames=100)
        heads2 = TrajectoryHeads(base_ch=64)
        encoder2 = ConditionEncoder()
        state = load_checkpoint(path, unet2, heads2, encoder2)

        assert state["epoch"] == 5
        assert abs(state["loss"] - 0.123) < 0.001

        # Verify weights were actually restored (compare with original)
        for (n1, p1), (n2, p2) in zip(
            unet.named_parameters(), unet2.named_parameters(),
        ):
            assert torch.allclose(p1, p2, atol=1e-6), \
                f"UNet param {n1} differs after load"
        for (n1, p1), (n2, p2) in zip(
            heads.named_parameters(), heads2.named_parameters(),
        ):
            assert torch.allclose(p1, p2, atol=1e-6), \
                f"Heads param {n1} differs after load"
        for (n1, p1), (n2, p2) in zip(
            encoder.named_parameters(), encoder2.named_parameters(),
        ):
            assert torch.allclose(p1, p2, atol=1e-6), \
                f"Encoder param {n1} differs after load"

    finally:
        if os.path.exists(path):
            os.remove(path)


def test_trainer_to_device():
    """DiffusionTrainer.to(device) moves models correctly."""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import DiffusionTrainer, TrajectoryHeads

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    unet = TrajectoryUNet(n_balls=16, n_frames=100)
    encoder = ConditionEncoder()
    trainer = DiffusionTrainer(
        unet=unet, heads=heads, condition_encoder=encoder,
        n_frames=100,
    )

    # After construction, everything should be on the same device
    # Check one parameter from each model
    unet_param_device = next(unet.parameters()).device
    heads_param_device = next(heads.parameters()).device
    encoder_param_device = next(encoder.parameters()).device

    assert unet_param_device == heads_param_device == encoder_param_device, \
        f"Devices differ: unet={unet_param_device}, heads={heads_param_device}, encoder={encoder_param_device}"

    # Schedule buffers should be on the same device
    assert trainer.alphas_cumprod.device == unet_param_device
