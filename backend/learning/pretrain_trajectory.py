"""轨迹扩散模型预训练脚本

Step 1: 生成合成训练数据 (50K samples)
Step 2: 预训练扩散模型 (200 epochs)
Step 3: 保存checkpoint

用法:
  python -m learning.pretrain_trajectory
  python -m learning.pretrain_trajectory --samples 50000 --epochs 200 --batch-size 16
"""

import argparse
import os
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description="Pretrain trajectory diffusion model")
    parser.add_argument("--samples", type=int, default=50000, help="Synthetic samples (default: 50000)")
    parser.add_argument("--epochs", type=int, default=200, help="Training epochs (default: 200)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate (default: 1e-4)")
    parser.add_argument("--output", type=str, default="", help="Output checkpoint path")
    args = parser.parse_args()

    print("=" * 60)
    print("  Trajectory Diffusion Pretraining")
    print("=" * 60)
    print(f"  Samples: {args.samples}")
    print(f"  Epochs:  {args.epochs}")
    print(f"  Batch:   {args.batch_size}")
    print(f"  LR:      {args.lr}")
    print()

    # ─── Step 1: Generate synthetic data ───
    print("[Step 1/3] Generating synthetic training data...")
    t0 = time.time()
    from learning.synthetic_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator()
    samples = gen.generate(args.samples)
    t1 = time.time()
    print(f"  Generated {len(samples)} samples in {t1 - t0:.1f}s")

    # ─── Step 2: Create model and train ───
    print("\n[Step 2/3] Creating model and training...")

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    from learning.diffusion_model import DiffusionTrajectoryModel

    model_dir = os.path.dirname(__file__)
    model = DiffusionTrajectoryModel(model_dir=model_dir)

    total_params = model.get_param_count()
    print(f"  Model parameters: {total_params:,}")
    print(f"  Device: {model._device}")

    # pretrain() takes list[dict] directly, handles batching internally
    result = model.pretrain(
        samples, epochs=args.epochs, batch_size=args.batch_size)

    t2 = time.time()
    loss_history = result["loss_history"]
    print(f"\n  Training complete in {t2 - t1:.1f}s")
    print(f"  Final loss: {loss_history[-1]:.6f}")
    print(f"  Initial loss: {loss_history[0]:.6f}")
    if loss_history[0] > 0:
        print(f"  Reduction: {(1 - loss_history[-1] / loss_history[0]) * 100:.1f}%")

    # ─── Step 3: Save checkpoint ───
    print("\n[Step 3/3] Saving checkpoint...")
    output_path = args.output or os.path.join(model_dir, "diffusion_model.pt")
    model.save(output_path)
    print(f"  Checkpoint saved to: {output_path}")

    # Also save config for reference
    config_path = output_path.replace(".pt", "_config.json")
    import json
    with open(config_path, "w") as f:
        json.dump({
            "pretrain_samples": args.samples,
            "pretrain_epochs": args.epochs,
            "final_loss": loss_history[-1],
            "initial_loss": loss_history[0],
            "n_params": total_params,
        }, f, indent=2)
    print(f"  Config saved to: {config_path}")

    print("\n" + "=" * 60)
    print("  Pretraining complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
