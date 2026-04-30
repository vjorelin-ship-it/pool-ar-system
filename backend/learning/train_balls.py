"""
Train YOLOv8 nano on annotated pool ball data.

Usage:
    python -m learning.train_balls --epochs 100

The model will be saved to learning/balls.pt
"""
import sys
import os
import argparse
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DATA_DIR = os.path.join(os.path.dirname(__file__), 'training_data')
IMG_DIR = os.path.join(DATA_DIR, 'images')
LABEL_DIR = os.path.join(DATA_DIR, 'labels')
YAML_PATH = os.path.join(DATA_DIR, 'dataset.yaml')
MODEL_OUT = os.path.join(os.path.dirname(__file__), 'balls.pt')

CLASS_NAMES = [
    "cue",      # 0
    "yellow_1", # 1
    "blue_2",   # 2
    "red_3",    # 3
    "purple_4", # 4
    "orange_5", # 5
    "green_6",  # 6
    "brown_7",  # 7
    "black_8",  # 8
    "yellow_9", # 9
    "blue_10",  # 10
    "red_11",   # 11
    "purple_12",# 12
    "orange_13",# 13
    "green_14", # 14
    "brown_15", # 15
]


def prepare_dataset():
    """Create dataset.yaml and verify data."""
    images = sorted([f for f in os.listdir(IMG_DIR) if f.endswith('.jpg')])
    if not images:
        print("ERROR: No images found! Run collect_data.py first.")
        return False

    annotated = 0
    for img in images:
        label = img.replace('.jpg', '.txt')
        lpath = os.path.join(LABEL_DIR, label)
        if os.path.isfile(lpath) and os.path.getsize(lpath) > 0:
            annotated += 1

    print(f"Images: {len(images)}, Annotated: {annotated}")
    if annotated < 10:
        print("WARNING: Very few annotated images. Annotate at least 20-30 for good results.")
        print(f"  Open http://localhost:8000/annotate to label images")
        return annotated >= 5  # allow with at least 5

    # Create dataset.yaml (using all images, YOLO handles empty labels)
    data_config = {
        'path': DATA_DIR,
        'train': 'images',
        'val': 'images',
        'nc': len(CLASS_NAMES),
        'names': CLASS_NAMES,
    }
    with open(YAML_PATH, 'w') as f:
        yaml.dump(data_config, f, default_flow_style=False)
    print(f"Dataset config saved to {YAML_PATH}")
    return True


def train(epochs: int = 100, imgsz: int = 640, batch: int = 8):
    """Train YOLOv8 nano on CPU. 30-50 images ~10-15 min."""
    from ultralytics import YOLO

    print(f"Training YOLOv8 nano: epochs={epochs}, imgsz={imgsz}, batch={batch}")
    print(f"Model will be saved to: {MODEL_OUT}")

    model = YOLO('yolov8n.pt')

    results = model.train(
        data=YAML_PATH,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        name='pool_balls',
        project=os.path.dirname(MODEL_OUT),
        exist_ok=True,
        verbose=True,
        device='cpu',
        workers=0,
    )

    # Save to final path
    best_pt = os.path.join(os.path.dirname(MODEL_OUT), 'pool_balls', 'weights', 'best.pt')
    if os.path.isfile(best_pt):
        import shutil
        shutil.copy(best_pt, MODEL_OUT)
        print(f"\nModel saved to: {MODEL_OUT}")
    else:
        print(f"\nTraining completed but best.pt not found at {best_pt}")

    # Export to ONNX for DirectML inference
    onnx_path = MODEL_OUT.replace('.pt', '.onnx')
    try:
        model.export(format='onnx', imgsz=imgsz, simplify=True)
        print(f"ONNX model exported to: {onnx_path}")
    except Exception as e:
        print(f"ONNX export skipped: {e}")

    # Validate
    metrics = model.val()
    print(f"Validation metrics: {metrics}")

    return model


def main():
    parser = argparse.ArgumentParser(description='Train YOLOv8 for pool ball detection')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs')
    parser.add_argument('--imgsz', type=int, default=640, help='Image size')
    parser.add_argument('--batch', type=int, default=8, help='Batch size')
    args = parser.parse_args()

    if not prepare_dataset():
        print("\nPlease annotate images first:")
        print(f"  1. Run: python -m learning.collect_data --count 50")
        print(f"  2. Open http://localhost:8000/annotate")
        print(f"  3. Label at least 20-30 images")
        print(f"  4. Run training again")
        return

    train(epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)


if __name__ == '__main__':
    main()
