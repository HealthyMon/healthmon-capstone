"""Loopback-only Windows bridge for Unity; reuses the branch's unmodified RTMPose counter.

No Qt, CoreML or game-backend dependency. Frames live in memory and are never recorded.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import math
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal

COUNTER_ROOT = Path(__file__).resolve().parent / "mac-exercise-counter"
sys.path.insert(0, str(COUNTER_ROOT / "src"))
from exercise_counter.config import load_config
from exercise_counter.counter import EXERCISE_GUIDES
from exercise_counter.pipeline import Pipeline
from exercise_counter.runtime import Models

MAX_JPEG_BYTES = 2 * 1024 * 1024
STATE_LABELS = {"unready": "준비 자세 확인", "ready": "준비 완료", "bent": "굽힘 확인", "returning": "복귀 확인"}


class Start(BaseModel):
    exercise: Literal["squat", "pushup", "curl"]
    squat_view: Literal["auto", "front", "side"] = "auto"


class Control(BaseModel):
    command: Literal["pause", "retarget"]
    paused: bool = False


def player_message(snap):
    """Adapt the shared counter's coaching copy to the game's HUD without changing counting."""
    guides = {
        "squat": "골반 · 무릎 · 발목을 화면 안에 배치",
        "pushup": "어깨 · 팔꿈치 · 손목을 화면 안에 배치 · 전신 판정은 하체 인식 필요",
        "curl": "어깨 · 팔꿈치 · 손목을 화면 안에 배치 · 좌우 개별 카운트",
    }
    message = snap["message"].replace(EXERCISE_GUIDES[snap["exercise"]], guides[snap["exercise"]])
    phrases = {
        "준비 · 굽히세요": "준비 완료 · 굽힘 시작",
        "굽힘 확인 · 복귀하세요": "굽힘 완료 · 준비 자세로 복귀",
        "위팔을 몸 옆으로 내린 방향으로 유지하세요": "위팔을 몸 옆에 고정",
        "몸통을 수평에 가깝게 유지하세요": "몸통 수평 유지",
        "발 또는 카메라 위치 변화 · 준비 자세를 다시 확인하세요": "위치 변경 감지 · 준비 자세 재정렬",
        "필수 관절 사이 거리가 너무 짧아 측정을 보류합니다": "관절 구분 불가 · 촬영 거리 조정 필요",
        "관절 출력 또는 입력 시간 무효": "자세 인식 불가 · 준비 자세 재정렬",
        "보이지 않습니다": "인식 불가",
    }
    for source, replacement in phrases.items():
        message = message.replace(source, replacement)
    return message


def packet(session_id, pipeline, snap, sequence=0, jpeg=None):
    counts = snap["counts"]
    states = list(dict.fromkeys(STATE_LABELS.get(s, "준비 자세 확인") for s in snap["states"].values()))
    angles = snap.get("angles", {})
    names = {"left": "왼쪽", "right": "오른쪽", "elbow": "팔꿈치", "knee": "무릎", "hip_drop": "골반 이동"}
    angle_text = "\n".join(f"{names.get(k, k)} {v}{'' if k == 'hip_drop' else '°'}" for k, v in angles.items())
    return dict(session_id=session_id, exercise=snap["exercise"], sequence=sequence,
                count=sum(counts.values()), left_count=counts.get("left", 0), right_count=counts.get("right", 0),
                paused=snap["paused"], tracked=bool(snap.get("tracked", False)),
                message=player_message(snap), phase="일시정지" if snap["paused"] else " · ".join(states),
                angle_text=angle_text or "관절 확인 중", body_assessment=snap.get("diagnostics", {}).get("body_assessment", "보류"),
                processing_ms=round(snap.get("processing_ms", 0), 2), jpeg_base64=jpeg)


def create_app(models=None):
    app = FastAPI(title="HealthMon Pose", docs_url=None, redoc_url=None)
    sessions = {}
    lock = threading.RLock()
    config = load_config()
    config["runtime"]["provider"] = "cpu"
    model_holder = [models]

    @app.middleware("http")
    async def local_only(request, call_next):
        # Unity sends no Origin. Reject browser-origin mutations and DNS rebinding hosts.
        from starlette.responses import JSONResponse
        if request.url.hostname not in ("127.0.0.1", "localhost", "::1", "testserver") or request.headers.get("origin"):
            return JSONResponse({"detail": "local Unity client only"}, status_code=403)
        return await call_next(request)

    def expire():
        now = time.monotonic()
        for sid in list(sessions):
            if now - sessions[sid]["touched"] > 1800:
                del sessions[sid]

    def get(sid, allow_finished=False):
        expire()
        state = sessions.get(sid)
        if state is None or (state["finished"] and not allow_finished):
            raise HTTPException(404, "session expired")
        state["touched"] = time.monotonic()
        return state

    @app.get("/health")
    def health():
        with lock:
            expire()
            return {"status": "ready" if model_holder[0] is not None else "idle", "service": "healthmon-pose",
                    "provider": "CPUExecutionProvider", "active_sessions": sum(not s["finished"] for s in sessions.values())}

    @app.post("/sessions")
    def start(body: Start):
        with lock:
            expire()
            if sum(not s["finished"] for s in sessions.values()) >= 4:
                raise HTTPException(409, "close an existing session first")
            if model_holder[0] is None:
                try:
                    model_holder[0] = Models(config, provider="cpu")
                except (FileNotFoundError, RuntimeError) as exc:
                    raise HTTPException(503, "pose models are unavailable; run Start-HealthMon.cmd -Target Setup") from exc
            cfg = copy.deepcopy(config)
            cfg["squat"]["view"] = body.squat_view
            pipeline = Pipeline(cfg, body.exercise, models=model_holder[0])
            sid = uuid4().hex
            result = packet(sid, pipeline, pipeline.counter.snapshot())
            # Bound completed-session receipts without touching active sessions.
            while len(sessions) >= 64:
                old = next((key for key, value in sessions.items() if value["finished"]), None)
                if old is None: break
                del sessions[old]
            sessions[sid] = dict(pipeline=pipeline, touched=time.monotonic(), sequence=0,
                                 timestamp=-1., fingerprint=None, result=result, finished=False)
            return result

    @app.post("/sessions/{sid}/frames")
    async def frame(sid: str, sequence: int, timestamp: float, request: Request):
        if sequence < 1 or not math.isfinite(timestamp) or timestamp < 0:
            raise HTTPException(422, "invalid sequence or timestamp")
        if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
            raise HTTPException(415, "JPEG required")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_JPEG_BYTES:
                raise HTTPException(413, "frame too large")
        # Heavy inference stays off the ASGI event loop, serialized around shared ORT sessions.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(process, sid, sequence, timestamp, bytes(data))

    def process(sid, sequence, timestamp, data):
        with lock:
            state = get(sid)
            fingerprint = hashlib.sha256(data + repr(timestamp).encode()).hexdigest()
            if sequence == state["sequence"] and fingerprint == state["fingerprint"]:
                return state["result"]
            if sequence <= state["sequence"] or timestamp <= state["timestamp"]:
                raise HTTPException(409, "stale frame")
            if not data.startswith(b"\xff\xd8"):
                raise HTTPException(422, "invalid JPEG")
            pixels = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if pixels is None or min(pixels.shape[:2]) < 64 or max(pixels.shape[:2]) > 4096:
                raise HTTPException(422, "unsupported frame dimensions")
            if max(pixels.shape[:2]) > 960:
                scale = 960 / max(pixels.shape[:2])
                pixels = cv2.resize(pixels, (round(pixels.shape[1] * scale), round(pixels.shape[0] * scale)))
            pipeline = state["pipeline"]
            snap, points, scores = pipeline.process(pixels, timestamp)
            rendered = pipeline.draw(pixels, points, scores)
            encoded, jpeg = cv2.imencode(".jpg", rendered, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if not encoded:
                raise HTTPException(500, "frame encoding failed")
            result = packet(sid, pipeline, snap, sequence, base64.b64encode(jpeg).decode("ascii"))
            state.update(sequence=sequence, timestamp=timestamp, fingerprint=fingerprint, result=result)
            return result

    @app.post("/sessions/{sid}/control")
    def control(sid: str, body: Control):
        with lock:
            state = get(sid)
            pipeline = state["pipeline"]
            if body.command == "pause":
                pipeline.counter.set_paused(body.paused)
                pipeline.last_frame_time = None
            else:
                pipeline.reset_selection()
            result = packet(sid, pipeline, pipeline.counter.snapshot(), state["sequence"])
            state.update(fingerprint=None, result=result)
            return result

    @app.delete("/sessions/{sid}")
    def finish(sid: str):
        with lock:
            state = get(sid, allow_finished=True)
            state["finished"] = True
            state["result"] = dict(state["result"], jpeg_base64=None)
            return state["result"]

    return app


app = create_app()

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host=os.environ.get('HEALTHMON_POSE_BIND', "127.0.0.1"), port=18095, access_log=False)
