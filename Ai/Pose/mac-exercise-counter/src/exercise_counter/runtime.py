"""rtmlib pre/post processing with explicitly configured local ORT sessions.

No Body presets, URL loading, Azure provider or network access at runtime.
The small constructors below replace BaseTool's session construction only;
RTMPose/YOLOX inference, crop, normalization and decoding remain rtmlib's.
"""
import time
from pathlib import Path
import numpy as np
import onnxruntime as ort

ort.disable_telemetry_events()
from rtmlib import RTMPose, YOLOX
from .config import ROOT


def make_session(path, provider="cpu", threads=6, profile=False):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"모델이 없습니다: {path}. scripts/download_models.py를 실행하세요.")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
    opts.enable_profiling = profile
    opts.profile_file_prefix = str(ROOT / "reports" / (path.stem + "-" + provider))
    opts.log_severity_level = 3
    providers = ["CPUExecutionProvider"]
    if provider == "coreml":
        if "CoreMLExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("이 ONNX Runtime 빌드에는 CoreML provider가 없습니다.")
        static_only = path.stem == "yolox-tiny"
        cache = ROOT / "models" / ("coreml-cache-static" if static_only else "coreml-cache")
        cache.mkdir(exist_ok=True)
        providers.insert(0, ("CoreMLExecutionProvider", {
            "ModelFormat": "MLProgram", "MLComputeUnits": "ALL",
            # Detector NMS can return empty dynamic tensors; keep those ops
            # on CPU. Pose has fixed non-empty SimCC outputs and can use the
            # faster dynamic-compatible partition, verified against CPU.
            "RequireStaticInputShapes": "1" if static_only else "0", "EnableOnSubgraphs": "0",
            "ModelCacheDirectory": str(cache)
        }))
    elif provider != "cpu":
        raise ValueError(f"Unknown provider {provider}")
    session = ort.InferenceSession(str(path), sess_options=opts, providers=providers)
    session.disable_fallback()
    if provider == "coreml" and "CoreMLExecutionProvider" not in session.get_providers():
        raise RuntimeError("CoreML session 생성 중 CPU로 대체되었습니다.")
    return session


class LocalPose(RTMPose):
    def __init__(self, provider="cpu", threads=6, profile=False):
        self.onnx_model = str(ROOT / "models/rtmpose-l.onnx")
        self.model_input_size = (288, 384)  # rtmlib: W,H; ONNX: N,C,H,W
        self.mean = np.array((123.675, 116.28, 103.53), dtype=np.float32)
        self.std = np.array((58.395, 57.12, 57.375), dtype=np.float32)
        self.to_openpose = False
        self.backend, self.device = "onnxruntime", provider
        self.session = make_session(self.onnx_model, provider, threads, profile)
        assert self.session.get_inputs()[0].shape[-2:] == [384, 288]


class LocalDetector(YOLOX):
    def __init__(self, cfg, provider="cpu", threads=6, profile=False):
        self.onnx_model = str(ROOT / "models/yolox-tiny.onnx")
        self.model_input_size = (416, 416)
        self.det_mode = "human"
        self.nms_thr = cfg["nms_threshold"]
        self.score_thr = cfg["score_threshold"]
        self.mean = self.std = None
        self.backend, self.device = "onnxruntime", provider
        self.session = make_session(self.onnx_model, provider, threads, profile)
        assert self.session.get_inputs()[0].shape[-2:] == [416, 416]

    def postprocess(self, outputs, ratio=1.):
        # The official SDK export includes NMS. rtmlib hardcodes 0.3 in that
        # branch; respect our configurable threshold instead (one human class).
        if outputs.shape[-1] == 5:
            rows = outputs[0]
            return (rows[rows[:, 4] >= self.score_thr, :4] / ratio).copy()
        return super().postprocess(outputs, ratio)


class Models:
    def __init__(self, cfg, provider=None, profile=False):
        self.cfg = cfg
        self.allow_fallback = not profile
        self.fallback_generation = 0
        self.provider = provider or cfg["runtime"]["provider"]
        self.fallback_reason = None
        threads = cfg["runtime"]["threads"]
        try:
            self.pose = LocalPose(self.provider, threads, profile)
            self.detector = LocalDetector(cfg["detection"], self.provider, threads, profile)
        except Exception as exc:
            if self.provider == "cpu" or profile:
                raise
            self.fallback_reason = repr(exc)
            self.provider = "cpu"
            self.pose = LocalPose("cpu", threads, profile)
            self.detector = LocalDetector(cfg["detection"], "cpu", threads, profile)
        self.providers = {"pose": self.pose.session.get_providers(),
                          "detector": self.detector.session.get_providers()}

    def detect(self, frame):
        try:
            result = self.detector(frame)
        except Exception as exc:
            if self.detector.device != "coreml" or not self.allow_fallback:
                raise
            self.fallback_reason = "Detector CoreML runtime error: " + str(exc)
            print(self.fallback_reason,flush=True)
            self.detector = LocalDetector(self.cfg["detection"], "cpu", self.cfg["runtime"]["threads"])
            self.providers["detector"] = self.detector.session.get_providers()
            self.fallback_generation += 1
            result = self.detector(frame)
        boxes = np.asarray(result, dtype=np.float32).reshape(-1, 4)
        h, w = frame.shape[:2]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h - 1)
        return boxes

    def estimate(self, frame, box):
        # Never call RTMPose with []: rtmlib would silently use the full image.
        try:
            points, scores = self.pose(frame, bboxes=[box])
        except Exception as exc:
            if self.pose.device != "coreml" or not self.allow_fallback:
                raise
            self.fallback_reason = "Pose CoreML runtime error: " + str(exc)
            print(self.fallback_reason,flush=True)
            self.pose = LocalPose("cpu", self.cfg["runtime"]["threads"])
            self.providers["pose"] = self.pose.session.get_providers()
            self.fallback_generation += 1
            points, scores = self.pose(frame, bboxes=[box])
        if points.shape != (1, 17, 2) or scores.shape != (1, 17):
            raise RuntimeError(f"Expected Body17, got {points.shape}, {scores.shape}")
        return points[0], scores[0]
