# VisionAttend-AI Models Directory

This directory stores offline ONNX model weights for the VisionAttend-AI face recognition engine.

> **IMPORTANT**: In compliance with the project security and licensing policy, **large pre-trained model weights (`.onnx`) are NEVER committed to Git repository history.** They are ignored via `.gitignore`.

---

## Model Licensing & Usage Compliance

### InsightFace ArcFace (`buffalo_l` / `w600k_r50.onnx`)
- **Software Code**: MIT License (open source).
- **Model Weights License**: **Non-Commercial / Academic Research Use Only**.
  - **Permitted Use**: Academic research, university classroom attendance evaluation, non-profit proof-of-concept testing, and personal educational projects.
  - **Commercial Restrictions**: You **cannot** bundle, sell, or deploy `w600k_r50.onnx` inside a commercial product or commercial SaaS without an explicit commercial license agreement directly from InsightFace ([insightface.ai](https://insightface.ai)).
  - **Commercial Alternative**: For commercial production deployment, an Apache-2.0 or MIT-licensed open-weights model (e.g., MobileFaceNet trained on open-source datasets) should be substituted in `FACE_RECOGNITION_MODEL_NAME`.

---

## Download and Setup Instructions

To download the verified `w600k_r50.onnx` recognition model for local development:

### Method 1: Using Python via InsightFace Model Zoo
```python
import insightface
# Downloads buffalo_l package into ~/.insightface/models/buffalo_l
app = insightface.app.FaceAnalysis(name='buffalo_l', root='~/.insightface')
# The recognition model is located at:
# ~/.insightface/models/buffalo_l/w600k_r50.onnx
```
Copy `w600k_r50.onnx` into this `backend/models/` directory:
```bash
cp ~/.insightface/models/buffalo_l/w600k_r50.onnx backend/models/
```

### Method 2: Direct Official Release Archive Download
Download the official `buffalo_l.zip` archive directly from the DeepInsight GitHub releases:
```text
https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
```
Extract `w600k_r50.onnx` from the zip archive and place it at:
```text
backend/models/w600k_r50.onnx
```

### Verified File Specifications:
- **Filename**: `w600k_r50.onnx`
- **File size**: `174,383,860 bytes` (~174.4 MB)
- **Input shape**: `['None', 3, 112, 112]` (RGB float32, normalized via `(x - 127.5) / 127.5`)
- **Output shape**: `[1, 512]` (512-D float32 ArcFace feature embedding, L2-normalized)
- **Execution Provider**: CPUExecutionProvider (ONNX Runtime)
