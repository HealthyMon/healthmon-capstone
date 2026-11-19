import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_config(path=None):
    with open(path or ROOT / "config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    for exercise in ("pushup", "squat", "curl"):
        if not 0 < cfg[exercise]["bent_angle"] < cfg[exercise]["extended_angle"] < 180:
            raise ValueError(f"{exercise}: 굽힘 각도 < 복귀 각도 < 180 조건이 필요합니다.")
    if cfg["runtime"]["detection_every"] < 1 or cfg["quality"]["max_sample_gap_s"] <= 0:
        raise ValueError("detection_every와 max_sample_gap_s는 양수여야 합니다.")
    if cfg["squat"].get("view") not in ("auto", "front", "side"):
        raise ValueError("squat.view는 auto/front/side 중 하나여야 합니다. 기존 설정 파일은 현재 config.json의 하체 기준 항목으로 갱신하세요.")
    for key in ("min_hip_drop_leg", "max_return_hip_drop_leg", "max_ankle_shift_leg", "front_hip_width_leg", "front_min_hip_drop_leg"):
        if cfg["squat"].get(key, 0) <= 0:
            raise ValueError(f"squat.{key}: 관측된 다리 길이 기준 양수 설정이 필요합니다.")
    return cfg
