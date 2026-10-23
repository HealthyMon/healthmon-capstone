"""Independent regression checks for Persona Lab review findings.

All model results here are injected fixtures, never actual Qwen evaluations.
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.contracts import Action, ModelOutput
from src.persona_engine import replay_events
from src.persona_lab import create_app
from src.persona_runtime import DEFAULT_GENERATION, PersonaRuntime, prepare_context
from src.persona_store import LabStore


START = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
ORIGIN = "http://127.0.0.1:8001"
HEADERS = {"Origin": ORIGIN, "X-Persona-Lab": "1"}


def event(identifier, kind, at, **payload):
    return {"event_id": identifier, "idempotency_key": identifier,
            "user_id": "persona-lab", "character_id": "lab-preview",
            "event_type": kind, "occurred_at": at.isoformat(), "source": "simulation",
            "verification_status": "verified", "confidence": 1.0, "payload": payload}


def test_prompt_retains_verified_activity_and_current_accepted_quest():
    events = [event("accept", "quest_accepted", START, quest_id="walk_500", quest_instance_id="accepted-walk"),
              event("record", "exercise_recorded", START + timedelta(minutes=1), exercise_type="walk", steps=200)]
    now = START + timedelta(minutes=2)
    state = replay_events(events, now)
    context = prepare_context(state, events, now, "지금 진행 중인 퀘스트와 걸음 기록을 알려줘.")
    assert context["activities"], "Verified records were dropped from the prompt"
    assert "200" in json.dumps(context["activities"], ensure_ascii=False)
    assert any(q.get("quest_id", q.get("id")) == "walk_500" for q in context["active_quests"]), "Accepted quest was dropped from the prompt"


def test_history_projection_sorts_actual_instants_across_timezones():
    accepted = datetime.fromisoformat("2026-10-02T00:00:00+09:00")
    recorded = datetime.fromisoformat("2026-10-01T15:01:00+00:00")
    completed = datetime.fromisoformat("2026-10-01T15:02:00+00:00")
    rows = [event("accept", "quest_accepted", accepted, quest_id="walk_100", quest_instance_id="attempt"),
            event("walk", "exercise_recorded", recorded, exercise_type="walk", steps=100),
            event("done", "quest_completed", completed, quest_id="walk_100", quest_instance_id="attempt", evidence_event_ids=["walk"])]
    state = replay_events(rows, completed)
    assert any(a["status"] == "completed" for a in state["event_audit"])
    context = prepare_context(state, rows, completed, "내 퀘스트 상태는?")
    assert not context["active_quests"], "A completed attempt must not be resurrected by ISO string sorting"


def test_preview_can_use_each_selected_day_as_its_own_reference_time(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PERSONA_LAB_ENABLED", "1")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    runtime = PersonaRuntime()
    monkeypatch.setattr(runtime, "_load", lambda: pytest.fail("Dummy review must not load Qwen"))
    application = create_app(runtime, LabStore(tmp_path / "isolated.sqlite3"))
    now_a = START + timedelta(days=1)
    now_b = START + timedelta(days=10)
    with TestClient(application, base_url=ORIGIN, client=("127.0.0.1", 30000)) as client:
        response = client.post("/api/preview", headers=HEADERS,
                               json={"mode": "dummy", "now_a": now_a.isoformat(), "now_b": now_b.isoformat()})
    assert response.status_code == 200, response.text
    result = response.json()
    assert datetime.fromisoformat(result["contexts"]["a"]["as_of"]) == now_a
    assert datetime.fromisoformat(result["contexts"]["b"]["as_of"]) == now_b


def test_unknown_food_group_does_not_earn_known_group_novelty():
    row = event("food", "food_recorded", START, food_name="검증된 새 음식", food_group="unknown")
    state = replay_events([row], START)
    assert state["personality"]["curiosity"] == pytest.approx(50.2)
    assert not any(r["reason_code"] == "new_food_group" for r in state["ledger"])


def test_fallback_is_labeled_as_fallback_not_model_speech(monkeypatch):
    # Prevent importing heavyweight libraries; the injected responder does not
    # execute the nested generator and no model call takes place in this test.
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(set_seed=lambda _: None))
    fallback = ModelOutput(speech="잠깐 말이 꼬였어.", emotion="neutral", animation="idle", action=Action(), memory_ids=[])
    import src.persona_runtime
    monkeypatch.setattr(src.persona_runtime, "respond", lambda *args: (fallback, {"fallback": True, "attempts": 1}))
    result = PersonaRuntime()._one({}, "안녕", DEFAULT_GENERATION, "qwen")
    assert result.get("output_origin") == "fallback"


def test_failed_batch_rolls_back_earlier_inserts(tmp_path):
    store = LabStore(tmp_path / "isolated.sqlite3")
    initial = dict.fromkeys(("curiosity", "affection", "activity", "confidence"), 50)
    short = {"mood": "neutral", "energy": 60, "recent_motivation": 50, "recent_stress": 0}
    character = store.create(initial, short)
    original = event("existing", "exercise_recorded", START, exercise_type="walk", steps=100)
    store.append(character, [original], START)
    new = event("should-rollback", "exercise_recorded", START + timedelta(minutes=1), exercise_type="walk", steps=200)
    conflict = copy.deepcopy(original)
    conflict["payload"]["steps"] = 999
    with pytest.raises(ValueError, match="Conflicting"):
        store.append(character, [new, conflict], START + timedelta(minutes=2))
    assert [row["event_id"] for row in store.read(character)["events"]] == ["existing"]
