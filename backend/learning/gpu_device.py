"""统一 GPU 设备检测

返回当前环境可用的最优设备：
  DirectML (AMD/NPU/Intel GPU) > CUDA (NVIDIA GPU) > CPU

用法:
  from learning.gpu_device import get_device, get_ort_providers
  device = get_device()            # torch.device
  providers = get_ort_providers()  # ONNX Runtime execution providers
"""
import torch


def get_device() -> torch.device:
    """返回最优可用设备"""
    # 1. DirectML (Windows: AMD, Intel, NPU)
    try:
        import torch_directml
        device = torch_directml.device()
        print(f"[GPU] Using DirectML device: {device}")
        return device
    except ImportError:
        pass

    # 2. CUDA (NVIDIA)
    if torch.cuda.is_available():
        print(f"[GPU] Using CUDA: {torch.cuda.get_device_name(0)}")
        return torch.device("cuda")

    # 3. CPU fallback
    print("[GPU] No GPU found, using CPU")
    return torch.device("cpu")


def get_ort_providers() -> list:
    """返回 ONNX Runtime 执行提供器列表（DirectML优先）"""
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if 'DmlExecutionProvider' in available:
            return ['DmlExecutionProvider', 'CPUExecutionProvider']
        if 'CUDAExecutionProvider' in available:
            return ['CUDAExecutionProvider', 'CPUExecutionProvider']
    except ImportError:
        pass
    return ['CPUExecutionProvider']
