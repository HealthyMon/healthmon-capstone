"""Quest/state integration scenarios; no model, network or database access."""
import copy
import pytest
from src.character_lab_engine import fresh, execute
from src.character_lab_quests import daily_quest_id, mini_quest_id, catalog_candidate_to_payload
from src.persona_quests import catalog_by_id
from src.character_lab_models import PersonaResponder


def cmd(kind, ident, **payload):
    return {'kind': kind, 'event_id': ident, 'payload': payload}


def run(lab, *commands):
    return execute(lab, list(commands))['session']


def walk(lab, ident, amount, **kwargs):
    return run(lab, cmd('exercise', ident, exercise_type='walk', category='lower',
                       actual=amount, target=max(amount, 1), unit='step', **kwargs))


def finish(lab, qid, ident):
    commands = ([cmd('quest', ident+'-progress', quest_id=qid, action='progress')]
                if lab['quests'][qid]['status'] == 'accepted' else [])
    return execute(lab, commands+[cmd('quest', ident, quest_id=qid, action='complete')])


def test_daily_5999_is_not_completion_6000_completes_and_reward_is_once():
    lab = fresh()
    qid = daily_quest_id(lab['state']['virtual_test_date'])
    lab = run(lab, cmd('quest', 'accept-day', quest_id=qid, action='accept'))
    lab = walk(lab, 'walking-first', 5999)
    before = copy.deepcopy(lab)
    with pytest.raises(ValueError, match='Insufficient verified'):
        finish(lab, qid, 'premature')
    assert lab == before
    lab = walk(lab, 'unverified-last', 1, verification_status='user_reported')
    with pytest.raises(ValueError, match='Insufficient verified'):
        finish(lab, qid, 'still-premature')
    lab = walk(lab, 'verified-last', 1)
    result = finish(lab, qid, 'claim-day')
    assert result['session']['quests'][qid]['status'] == 'completed'
    assert result['session']['quests'][qid]['reward_paid']
    view = next(q for q in result['quests'] if q['quest_id'] == qid)
    assert view['progress']['verified_value'] == 6000
    assert view['reward']['paid']
    again = execute(result['session'], [cmd('quest', 'claim-day', quest_id=qid, action='complete')])
    assert again['after'] == result['after']
    with pytest.raises(ValueError, match='Invalid quest transition'):
        finish(again['session'], qid, 'claim-again-new-id')


def test_mini_100_and_daily_6000_have_separate_targets_and_verified_progress():
    lab = fresh()
    day = lab['state']['virtual_test_date']
    daily, mini = daily_quest_id(day), mini_quest_id('walk_100', day)
    payload = catalog_candidate_to_payload(catalog_by_id()['walk_100'], mini, day)
    lab = run(lab, cmd('quest', 'mini-create', **payload),
              cmd('quest', 'mini-accept', quest_id=mini, action='accept'),
              cmd('quest', 'daily-accept', quest_id=daily, action='accept'))
    lab = walk(lab, 'mini-99', 99, quest_id=mini)
    with pytest.raises(ValueError, match='Insufficient verified'):
        finish(lab, mini, 'mini-too-early')
    lab = walk(lab, 'mini-1', 1, quest_id=mini)
    result = finish(lab, mini, 'mini-finish')
    views = {q['quest_id']: q for q in result['quests']}
    assert views[mini]['status'] == 'completed'
    assert views[mini]['goal']['target'] == 100
    assert views[daily]['goal']['target'] == 6000
    assert views[daily]['progress']['verified_value'] == 100
    assert views[daily]['status'] == 'accepted' and not views[daily]['reward']['paid']


def test_daily_pre_acceptance_steps_count_but_new_day_starts_at_zero():
    lab = walk(fresh(), 'before-acceptance-steps', 6000)
    qid = daily_quest_id(lab['state']['virtual_test_date'])
    lab = run(lab, cmd('quest', 'late-accept', quest_id=qid, action='accept'))
    completed = finish(lab, qid, 'late-claim')['session']
    tomorrow = execute(completed, [cmd('time', 'tomorrow', days=1)])
    next_id = daily_quest_id(tomorrow['after']['virtual_test_date'])
    views = {q['quest_id']: q for q in tomorrow['quests']}
    assert views[qid]['status'] == 'completed'
    assert views[next_id]['status'] == 'created'
    assert views[next_id]['progress']['verified_value'] == 0
    assert not views[next_id]['reward']['paid']


def test_rejected_daily_does_not_regenerate_and_overdue_acceptance_fails_once():
    lab = fresh()
    qid = daily_quest_id(lab['state']['virtual_test_date'])
    rejected = run(lab, cmd('quest', 'reject-daily', quest_id=qid, action='reject'))
    repeated = run(rejected, cmd('quest_tick', 'refresh-daily'))
    assert repeated['quests'][qid]['status'] == 'rejected'
    assert len(repeated['quests']) == 1
    accepted = run(lab, cmd('quest', 'accept-daily', quest_id=qid, action='accept'))
    tomorrow = run(accepted, cmd('time', 'missed-day', days=1))
    assert tomorrow['quests'][qid]['status'] == 'failed'
    assert not tomorrow['quests'][qid]['reward_paid']
    assert tomorrow['budgets']['2026-10-05:mood:negative'] == 3
    unchanged = run(tomorrow, cmd('quest_tick', 'second-tick'))
    assert unchanged['state'] == tomorrow['state']


def test_failure_mood_cap_uses_new_date_and_unaccepted_daily_has_no_penalty():
    lab = fresh()
    commands = []
    for i in range(6):
        commands.extend([cmd('quest', 'create-'+str(i), quest_id='q'+str(i)),
                         cmd('quest', 'accept-'+str(i), quest_id='q'+str(i), action='accept')])
    lab = run(lab, *commands)
    next_day = run(lab, cmd('time', 'expire-six', days=1))
    assert next_day['state']['mood'] == -15
    assert next_day['budgets']['2026-10-05:mood:negative'] == 15
    assert '2026-10-04:mood:negative' not in next_day['budgets']
    default = run(fresh(), cmd('time', 'no-accepted-goal', days=1))
    assert default['state']['mood'] == 0


def test_current_state_responder_generates_once_and_marks_reused_comparison():
    from src.persona_runtime import PersonaRuntime, DEFAULT_GENERATION
    runtime = PersonaRuntime()
    calls = []
    original = runtime._one
    def tracked(*args):
        calls.append(True)
        return original(*args)
    runtime._one = tracked
    runtime._load = lambda: pytest.fail('CPU-only current-state check must not load Qwen')
    lab = fresh()
    result = PersonaResponder(runtime).compare(lab, lab['state'], lab['state'],
                '오늘 뭐 할까?', [], DEFAULT_GENERATION, 'dummy', 'casual')
    assert result['single_state'] and len(calls) == 1
    assert result['results'][0]['a']['output'] == result['results'][0]['b']['output']
    assert result['contexts']['a'] == result['contexts']['b']


def test_ten_week_sassy_history_fits_existing_local_inference_budget():
    from transformers import AutoTokenizer
    from src.character_lab_schema import ROOT
    from src.character_lab_presets import preview
    from src.character_lab_models import response_context
    from src.persona_runtime import persona_messages
    tokenizer = AutoTokenizer.from_pretrained(ROOT/'models/qwen3.5-9b', local_files_only=True)
    lab = preview('rough_language')['session']
    before = copy.deepcopy(lab)
    ctx = response_context(lab, lab['state'], '오늘 뭐 할까?', [], 'casual')
    prompt = persona_messages(ctx, '오늘 뭐 할까?')
    encoded = tokenizer.apply_chat_template(prompt, tokenize=True, enable_thinking=False,
                                           add_generation_prompt=True, return_dict=True)
    assert len(encoded['input_ids']) <= 4096
    assert ctx['expression_profile']['voice_id'] == 'sassy'
    assert ctx['event_projection']['shown_events'] <= 6
    assert lab == before
