"""Synthetic shot-trajectory generator for diffusion model training.

Generates 50K synthetic shot trajectories using PhysicsEngine with randomized
parameter perturbations. Each sample captures ball positions over 300 frames,
event sequences, shot parameters, and physics-engine guidance paths.
"""

import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class SyntheticConfig:
    """Noise / perturbation configuration for synthetic data generation."""

    num_frames: int = 300
    ball_types: List[str] = field(default_factory=lambda: [
        "cue", "solid", "solid", "solid", "solid", "solid", "solid", "solid",
        "black", "stripe", "stripe", "stripe", "stripe", "stripe", "stripe", "stripe",
    ])
    power_noise: float = 0.15
    cushion_noise: float = 0.10
    pocket_noise: float = 0.08
    angle_noise_deg: float = 3.0
    friction_noise: float = 0.15


class SyntheticDataGenerator:
    """Generates perturbed shot trajectories using the physics engine.

    Each sample contains:
      - initial_balls:  (16, 8)      positions, velocities, type one-hot
      - trajectory:     (16, 300, 2)  all ball positions over time
      - events:         (300, 4)      one-hot events [none, collision, pocket, stop]
      - shot_params:    (3,)          [power, spin_x, spin_y]
      - physics_path:   (2, 8, 2)     physics-engine paths for conditioning
    """

    def __init__(self, num_frames: int = 300, seed: int = 42):
        self.config = SyntheticConfig(num_frames=num_frames)
        self._rng = np.random.RandomState(seed)
        self._physics = None

    def _get_physics(self):
        if self._physics is None:
            from physics.engine import PhysicsEngine
            self._physics = PhysicsEngine()
        return self._physics

    # ─── batch generation ───────────────────────────────────────────

    def generate(self, num_samples: int = 50000) -> List[Dict]:
        """Batch-generate synthetic samples, printing progress every 5K."""
        samples = []
        for i in range(num_samples):
            s = self.generate_one()
            if s is not None:
                samples.append(s)
            if (i + 1) % 5000 == 0:
                print(f"[Synth] Generated {i + 1}/{num_samples}  (valid: {len(samples)})")
        print(f"[Synth] Finished: {len(samples)} valid samples out of {num_samples} attempts")
        return samples

    def generate_one(self) -> Optional[Dict]:
        """Generate a single synthetic sample.

        Returns None if the physics engine cannot find a valid shot for the
        randomised ball layout.
        """
        physics = self._get_physics()
        from physics.engine import Vec2
        r = self._rng

        # Random ball layout
        balls = self._random_ball_positions(r)
        cue_ball = balls[0]
        target_idx = r.randint(1, 15)
        target_ball = balls[target_idx]
        pocket_idx = r.randint(0, 5)
        pocket = physics.POCKETS[pocket_idx]

        # Physics shot
        cue_vec = Vec2(cue_ball[0], cue_ball[1])
        target_vec = Vec2(target_ball[0], target_ball[1])
        result = physics.find_best_shot(cue_vec, target_vec)
        if not result.success:
            return None

        # Randomised shot parameters
        power = r.uniform(0.2, 1.0)
        spin_x = r.uniform(-1.0, 1.0)
        spin_y = r.uniform(-1.0, 1.0)
        shot_params = np.array([power, spin_x, spin_y], dtype=np.float32)

        # Build components
        trajectory = self._build_perturbed_trajectory(
            balls, target_idx, result, power, r, physics=physics,
        )
        events = self._build_events(trajectory, target_idx, pocket, r)
        physics_path = self._build_physics_path(result)

        # initial_balls: (16, 8) = [x, y, vx, vy, is_cue, is_black, is_solid, is_stripe]
        initial_balls = np.zeros((16, 8), dtype=np.float32)
        for i, b in enumerate(balls):
            initial_balls[i, 0] = b[0]
            initial_balls[i, 1] = b[1]
            initial_balls[i, 2] = 0.0
            initial_balls[i, 3] = 0.0
            bt = self.config.ball_types[i]
            initial_balls[i, 4] = 1.0 if bt == "cue" else 0.0
            initial_balls[i, 5] = 1.0 if bt == "black" else 0.0
            initial_balls[i, 6] = 1.0 if bt == "solid" else 0.0
            initial_balls[i, 7] = 1.0 if bt == "stripe" else 0.0

        return {
            "initial_balls": initial_balls,
            "trajectory": trajectory,
            "events": events,
            "shot_params": shot_params,
            "physics_path": physics_path,
            "target_idx": target_idx,
            "pocket_idx": pocket_idx,
        }

    # ─── internal helpers ────────────────────────────────────────────

    def _random_ball_positions(self, rng) -> List[Tuple[float, float]]:
        """Generate 16 non-overlapping ball positions (normalised coords)."""
        MIN_DIST = 0.04
        positions: List[Tuple[float, float]] = []
        attempts = 0
        while len(positions) < 16 and attempts < 1000:
            x = rng.uniform(0.08, 0.92)
            y = rng.uniform(0.08, 0.92)
            ok = True
            for px, py in positions:
                if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 < MIN_DIST:
                    ok = False
                    break
            if ok:
                positions.append((x, y))
            attempts += 1
        # Fallback: place remaining balls (may overlap if placement space is tight)
        while len(positions) < 16:
            positions.append((rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)))
        return positions

    def _build_perturbed_trajectory(
        self, balls, target_idx, result, power, rng, physics=None,
    ) -> np.ndarray:
        """Build (16, F, 2) trajectory with randomised perturbations.

        Cue ball (index 0) gets angle noise, power-dependent speed profile,
        and per-frame jitter.  The target ball follows the physics target_path
        with noise.  All other balls stay at their initial positions.
        """
        F = self.config.num_frames
        traj = np.zeros((16, F, 2), dtype=np.float32)

        # Set initial frame from ball positions
        for i, b in enumerate(balls):
            traj[i, 0, 0] = b[0]
            traj[i, 0, 1] = b[1]

        cue_path = [(p.x, p.y) for p in result.cue_path]
        target_path = [(p.x, p.y) for p in result.target_path]

        if len(cue_path) == 0:
            return traj  # defensive — shouldn't happen (success already checked)

        cue_start = cue_path[0]
        cue_end = cue_path[-1] if len(cue_path) > 1 else cue_start

        # Direction vector with angle perturbation
        angle_noise_rad = (
            rng.uniform(-self.config.angle_noise_deg, self.config.angle_noise_deg)
            * math.pi / 180.0
        )
        dx = cue_end[0] - cue_start[0]
        dy = cue_end[1] - cue_start[1]
        cos_a = math.cos(angle_noise_rad)
        sin_a = math.sin(angle_noise_rad)
        dx_n = dx * cos_a - dy * sin_a
        dy_n = dx * sin_a + dy * cos_a

        # Three-phase speed profile: accel → coast → decel
        speed_scale = power * (
            1.0 + rng.uniform(-self.config.power_noise, self.config.power_noise)
        )
        accel_frames = max(1, int(F * 0.05))
        coast_frames = int(F * (0.4 + speed_scale * 0.3))
        decel_frames = F - accel_frames - coast_frames

        # Target ball motion window
        tgt_start = max(1, int(F * 0.15))
        tgt_end = min(F, tgt_start + int(F * 0.35))

        for t in range(1, F):
            # --- alpha: fraction of the cue ball path completed ---
            if t <= accel_frames:
                alpha = (t / accel_frames) * 0.5
            elif t <= accel_frames + coast_frames:
                alpha = 0.5 + (t - accel_frames) / coast_frames * 0.5
            else:
                remain = F - t
                decel_progress = remain / max(decel_frames, 1)
                friction_factor = 1.0 + rng.uniform(-self.config.friction_noise, self.config.friction_noise)
                alpha = 1.0 - 0.5 * decel_progress * decel_progress * friction_factor

            # Cue ball (index 0)
            nx = cue_start[0] + dx_n * alpha
            ny = cue_start[1] + dy_n * alpha
            traj[0, t, 0] = float(np.clip(nx + rng.normal(0, 0.001), 0.01, 0.99))
            traj[0, t, 1] = float(np.clip(ny + rng.normal(0, 0.001), 0.01, 0.99))

            # Target ball (index = target_idx)
            if t >= tgt_start and len(target_path) > 0:
                tp = min(1.0, (t - tgt_start) / max(tgt_end - tgt_start, 1))
                tx0, ty0 = target_path[0]
                if len(target_path) > 1:
                    tx1, ty1 = target_path[-1]
                    traj[target_idx, t, 0] = float(np.clip(
                        tx0 + (tx1 - tx0) * tp + rng.normal(0, 0.001), 0.01, 0.99,
                    ))
                    traj[target_idx, t, 1] = float(np.clip(
                        ty0 + (ty1 - ty0) * tp + rng.normal(0, 0.001), 0.01, 0.99,
                    ))
                else:
                    traj[target_idx, t, 0] = tx0
                    traj[target_idx, t, 1] = ty0
            else:
                traj[target_idx, t, 0] = traj[target_idx, t - 1, 0]
                traj[target_idx, t, 1] = traj[target_idx, t - 1, 1]

            # All other balls: stationary
            for i in range(1, 16):
                if i == target_idx:
                    continue
                traj[i, t, 0] = traj[i, t - 1, 0]
                traj[i, t, 1] = traj[i, t - 1, 1]

        # cushion_noise and pocket_noise used by trainer (Task 4)

        return traj

    def _build_events(self, traj, target_idx, pocket, rng) -> np.ndarray:
        """Build (F, 4) one-hot event sequence.

        Events: [none, collision, pocket, stop].
        Frames are assigned randomised but plausible event boundaries.
        Each frame is strictly one-hot.
        """
        F = traj.shape[1]  # use actual trajectory length
        events = np.zeros((F, 4), dtype=np.float32)
        events[:, 0] = 1.0  # default: all "none"

        # Collision ~15% into the sequence
        collision_f = int(F * 0.15) + rng.randint(-3, 4)
        collision_f = max(2, min(F - 10, collision_f))
        _set_event(events, collision_f, 1)

        # Pocket ~50%
        pocket_f = int(F * 0.50) + rng.randint(-5, 5)
        pocket_f = max(collision_f + 5, min(F - 5, pocket_f))
        _set_event(events, pocket_f, 2)

        # Stop ~85% — all subsequent frames are "stop"
        stop_f = int(F * 0.85) + rng.randint(-10, 10)
        stop_f = max(pocket_f + 5, min(F - 2, stop_f))
        _set_event(events, stop_f, 3)
        events[stop_f:, :] = 0.0
        events[stop_f:, 3] = 1.0

        return events

    def _build_physics_path(self, result) -> np.ndarray:
        """Extract physics-engine paths as (2, 8, 2) array.

        Index 0 = cue ball path, index 1 = target ball path.
        Each path holds up to 8 waypoints, zero-padded for shorter paths.
        """
        path = np.zeros((2, 8, 2), dtype=np.float32)
        cue_pts = [(p.x, p.y) for p in result.cue_path]
        target_pts = [(p.x, p.y) for p in result.target_path]
        for j, (x, y) in enumerate(cue_pts[:8]):
            path[0, j, 0] = x
            path[0, j, 1] = y
        for j, (x, y) in enumerate(target_pts[:8]):
            path[1, j, 0] = x
            path[1, j, 1] = y
        return path

    # ─── training tensors ────────────────────────────────────────────

    def to_tensors(self, samples: List[Dict]) -> Dict[str, 'torch.Tensor']:
        """Convert a list of sample dicts into batched training tensors.

        Events are converted from one-hot (300, 4) to class indices (300,)
        for efficient storage and cross-entropy loss compatibility.
        """
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is required for to_tensors()")
        import torch

        N = len(samples)
        F = self.config.num_frames

        traj = torch.zeros(N, 16, F, 2)
        init_balls = torch.zeros(N, 16, 8)
        events = torch.zeros(N, self.config.num_frames, 4)
        shot_params = torch.zeros(N, 3)
        phys_path = torch.zeros(N, 2, 8, 2)

        for i, s in enumerate(samples):
            traj[i] = torch.from_numpy(s["trajectory"])
            init_balls[i] = torch.from_numpy(s["initial_balls"])
            events[i] = torch.from_numpy(s["events"])
            shot_params[i] = torch.from_numpy(s["shot_params"])
            phys_path[i] = torch.from_numpy(s["physics_path"])

        return {
            "trajectory": traj,
            "initial_balls": init_balls,
            "events": events,
            "shot_params": shot_params,
            "physics_path": phys_path,
        }


# ─── module-level helpers ───────────────────────────────────────────

def _set_event(events: np.ndarray, frame: int, class_idx: int) -> None:
    """Set a strictly one-hot event at *frame*, clearing any prior event."""
    events[frame, :] = 0.0
    events[frame, class_idx] = 1.0
