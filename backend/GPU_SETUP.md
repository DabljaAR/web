# GPU Setup Guide for DabljaAR Backend

## Quick GPU Setup

To run TTS and STT on GPU for faster performance:

### 1. Install PyTorch with CUDA

```bash
# First, uninstall CPU-only PyTorch
pip uninstall torch torchaudio

# Install PyTorch with CUDA 12.1 (adjust version for your CUDA)
pip install torch==2.6.0+cu121 torchaudio==2.6.0+cu121 --index-url https://download.pytorch.org/whl/cu121

# For latest version:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 2. Verify CUDA Installation

```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
print(f"GPU count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"GPU name: {torch.cuda.get_device_name(0)}")
```

### 3. Update Configuration

Edit your `.env` file:

```env
# Enable GPU for both models
STT_DEVICE=cuda
HABIBI_DEVICE=cuda

# Use float16 for better GPU performance (if supported)
STT_COMPUTE_TYPE=float16

# Optionally use larger model for better quality
STT_MODEL_SIZE=medium
```

### 4. Test GPU Usage

```bash
# Run this to verify GPU is being used
cd /home/moustafa/dabljaAR/web/backend
.venv/bin/python -c "
from app.config import settings
print(f'STT Device: {settings.get_device()}')
print(f'TTS Device: {settings.HABIBI_DEVICE}')

import torch
if torch.cuda.is_available():
    print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB')
else:
    print('CUDA not available')
"
```

## Performance Comparison

| Setup | STT Speed | TTS Speed | Memory Usage |
|-------|-----------|-----------|--------------|
| CPU (int8) | ~0.3x realtime | ~1.5s/sentence | 2-4GB RAM |
| GPU (float16) | ~1.5x realtime | ~0.3s/sentence | 4-6GB VRAM |

## Troubleshooting

### CUDA Version Mismatch
```bash
# Check your CUDA version
nvidia-smi

# Install matching PyTorch version
# For CUDA 11.8:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# For CUDA 12.4:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### Out of Memory Errors
```env
# Reduce model sizes
STT_MODEL_SIZE=small
STT_COMPUTE_TYPE=int8

# Lower memory threshold
STT_GPU_MEMORY_THRESHOLD=0.7
```

### Mixed Precision Issues
If you get errors with float16, fallback to float32:
```env
STT_COMPUTE_TYPE=float32
```

## Auto-Detection

The system automatically detects:
- ✅ Available CUDA devices
- ✅ Optimal compute types for your GPU
- ✅ Memory limitations

Set `DEVICE=auto` to let the system choose the best configuration.