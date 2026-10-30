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

### Method 2: Manual Download
Download `w600k_r50.onnx` from the official InsightFace release archive and save it directly as:
```text
backend/models/w600k_r50.onnx
```

### Expected File Specifications:
- **Filename**: `w600k_r50.onnx`
- **File size**: ~171 MB (179,726,670 bytes)
- **Input shape**: `[batch_size, 3, 112, 112]` (float32, normalized)
- **Output shape**: `[batch_size, 512]` (float32 feature embedding)
