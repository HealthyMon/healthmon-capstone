"""Public API acceptance tests, each against a fresh native PostgreSQL+pgvector DB.

The fixture explicitly creates a random healthmon_test_* database and never opens a
developer's existing DB. Watch/AI inputs here are labelled test fixtures, not device
measurements or real inference. Workers are disabled to keep clocks deterministic.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import psycopg
import pytest
from fastapi.testclient import TestClient

from Server.healthmon.app import create_app
from Server.healthmon import service


BASE = datetime(2026, 10, 22, 3, tzinfo=timezone.utc)


def clock(client, when):
    client.app.state.clock = lambda: when


def workout(ident="workout-fixture", when=None, **overrides):
    value = dict(event_id=ident, revision=1,
                 occurred_at=(when or BASE + timedelta(hours=1)).isoformat(),
                 started_at=(when or BASE + timedelta(hours=1)).isoformat(),
                 workout_type="run", actual=30, target=None, unit="minutes",
                 source="watch", synthetic=False)
    value.update(overrides)
    return value


def meal(ident="meal-fixture", when=None, **overrides):
    value = dict(event_id=ident, revision=1,
                 occurred_at=(when or BASE + timedelta(hours=1)).isoformat(),
                 source="user", food_name="확정 테스트 아침", meal_type="breakfast",
                 confirmed=True, quantity_confirmed=True, grams=300,
                 carbohydrate_g=55, protein_g=20, fat_g=12,
                 vegetable_fruit_g=80, kcal=408)
    value.update(overrides)
    return value


def post_workout(client, pet, value):
    response = client.post(f"/pets/{pet}/workouts", json=value)
    assert response.status_code == 200, response.text
    return response.json()


def rows(db, statement, params=()):
    with db.connect() as connection:
        return connection.execute(statement, params).fetchall()


def test_ready_identity_and_server_instance_survive_new_app(client, pet, db, settings):
    info = client.get("/server-info").json()
    assert info["environment"] == "test"
    assert client.get("/health/ready").json()["ready"] is True
    assert client.get("/identity").json()["owner_id"] == "owner-a"
    clock(client, BASE + timedelta(hours=2))
    first = post_workout(client, pet, workout())
    assert first["stored"] is True
    assert first["state"]["lower_body"] == 52
    reloaded_app = create_app(settings, db)
    reloaded_app.state.clock = lambda: BASE + timedelta(hours=2)
    with TestClient(reloaded_app) as reloaded:
        reloaded.headers["Authorization"] = "Bearer test-owner-a-token"
        assert reloaded.get("/server-info").json() == info
        assert reloaded.get(f"/pets/{pet}/state").json()["lower_body"] == 52
        assert len(reloaded.get(f"/pets/{pet}/workouts").json()["records"]) == 1


def test_concurrent_same_id_is_one_durable_event_and_one_reward(client, pet, db):
    clock(client, BASE + timedelta(hours=2))
    payload = workout("same-watch-id")
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.post(f"/pets/{pet}/workouts", json=payload), range(12)))
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    assert all(response.json()["state"]["lower_body"] == 52 for response in responses)
    assert len(rows(db,"SELECT * FROM sources WHERE pet_id=%s",(pet,))) == 1
    assert len(rows(db,"SELECT * FROM source_revisions WHERE pet_id=%s",(pet,))) == 1
    ledger = rows(db,"SELECT reward_key FROM game_ledger WHERE pet_id=%s",(pet,))
    assert len({item["reward_key"] for item in ledger}) == len(ledger)
    total = client.get(f"/pets/{pet}/state").json()["total_exp"]
    assert client.post(f"/pets/{pet}/workouts",json=payload).json()["state"]["total_exp"] == total


def test_same_id_different_contents_requires_sequential_revision(client, pet, db):
    clock(client, BASE + timedelta(hours=2))
    payload = workout()
    first = post_workout(client,pet,payload)
    conflict = client.post(f"/pets/{pet}/workouts",json={**payload,"actual":3})
    assert conflict.status_code == 409
    assert client.post(f"/pets/{pet}/workouts",json={**payload,"revision":3}).status_code == 409
    revised = post_workout(client,pet,{**payload,"revision":2,"actual":3})
    assert revised["state"]["lower_body"] == 49
    assert revised["state"]["total_exp"] >= first["state"]["total_exp"]
    assert revised["state"]["coin"] >= first["state"]["coin"]
    assert len(rows(db,"SELECT * FROM source_revisions WHERE pet_id=%s",(pet,))) == 2
    assert len(rows(db,"SELECT * FROM sources WHERE pet_id=%s",(pet,))) == 1
    assert client.post(f"/pets/{pet}/workouts",json={**payload,"revision":3,"actual":3,"occurred_at":(BASE+timedelta(minutes=61)).isoformat()}).status_code == 409


def test_goal_snapshot_uses_exercise_start_and_is_preserved(client, pet):
    clock(client,BASE+timedelta(minutes=10))
    goal = client.post(f"/pets/{pet}/goals",json={"exercise_type":"run","target":60,"unit":"minutes","body_part":"lower"})
    assert goal.status_code == 200,goal.text
    clock(client,BASE+timedelta(hours=2))
    first = post_workout(client,pet,workout("started-before-change",started_at=(BASE+timedelta(minutes=5)).isoformat()))
    assert first["state"]["lower_body"] == 52
    second = post_workout(client,pet,workout("started-after-change",started_at=(BASE+timedelta(minutes=20)).isoformat()))
    assert second["state"]["lower_body"] == 52  # 30/60=50% -> 0
    records = {item["event_id"]:item["record"] for item in client.get(f"/pets/{pet}/workouts").json()["records"]}
    assert records["started-before-change"]["goal_snapshot"]["target"] == 30
    assert records["started-after-change"]["goal_snapshot"]["target"] == 60
    rejected = client.post(f"/pets/{pet}/workouts",json=workout("invented-target",target=30))
    assert rejected.status_code == 409


@pytest.mark.parametrize("overrides",[
    {"actual":None,"workout_type":"squat","unit":"repetitions"},
    {"unit":None}, {"unit":"steps"},
    {"workout_type":"cycle"}, {"workout_type":"gymnastics"},
])
def test_incomplete_or_unsupported_workout_preserves_record_unscored(client,pet,overrides):
    clock(client,BASE+timedelta(hours=2))
    result = post_workout(client,pet,workout(**overrides))
    assert result["evaluation_status"] == "recorded_unscored"
    assert result["state"]["lower_body"] == 50
    record = client.get(f"/pets/{pet}/workouts").json()["records"][0]["record"]
    if overrides.get("actual",30) is None:
        assert record["actual"] is None
    if overrides.get("workout_type") in {"cycle","gymnastics"}:
        assert record["target"] is None


def test_zero_null_and_explicit_nonperformance_are_different(client,pet):
    clock(client,BASE+timedelta(hours=2))
    missing = post_workout(client,pet,workout("missing",actual=None))
    assert missing["evaluation_status"] == "recorded_unscored"
    zero = post_workout(client,pet,workout("measured-zero",actual=0))
    assert zero["evaluation_status"] == "evaluated"
    assert zero["state"]["lower_body"] == 50
    missed = post_workout(client,pet,workout("confirmed-missed",actual=0,source="user",confirmed_nonperformance=True))
    assert missed["state"]["lower_body"] == 48
    assert client.post(f"/pets/{pet}/workouts",json=workout("forged-confirmation",actual=0,confirmed_nonperformance=True)).status_code == 422


def test_net_daily_cap_and_concurrent_updates_do_not_lose_events(client,pet):
    clock(client,BASE+timedelta(hours=2))
    values = [workout("a",actual=36),workout("b",actual=36),workout("c",actual=3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda value:client.post(f"/pets/{pet}/workouts",json=value),reversed(values)))
    assert all(response.status_code==200 for response in responses)
    assert client.get(f"/pets/{pet}/state").json()["lower_body"] == 53
    assert len(client.get(f"/pets/{pet}/workouts").json()["records"]) == 3


def test_full_body_goal_distributes_one_event_without_double_awarding(client,pet,db):
    clock(client,BASE+timedelta(minutes=5))
    goal=client.post(f"/pets/{pet}/goals",json={"exercise_type":"full_body","target":30,"unit":"repetitions","body_part":"full"})
    assert goal.status_code==200,goal.text
    clock(client,BASE+timedelta(hours=2))
    state=post_workout(client,pet,workout("full-body-fixture",workout_type="full_body",actual=30,unit="repetitions"))["state"]
    assert (state["upper_body"],state["lower_body"])==(51,51)
    base=rows(db,"SELECT sum(exp) AS exp FROM game_ledger WHERE pet_id=%s AND reward_key NOT LIKE 'quest:%%'",(pet,))[0]
    assert base["exp"]==35


@pytest.mark.parametrize("body_part",["upper","full"])
def test_known_running_goal_cannot_change_its_rule_body_part(client,pet,body_part):
    goal=client.post(f"/pets/{pet}/goals",json={"exercise_type":"run","target":30,"unit":"minutes","body_part":body_part})
    assert goal.status_code==422,goal.text


@pytest.mark.parametrize("exercise",["cycle","stretch","gymnastics"])
def test_unapproved_exercises_stay_unscored_even_with_a_saved_goal(client,pet,exercise):
    clock(client,BASE+timedelta(minutes=5))
    goal=client.post(f"/pets/{pet}/goals",json={"exercise_type":exercise,"target":30,"unit":"minutes","body_part":"lower"})
    assert goal.status_code==200,goal.text
    clock(client,BASE+timedelta(hours=2))
    result=post_workout(client,pet,workout("unapproved-goal-fixture",workout_type=exercise))
    assert result["evaluation_status"]=="recorded_unscored"
    assert result["state"]["lower_body"]==50


def test_first_receipt_boundary_and_duplicate_do_not_change_eligibility(client,pet,db):
    occurred = BASE+timedelta(hours=1)
    clock(client,occurred+timedelta(hours=24))
    original = post_workout(client,pet,workout("within-24",when=occurred))
    assert original["evaluation_status"] == "evaluated"
    archived = post_workout(client,pet,workout("over-24",when=occurred-timedelta(microseconds=1)))
    assert archived["evaluation_status"] == "archive_only"
    received = rows(db,"SELECT received_at FROM sources WHERE pet_id=%s AND id='within-24'",(pet,))[0]["received_at"]
    clock(client,occurred+timedelta(days=4))
    duplicate = post_workout(client,pet,workout("within-24",when=occurred))
    assert duplicate["duplicate"] and duplicate["evaluation_status"] == "evaluated"
    assert duplicate["state"]["lower_body"] == 52
    assert rows(db,"SELECT received_at FROM sources WHERE pet_id=%s AND id='within-24'",(pet,))[0]["received_at"] == received
    assert client.post(f"/pets/{pet}/workouts",json=workout("within-24",when=occurred,revision=2,actual=20)).status_code == 409


def test_future_and_timezone_naive_events_are_rejected_without_storage(client,pet,db):
    assert client.post(f"/pets/{pet}/workouts",json=workout()).status_code == 422
    assert client.post(f"/pets/{pet}/workouts",json=workout(occurred_at="2026-10-22T02:00:00",started_at=None)).status_code == 422
    assert not rows(db,"SELECT * FROM sources WHERE pet_id=%s",(pet,))


def test_body_identity_claims_and_other_owner_access_are_blocked(client,pet):
    clock(client,BASE+timedelta(hours=2))
    for extra in ({"user_id":"owner-b"},{"verified":True},{"owner_id":"owner-a"}):
        assert client.post(f"/pets/{pet}/workouts",json=workout(**extra)).status_code == 422
    headers={"Authorization":"Bearer test-owner-b-token"}
    assert client.get(f"/pets/{pet}/state",headers=headers).status_code == 404
    assert client.get(f"/pets/{pet}/workouts",headers=headers).status_code == 404
    assert client.post(f"/pets/{pet}/workouts",json=workout(),headers=headers).status_code == 404
    assert client.get("/identity",headers={"Authorization":"Bearer invalid-fixture"}).status_code == 401


def test_event_state_rewards_and_revision_all_roll_back_together(client,pet,db,monkeypatch):
    clock(client,BASE+timedelta(hours=2))
    before = client.get(f"/pets/{pet}/state").json()
    old_refresh = service.refresh
    def fail_after_projection(*args,**kwargs):
        old_refresh(*args,**kwargs)
        raise psycopg.errors.CheckViolation("test fixture forced rollback after ledger/state writes")
    monkeypatch.setattr(service,"refresh",fail_after_projection)
    response=client.post(f"/pets/{pet}/workouts",json=workout("rollback-event"))
    assert response.status_code == 503,response.text
    monkeypatch.setattr(service,"refresh",old_refresh)
    assert not rows(db,"SELECT * FROM sources WHERE pet_id=%s",(pet,))
    assert not rows(db,"SELECT * FROM source_revisions WHERE pet_id=%s",(pet,))
    assert not rows(db,"SELECT * FROM game_ledger WHERE pet_id=%s",(pet,))
    after=client.get(f"/pets/{pet}/state").json()
    assert (after["lower_body"],after["total_exp"],after["state_version"]) == (before["lower_body"],before["total_exp"],before["state_version"])


def test_meal_confirmation_missing_values_and_constituent_bundle(client,pet,db):
    clock(client,BASE+timedelta(hours=2))
    pending=client.post(f"/pets/{pet}/meals",json=meal("unconfirmed",confirmed=False)).json()
    assert pending["state"]["nutrition"] == 50
    assert pending["state"]["total_exp"] == 0
    unknown=client.post(f"/pets/{pet}/meals",json=meal("unknown",meal_type="snack",quantity_confirmed=False,grams=None,carbohydrate_g=None,protein_g=None,fat_g=None,vegetable_fruit_g=None,kcal=None)).json()
    assert unknown["state"]["nutrition"] == 50
    assert unknown["state"]["energy_balance"] == 0
    for ident in ("constituent-a","constituent-b"):
        response=client.post(f"/pets/{pet}/meals",json=meal(ident,grams=150,carbohydrate_g=27.5,protein_g=10,fat_g=6,vegetable_fruit_g=40,kcal=204))
        assert response.status_code == 200,response.text
    state=client.get(f"/pets/{pet}/state").json()
    assert state["nutrition"] == 52
    assert state["energy_balance"] == 0
    record=rows(db,"SELECT payload FROM sources WHERE pet_id=%s AND id='unknown'",(pet,))[0]["payload"]["data"]
    assert record["protein_g"] is None
    # Several constituents/unknown record of one breakfast must never create three meals.
    daily=rows(db,"SELECT summary FROM game_daily WHERE pet_id=%s",(pet,))[0]["summary"]
    assert daily["confirmed_meal_count"] == 1
    awarded=rows(db,"SELECT sum(exp) AS exp FROM game_ledger WHERE pet_id=%s AND reason='confirmed_meal_record'",(pet,))
    assert awarded[0]["exp"] == 15


def test_synthetic_scope_and_ai_disabled_leave_workout_available(client,pet,settings):
    clock(client,BASE+timedelta(hours=2))
    assert client.post(f"/pets/{pet}/chat",json={"request_id":"disabled-chat","text":"fixture"}).status_code == 503
    assert post_workout(client,pet,workout())["state"]["lower_body"] == 52
    settings.test_owners=frozenset()
    assert client.post(f"/pets/{pet}/workouts",json=workout("synthetic-denied",synthetic=True)).status_code == 403
    settings.ai_mode="mock"
    assert client.post(f"/pets/{pet}/chat",json={"request_id":"non-test-chat","text":"fixture"}).status_code == 503


def test_mock_chat_idempotence_state_context_and_vector_memory(client,pet,settings,db):
    settings.ai_mode="mock"
    clock(client,BASE+timedelta(hours=2))
    run=post_workout(client,pet,workout())
    request={"request_id":"mock-chat-fixture","text":"기억용 합성 테스트 문장","state_version":run["state_version"]}
    response=client.post(f"/pets/{pet}/chat",json=request)
    assert response.status_code==200,response.text
    chat=response.json()
    assert chat["provenance"]=="synthetic"
    assert chat["state_used"]["lower_body"]==52
    assert all(axis in chat["state_used"] for axis in ("activity","affinity","initiative"))
    assert client.post(f"/pets/{pet}/chat",json=request).json()==chat
    assert client.post(f"/pets/{pet}/chat",json={**request,"text":"different fixture"}).status_code==409
    source="message:"+request["request_id"]
    memory=client.post(f"/pets/{pet}/memories",json={"source_id":source,"revision":1,"slot":"experience"})
    assert memory.status_code==200,memory.text
    found=client.get(f"/pets/{pet}/memories",params={"query":"합성 테스트"})
    assert found.status_code==200,found.text
    assert found.json()["memories"][0]["source_id"]==source
    assert rows(db,"SELECT vector_dims(embedding) AS n,synthetic,embedding_model FROM memories WHERE pet_id=%s",(pet,))[0]=={"n":1024,"synthetic":True,"embedding_model":"mock.embedding:1:1024"}


def test_state_poll_and_workout_upload_do_not_cancel_inflight_chat(client,pet,settings,monkeypatch):
    settings.ai_mode="mock"
    clock(client,BASE+timedelta(hours=2))
    entered,release=Event(),Event()
    old_call=client.app.state.gateway.call
    def delayed(capability,*args,**kwargs):
        if capability=="chat":
            entered.set()
            assert release.wait(10),"test chat was never released"
        return old_call(capability,*args,**kwargs)
    monkeypatch.setattr(client.app.state.gateway,"call",delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f"/pets/{pet}/chat",json={"request_id":"pending-chat-fixture","text":"진행 중 합성 대화"})
        try:
            assert entered.wait(5)
            assert client.get(f"/pets/{pet}/state").status_code==200
            assert post_workout(client,pet,workout("during-chat"))["state"]["lower_body"]==52
        finally:
            release.set()
        response=pending.result(timeout=10)
    assert response.status_code==200,response.text
    assert response.json()["state_after"]["lower_body"]==52


def test_sessions_require_explicit_reopen_after_expiry(client,pet):
    body={"session_id":"session-fixture","active":True}
    assert client.post(f"/pets/{pet}/chat-session/heartbeat",json=body).status_code==409
    assert client.post(f"/pets/{pet}/chat-session",json=body).status_code==200
    assert client.post(f"/pets/{pet}/chat-session/heartbeat",json=body).status_code==200
    clock(client,BASE+timedelta(minutes=6))
    assert client.post(f"/pets/{pet}/chat-session/heartbeat",json=body).status_code==409
    assert client.post(f"/pets/{pet}/chat-session",json=body).status_code==200
    assert client.post(f"/pets/{pet}/chat-session",json={**body,"active":False}).status_code==200
    assert client.post(f"/pets/{pet}/chat-session/heartbeat",json=body).status_code==409


@pytest.mark.parametrize("mode,ready",[("disabled",False),("mock",True)])
def test_chat_session_ready_contract_is_explicit_for_ai_mode(client,pet,settings,mode,ready):
    settings.ai_mode=mode
    body={"session_id":"session-ready-fixture","active":True}
    response=client.post(f"/pets/{pet}/chat-session",json=body)
    assert response.status_code==200,response.text
    opened=response.json()
    assert opened["active"] is True
    assert opened["ready"] is ready
    assert opened["ai_mode"]==mode
    assert opened["local_model_loaded"] is False
    closed=client.post(f"/pets/{pet}/chat-session",json={**body,"active":False})
    assert closed.status_code==200,closed.text
    assert closed.json()["active"] is False
    assert closed.json()["ready"] is False


def test_food_analysis_confirm_duplicate_and_deleted_source_do_not_resurrect(client,pet,settings):
    settings.ai_mode="mock"
    clock(client,BASE+timedelta(hours=2))
    image=b"\x89PNG\r\n\x1a\nsynthetic-contract-image-fixture"
    headers={"X-Request-Id":"food-analysis-fixture","Content-Type":"image/png"}
    analyzed=client.post(f"/pets/{pet}/food/analyze",content=image,headers=headers)
    assert analyzed.status_code==200,analyzed.text
    assert analyzed.json()["synthetic"] is True
    assert client.get(f"/pets/{pet}/state").json()["total_exp"]==0
    assert client.post(f"/pets/{pet}/food/analyze",content=image,headers=headers).json()==analyzed.json()
    assert client.post(f"/pets/{pet}/food/analyze",content=image+b"changed",headers=headers).status_code==409
    body={"analysis_id":analyzed.json()["analysis_id"],"candidate_id":0,"grams":100,"meal_type":"breakfast","vegetable_fruit_g":80}
    confirmed=client.post(f"/pets/{pet}/food/confirm",json=body)
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()["stored"] is True
    repeated=client.post(f"/pets/{pet}/food/confirm",json=body)
    assert repeated.status_code==200 and repeated.json()["duplicate"] is True
    deleted=client.delete(f"/pets/{pet}/sources/{confirmed.json()['source_id']}",params={"expected_revision":1})
    assert deleted.status_code==200,deleted.text
    assert client.post(f"/pets/{pet}/food/confirm",json=body).status_code in (409,410)


def test_source_privacy_deletion_recomputes_only_stats_and_invalidates_memory(client,pet,settings,db):
    settings.ai_mode="mock"
    clock(client,BASE+timedelta(hours=2))
    before=post_workout(client,pet,workout("delete-workout"))["state"]
    assert client.delete(f"/pets/{pet}/sources/delete-workout",params={"expected_revision":1},headers={"Authorization":"Bearer test-owner-b-token"}).status_code==404
    assert client.delete(f"/pets/{pet}/sources/delete-workout",params={"expected_revision":99}).status_code==409
    deleted=client.delete(f"/pets/{pet}/sources/delete-workout",params={"expected_revision":1})
    assert deleted.status_code==200,deleted.text
    after=client.get(f"/pets/{pet}/state").json()
    assert after["lower_body"]==50
    assert after["total_exp"]>=before["total_exp"]
    assert after["coin"]>=before["coin"]
    assert client.get(f"/pets/{pet}/workouts").json()["records"]==[]
    assert client.post(f"/pets/{pet}/workouts",json=workout("delete-workout")).status_code==410
    chat_body={"request_id":"delete-memory-fixture","text":"삭제되어야 할 합성 문장"}
    assert client.post(f"/pets/{pet}/chat",json=chat_body).status_code==200
    source="message:"+chat_body["request_id"]
    assert client.post(f"/pets/{pet}/memories",json={"source_id":source,"revision":1,"slot":"experience"}).status_code==200
    assert client.delete(f"/pets/{pet}/sources/{source}",params={"expected_revision":1}).status_code==200
    assert client.get(f"/pets/{pet}/memories",params={"query":"합성"}).json()["memories"]==[]
    assert client.post(f"/pets/{pet}/chat",json=chat_body).status_code==410
    assert not rows(db,"SELECT * FROM memories WHERE pet_id=%s AND valid",(pet,))


def test_base_exp_daily_ninety_cap_and_quest_ledger_are_independent(client,pet,settings,db):
    settings.ai_mode="mock"
    clock(client,BASE+timedelta(hours=2))
    post_workout(client,pet,workout("base-exp-run"))
    for slot in ("breakfast","lunch","dinner","snack"):
        response=client.post(f"/pets/{pet}/meals",json=meal("base-exp-"+slot,meal_type=slot))
        assert response.status_code==200,response.text
    assert client.post(f"/pets/{pet}/chat",json={"request_id":"base-exp-chat-fixture","text":"합성 정상 대화"}).status_code==200
    base=rows(db,"SELECT sum(exp) AS exp,sum(coin) AS coin FROM game_ledger WHERE pet_id=%s AND reward_key NOT LIKE 'quest:%%'",(pet,))[0]
    assert base=={"exp":90,"coin":0}
    state=client.get(f"/pets/{pet}/state").json()
    ledger=rows(db,"SELECT sum(exp) AS exp,sum(coin) AS coin FROM game_ledger WHERE pet_id=%s",(pet,))[0]
    assert state["total_exp"]==ledger["exp"]
    assert state["coin"]==ledger["coin"]
    before=len(rows(db,"SELECT * FROM game_ledger WHERE pet_id=%s",(pet,)))
    for _ in range(3):
        client.get(f"/pets/{pet}/quests")
        client.get(f"/pets/{pet}/state")
    assert len(rows(db,"SELECT * FROM game_ledger WHERE pet_id=%s",(pet,)))==before


def test_privacy_delete_after_score_window_preserves_scored_growth(client,pet,db):
    clock(client,BASE+timedelta(hours=2))
    initial=post_workout(client,pet,workout("late-delete-workout"))["state"]
    assert initial["lower_body"]==52
    clock(client,BASE+timedelta(hours=27))
    response=client.delete(f"/pets/{pet}/sources/late-delete-workout",params={"expected_revision":1})
    assert response.status_code==200,response.text
    state=client.get(f"/pets/{pet}/state").json()
    assert state["lower_body"]==52
    assert state["total_exp"]>=initial["total_exp"]
    assert client.get(f"/pets/{pet}/workouts").json()["records"]==[]
    payload=rows(db,"SELECT payload,valid FROM sources WHERE pet_id=%s AND id='late-delete-workout'",(pet,))[0]
    assert payload["valid"] is False
    def has_key(value,key):
        if isinstance(value,dict):
            return key in value or any(has_key(item,key) for item in value.values())
        if isinstance(value,list):
            return any(has_key(item,key) for item in value)
        return False
    assert not has_key(payload["payload"],"actual")
    assert not rows(db,"SELECT raw_payload FROM source_revisions WHERE pet_id=%s AND source_id='late-delete-workout' AND raw_payload ? 'actual'",(pet,))


def test_monday_catchup_and_delayed_sunday_replace_week_once(client,db):
    monday=datetime(2026,10,19,3,tzinfo=timezone.utc)
    clock(client,monday)
    created=client.post("/pets",json={"name":"주간 합성 테스트"})
    assert created.status_code==200,created.text
    pet=created.json()["pet_id"]
    for offset in (0,1):
        end=monday+timedelta(days=offset,hours=1)
        clock(client,end+timedelta(minutes=1))
        post_workout(client,pet,workout("week-"+str(offset),when=end))
    # No background worker ran: the next state read must catch up a missed Monday.
    next_monday=datetime(2026,10,26,3,tzinfo=timezone.utc)
    clock(client,next_monday)
    assert client.get(f"/pets/{pet}/state").json()["activity"]==50  # two actual workout days
    sunday_end=datetime(2026,10,25,14,tzinfo=timezone.utc)  # Sunday 23:00 KST
    late=post_workout(client,pet,workout("late-sunday",when=sunday_end))
    assert late["evaluation_status"]=="evaluated"
    assert late["state"]["activity"]==51  # replace 0 with +1; do not add the week twice
    for _ in range(3):
        assert client.get(f"/pets/{pet}/state").json()["activity"]==51
    summaries=rows(db,"SELECT summary FROM game_weekly WHERE pet_id=%s AND week_start='2026-10-19'",(pet,))
    assert len(summaries)==1
    assert summaries[0]["summary"]["summary"]["workout_days"]==3
