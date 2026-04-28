"""Tests for synthetic trajectory generation (Task 1: Synthetic Data Generator)."""

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
