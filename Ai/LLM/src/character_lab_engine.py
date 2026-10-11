"""Pure sandbox backend rules. No LLM or production DB connection exists here."""
import copy
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from .character_lab_schema import CharacterState, Session, Command, Quest, RULES
from .character_lab_quests import sync_quests, verified_progress, quest_view, validate_generated_quest_payload


def fresh(state=None):
    state = CharacterState.model_validate(state or {}).model_dump(mode='json')
    lab = Session(state=state, initial_date=state['virtual_test_date']).model_dump(mode='json')
    lab['quest_audit'].extend(sync_quests(lab, state['virtual_test_date']))
    return lab


def evolution(state):
    cfg = RULES['evolution']
    stage = max(state['evolution_stage'], sum(state['level'] >= x for x in cfg['levels']))
    upper, lower = state['upper_body'], state['lower_body']
    exercise_type = ('balanced' if min(upper, lower) >= cfg['strong'] and abs(upper-lower) < cfg['asymmetry']
                     else 'upper' if upper-lower >= cfg['asymmetry'] and upper >= cfg['strong']
                     else 'lower' if lower-upper >= cfg['asymmetry'] and lower >= cfg['strong'] else 'ordinary')
    condition = ('fat_gain' if state['energy_balance'] >= cfg['fat_energy']
                 else 'underfed' if state['energy_balance'] <= cfg['low_energy']
                 else 'healthy' if state['nutrition'] >= cfg['healthy_nutrition'] else 'ordinary')
    body = ('initial' if not stage else condition if condition in ('fat_gain', 'underfed')
            else exercise_type + '_exercise' if exercise_type != 'ordinary' else 'ordinary')
    previous = state['previous_evolution']
    if (stage > previous.get('evolution_stage', state['evolution_stage'])
            and previous.get('final_body_type', state['body_type']) == 'fat_gain'
            and body in cfg['recovered_body_types'] and condition == 'healthy'):
        body = 'recovered'
    if (state['body_type'] == 'recovered' and stage == state['evolution_stage']
            and condition == 'healthy' and body in cfg['recovered_body_types']):
        body = 'recovered'
    return {'evolution_stage': stage, 'exercise_type': exercise_type, 'body_condition': condition,
            'final_body_type': body,
            'generation_required': stage != state['evolution_stage'] or body != state['body_type'],
            'applied_rule': 'provisional:evolution', 'rule_version': RULES['version'],
            'reason': f"level={state['level']}; upper={upper}, lower={lower}, nutrition={state['nutrition']}, energy={state['energy_balance']}",
            'provisional': True}


def execute(session, commands, dry_run=True):
    lab = Session.model_validate(session).model_dump(mode='json')
    batch_before = copy.deepcopy(lab['state'])
    results = []
    for raw in commands:
        cmd = Command.model_validate(raw).model_dump(mode='json')
        fingerprint_input = copy.deepcopy(cmd)
        for field in ('model_identifier', 'prompt_version'):
            if fingerprint_input['payload'].get(field) is None:
                fingerprint_input['payload'].pop(field, None)
        fingerprint = hashlib.sha256(json.dumps(fingerprint_input, sort_keys=True).encode()).hexdigest()
        ident = cmd['event_id']
        if ident in lab['processed']:
            if lab['processed'][ident] != fingerprint:
                raise ValueError('Conflicting event_id; entire batch rolled back')
            results.append({'event_id': ident, 'duplicate': True})
            continue
        s, p, kind = lab['state'], cmd['payload'], cmd['kind']
        before = copy.deepcopy(s)
        day = p.get('date') or s['virtual_test_date']
        if day > s['virtual_test_date']:
            raise ValueError('Future input: advance virtual time first')
        # Retroactive records make weekly/window caps ambiguous. Replay presets in date order.
        if day != s['virtual_test_date']:
            raise ValueError('Record date must equal virtual_test_date; use a fresh chronological session')
        detail = {'review_required': False}
        reasons = []

        def change(axis, delta, rule, cap=None, budget_day=None):
            if cap:
                key = f'{budget_day or day}:{axis}:{"positive" if delta >= 0 else "negative"}'
                used = lab['budgets'].get(key, 0)
                bounded = (min(delta, max(0, cap-used)) if delta >= 0 else -min(-delta, max(0, cap-used)))
                lab['budgets'][key] = used + abs(bounded)
                detail['daily_cap_applied'] = detail.get('daily_cap_applied', False) or bounded != delta
                delta = bounded
            old = s[axis]
            lo, hi = RULES['ranges'][axis]
            s[axis] = round(min(hi, max(lo, old + delta)), 6)
            reasons.append({'axis': axis, 'before': old, 'after': s[axis], 'delta': s[axis]-old, 'applied_rule': rule})

        def mood(effect, budget_day=None):
            delta = RULES['mood']['effects'][effect]
            change('mood', delta, 'mood:' + effect,
                   RULES['mood']['daily_positive' if delta >= 0 else 'daily_negative'], budget_day)

        def exp(amount, rule):
            change('exp', amount, rule)
            requirement = RULES['exp']['required_per_level']
            while s['level'] < RULES['ranges']['level'][1] and s['exp'] >= requirement*s['level']:
                old_exp, old_level = s['exp'], s['level']
                s['exp'] -= requirement*s['level']
                s['level'] += 1
                reasons.extend([{'axis': 'exp', 'before': old_exp, 'after': s['exp'], 'applied_rule': 'provisional:level_exp_cost'},
                                {'axis': 'level', 'before': old_level, 'after': s['level'], 'applied_rule': 'provisional:level_up'}])
            stage = max(s['evolution_stage'], sum(s['level'] >= x for x in RULES['evolution']['levels']))
            s['growth_stage'] = 'initial' if not stage else f'evolution_{stage}'
            if stage > s['evolution_stage']:
                result = evolution(s)
                s['previous_evolution'] = {'evolution_stage': s['evolution_stage'], 'final_body_type': s['body_type']}
                s['evolution_stage'], s['body_type'] = result['evolution_stage'], result['final_body_type']
                detail['evolution'] = result

        def sync_date(on_date):
            lifecycle = sync_quests(lab, on_date)
            lab['quest_audit'].extend(lifecycle)
            for audit in lifecycle:
                auto_before = copy.deepcopy(s)
                if audit['after_status'] == 'failed':
                    mood('quest_failed', budget_day=on_date)
                q = audit['quest']
                payload = {k: v for k, v in q.items() if k in Quest.model_fields}
                payload['action'] = audit['action']
                auto_id = 'auto:'+hashlib.sha256(audit['quest_id'].encode()).hexdigest()[:32]+':'+audit['action']
                auto_cmd = Command(kind='quest', event_id=auto_id, payload=payload).model_dump(mode='json')
                auto_detail = {'quest': copy.deepcopy(q), 'lifecycle': audit,
                               'reward_paid': q['reward_paid'], 'review_required': False}
                auto_log = {'event_id': auto_id, 'source_event': auto_cmd, 'kind': 'quest',
                            'before': auto_before, 'after': copy.deepcopy(s),
                            'applied_rules': [audit], 'reason': audit['reason'],
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'virtual_test_date': on_date, 'result_virtual_date': on_date,
                            'dry_run': dry_run, 'rule_version': RULES['version'],
                            'synthetic': True, 'result': auto_detail}
                lab['logs'].append(auto_log)
                lab['events'].append({'event_id': auto_id, 'kind': 'quest',
                                      'payload': auto_cmd['payload'], 'virtual_test_date': on_date,
                                      'result': auto_detail})
                lab['processed'][auto_id] = hashlib.sha256(json.dumps(auto_cmd, sort_keys=True).encode()).hexdigest()
                results.append(auto_log)
            detail.setdefault('quest_lifecycle', []).extend(lifecycle)

        if kind == 'manual_override':
            new = p['state']
            new['level'] = max(s['level'], new['level'])
            s.update(new)
            sync_date(s['virtual_test_date'])
            reasons.append({'applied_rule': 'manual_override', 'reason': 'Explicit synthetic state edit; level never decreases'})
        elif kind == 'exercise':
            rate = p['actual']/p['target']*100
            detail['achievement_rate'] = rate
            q = lab['quests'].get(p['quest_id']) if p['quest_id'] else None
            if p['quest_id'] and (q is None or q['status'] not in ('accepted', 'in_progress')):
                raise ValueError('Exercise quest must be an accepted, active test quest')
            if q and (q['quest_type'] != 'exercise' or q['target'] != p['exercise_type'] or q['unit'] != p['unit']):
                raise ValueError('Record does not match linked quest type/target/unit')
            eligible_missed = ((p['explicit_goal'] and p['due_date'] and p['due_date'] < day)
                               or (q and q['due_date'] < day))
            if p['verification_status'] != 'verified':
                delta = 0
                detail['review_required'] = True
            elif not p['actual']:
                delta = RULES['exercise']['missed'] if eligible_missed else 0
            else:
                delta = next(v for threshold, v in RULES['exercise']['thresholds'] if rate >= threshold)
            axes = ['upper_body'] if p['category'] == 'upper' else ['lower_body'] if p['category'] == 'lower' else ['upper_body', 'lower_body']
            for axis in axes:
                change(axis, delta/len(axes), f"exercise:achievement {rate:g}%" if p['actual'] else 'exercise:expired_goal_only',
                       RULES['exercise']['daily_positive' if delta >= 0 else 'daily_negative'])
                if p['actual'] > 0 and p['verification_status'] == 'verified':
                    s['last_upper_exercise' if axis == 'upper_body' else 'last_lower_exercise'] = day
            detail['verified_behavior'] = p['verification_status'] == 'verified' and p['actual'] > 0
            if p['verification_status'] == 'verified' and (p['actual'] > 0 or eligible_missed):
                mood('exercise_exceeded' if rate >= 120 else 'exercise_success' if rate >= 100 else 'exercise_shortfall')
            if detail['verified_behavior']:
                exp(RULES['exp']['exercise_record'], 'provisional:exercise_record_exp')
        elif kind == 'food':
            analysis = p['analysis']
            fields = ('protein', 'carbohydrate', 'fat', 'vegetable', 'amount')
            detail.update({'analysis_original': p['raw_text'], 'model_prediction': p['model_prediction'],
                           'corrected_result': analysis, 'analysis_confidence': analysis['analysis_confidence']})
            if any(analysis[k] == 'unknown' for k in fields):
                detail['review_required'] = True
                reasons.append({'applied_rule': 'food:unknown_requires_review', 'reason': 'No automatic Nutrition/EnergyBalance change'})
            else:
                deviations = sum(analysis[k] != 'proper' for k in fields)
                detail['deviation_count'] = deviations
                change('nutrition', RULES['food']['deviation_delta'][deviations], f'provisional:food_deviations_{deviations}')
                energy_cfg = RULES['food']['extreme_energy' if p['amount_severity'] == 'extreme' else 'energy']
                change('energy_balance', energy_cfg[analysis['amount']], 'provisional:food_amount_' + analysis['amount'])
                exp(RULES['exp']['food_record'], 'provisional:food_record_exp')
        elif kind == 'conversation':
            a = p['analysis']
            trusted = a['analysis_confidence'] >= RULES['weekly']['minimum_analysis_confidence']
            # Reject cross-target affection even when a model incorrectly predicts it.
            relation = a['target'] == 'character' and a['character_affection'] != 'neutral'
            detail.update({'long_term_eligible': trusted, 'relation_eligible': trusted and relation,
                           'analysis_confidence': a['analysis_confidence'], 'review_required': not trusted})
            if a['target'] != 'character' and a['character_affection'] != 'neutral':
                detail['review_required'] = True
                reasons.append({'applied_rule': 'conversation:cross_target_affection_ignored'})
            if trusted:
                if relation:
                    mood('character_positive' if a['character_affection'] == 'positive' else 'character_negative')
                elif a['motivation'] == 'low':
                    mood('low_motivation')
                elif a['target'] in ('exercise', 'food', 'quest') and a['sentiment'] == 'positive':
                    mood('activity_positive')
            key = day + ':conversation_exp'
            remaining = max(0, RULES['exp']['daily_conversation_cap'] - lab['budgets'].get(key, 0))
            reward = min(remaining, RULES['exp']['conversation'])
            lab['budgets'][key] = lab['budgets'].get(key, 0) + reward
            exp(reward, 'provisional:conversation_daily_exp')
        elif kind == 'quest':
            qid, action = p['quest_id'], p['action']
            q = lab['quests'].get(qid)
            if action == 'create':
                validate_generated_quest_payload(p)
                if q:
                    raise ValueError('Quest ID already exists')
                start, due = p['start_date'] or day, p['due_date'] or day
                if due < start or start < day:
                    raise ValueError('Quest dates must be ordered and start on/after virtual date')
                if ((p['quest_type'] == 'exercise' and p['verification_method'] == 'food_record') or
                        (p['quest_type'] == 'food' and p['verification_method'] == 'exercise_record')):
                    raise ValueError('Quest verification method does not match quest type')
                q = dict(p, start_date=start, due_date=due, status='created', created_date=day,
                         progress_value=0, reward_paid=False, accepted_date=None, resolved_date=None,
                         accepted_event_index=None)
                lab['quests'][qid] = q
            else:
                if not q:
                    raise ValueError('Unknown test quest')
                transitions = {'accept': {'created'}, 'reject': {'created'}, 'progress': {'accepted', 'in_progress'},
                               'complete': {'in_progress'}, 'fail': {'accepted', 'in_progress'},
                               'expire': {'created'}}
                if q['status'] not in transitions[action]:
                    raise ValueError(f"Invalid quest transition {q['status']} -> {action}")
                if action == 'accept' and not q['start_date'] <= day <= q['due_date']:
                    raise ValueError('Accept within quest dates only')
                if action in ('progress', 'complete'):
                    fraction = p['progress'] if action == 'progress' else 1
                    if fraction <= q['progress_value']:
                        raise ValueError('Progress must increase')
                    if q.get('quest_scope') in ('daily', 'mini'):
                        total = verified_progress(lab, q)
                        detail['verified_total'] = total
                        evidence_ok = total >= q['target_value']*fraction
                        evidence = [x for x in lab['events'] if x['kind'] == 'food'
                                    and not x['result'].get('review_required')
                                    and not x['result'].get('quest_evidence_used')
                                    and q['accepted_date'] <= x['virtual_test_date'] <= day]
                    elif q['verification_method'] == 'admin_verified':
                        evidence_ok = p['admin_verified']
                        detail['evidence_origin'] = 'explicit_synthetic_admin_verification'
                    else:
                        evidence = [x for x in lab['events'][q['accepted_event_index']+1:]
                                    if x['payload'].get('quest_id') == qid or
                                    (q['quest_type'] == 'food' and x['kind'] == 'food')]
                        if q['verification_method'] == 'exercise_record':
                            total = sum(x['payload']['actual'] for x in evidence if x['kind'] == 'exercise'
                                        and x['payload']['verification_status'] == 'verified'
                                        and x['payload']['exercise_type'] == q['target'] and x['payload']['unit'] == q['unit'])
                        else:
                            total = sum(x['kind'] == 'food' and not x['result'].get('review_required') for x in evidence
                                        if q['accepted_date'] <= x['virtual_test_date'] <= day
                                        and not x['result'].get('quest_evidence_used'))
                        evidence_ok = total >= q['target_value']*fraction
                        detail['verified_total'] = total
                    if not evidence_ok:
                        raise ValueError('Insufficient verified synthetic evidence; user acceptance is not completion')
                    if day > q['due_date']:
                        raise ValueError('Cannot complete/progress after due date')
                    q['progress_value'] = fraction
                if action == 'expire' and day <= q['due_date']:
                    raise ValueError('Cannot expire before due date passes')
                q['status'] = {'accept': 'accepted', 'reject': 'rejected', 'progress': 'in_progress',
                               'complete': 'completed', 'fail': 'failed', 'expire': 'expired'}[action]
                if action == 'accept':
                    q['accepted_date'], q['accepted_event_index'] = day, len(lab['events'])
                if action in ('reject', 'complete', 'fail', 'expire'):
                    q['resolved_date'] = day
                if action == 'complete' and not q['reward_paid']:
                    exp(q['reward_exp'], 'quest:reward_once')
                    mood('quest_completed')
                    q['reward_paid'] = True
                    if q['verification_method'] == 'food_record':
                        for x in evidence:
                            if x['kind'] == 'food':
                                x['result']['quest_evidence_used'] = qid
                if action == 'fail':
                    mood('quest_failed')
            detail.update({'quest': copy.deepcopy(q), 'reward_paid': q['reward_paid'],
                           'activity_event': q['status'] == 'completed' and q['quest_type'] == 'exercise',
                           'initiative_event': q['character_proposal'] and q['status'] in ('completed', 'failed', 'rejected')})
            reasons.append({'applied_rule': 'quest:validated_' + action})
        elif kind == 'quest_tick':
            sync_date(s['virtual_test_date'])
            reasons.append({'applied_rule': 'quest:daily_tick'})
        elif kind == 'time':
            action = p['action']

            def decay(on_date):
                if on_date in lab['decay_dates']:
                    return
                old = s['mood']
                new = old * RULES['mood']['decay']
                if abs(new) < RULES['mood']['zero_epsilon']:
                    new = 0
                change('mood', new-old, 'provisional:mood_daily_decay')
                lab['decay_dates'].append(on_date)

            def weekly():
                end = date.fromisoformat(s['virtual_test_date']) - timedelta(days=1)
                start = end - timedelta(days=RULES['weekly']['window_days']-1)
                if start < date.fromisoformat(lab['initial_date']):
                    raise ValueError('A complete seven-day period is required before weekly update')
                key = f'{start}/{end}'
                if any(start <= date.fromisoformat(w.split('/')[1]) and end >= date.fromisoformat(w.split('/')[0]) for w in lab['weeks']):
                    detail['weekly_duplicate_or_overlap'] = True
                    return
                cfg = RULES['weekly']
                events = [x for x in lab['events'] if start.isoformat() <= x['virtual_test_date'] <= end.isoformat()]
                exercises = [x for x in events if x['kind'] == 'exercise' and x['result']['verified_behavior']]
                conversations = [x for x in events if x['kind'] == 'conversation' and x['result']['long_term_eligible']]
                days = len({x['virtual_test_date'] for x in exercises})
                # Average daily total actual/target, so duplicate records cannot manufacture active days.
                rates = [sum(x['payload']['actual'] for x in exercises if x['virtual_test_date'] == d)/
                         sum(x['payload']['target'] for x in exercises if x['virtual_test_date'] == d)*100
                         for d in {x['virtual_test_date'] for x in exercises}]
                avg = sum(rates)/len(rates) if rates else 0
                low = sum(x['payload']['analysis']['motivation'] == 'low' for x in conversations)
                delta = next((delta for n, rate, delta in cfg['activity_thresholds'] if days >= n and avg >= rate),
                             cfg['inactive_low_motivation_delta'] if days <= cfg['inactive_days'] and low >= cfg['repeated_count']
                             else cfg['inactive_delta'] if days <= cfg['inactive_days'] else 0)
                change('activity', delta, f'weekly:verified_exercise_days={days}; average={avg:g}%')
                relations = [x for x in conversations if x['result']['relation_eligible']]
                negative = sum(x['payload']['analysis']['character_affection'] == 'negative' for x in relations)
                positive = sum(x['payload']['analysis']['character_affection'] == 'positive' for x in relations)
                chat_days = len({x['virtual_test_date'] for x in conversations})
                delta = (cfg['affinity_negative_delta'] if negative >= cfg['repeated_count'] else
                         cfg['affinity_daily_positive_delta'] if chat_days >= cfg['almost_daily'] and positive >= cfg['repeated_count'] else
                         next(d for n, d in cfg['affinity_day_thresholds'] if chat_days >= n))
                change('affection', delta, f'weekly:conversation_days={chat_days}; positive={positive}; character_negative={negative}')
                proposals = [q for q in lab['quests'].values() if q['character_proposal'] and
                             start.isoformat() <= q['created_date'] <= end.isoformat() and q['resolved_date'] and
                             q['resolved_date'] <= end.isoformat()]
                ratio = sum(q['status'] == 'completed' and q['accepted_date'] is not None for q in proposals)/len(proposals) if proposals else None
                if ratio is not None:
                    change('initiative', next(d for threshold, d in cfg['initiative_thresholds'] if ratio >= threshold),
                           f'weekly:accepted_and_completed/proposals={ratio:g}')
                else:
                    reasons.append({'applied_rule': 'weekly:initiative_zero_denominator', 'reason': 'Initiative unchanged'})
                detail['weekly'] = {'period': key, 'exercise_days': days, 'average_achievement': avg,
                                    'conversation_days': chat_days, 'proposal_count': len(proposals), 'performed_ratio': ratio}
                from .character_lab_personality import expression_weekly
                expression = expression_weekly(events, s)
                for axis, delta in expression['deltas'].items():
                    change(axis, delta, 'provisional:weekly_expression_'+axis)
                detail['expression_update'] = expression
                lab['weeks'].append(key)

            if action in ('advance', 'all_weekly'):
                sync_date(s['virtual_test_date'])
                for _ in range(p['days']):
                    s['virtual_test_date'] = (date.fromisoformat(s['virtual_test_date'])+timedelta(days=1)).isoformat()
                    decay(s['virtual_test_date'])
                    sync_date(s['virtual_test_date'])
                if action == 'all_weekly':
                    weekly()
            elif action == 'decay':
                decay(s['virtual_test_date'])
            elif action == 'weekly':
                weekly()
            else:
                s['virtual_test_date'] = lab['initial_date']
                reasons.append({'applied_rule': 'time:restore_initial_date', 'reason': 'Budgets/idempotency preserved; reset session for a fresh history'})
        elif kind == 'evolution':
            detail['evolution'] = evolution(s)
            if p['apply'] and detail['evolution']['generation_required']:
                result = detail['evolution']
                s['previous_evolution'] = {'evolution_stage': s['evolution_stage'], 'final_body_type': s['body_type']}
                s['evolution_stage'], s['body_type'] = result['evolution_stage'], result['final_body_type']
                s['growth_stage'] = 'initial' if not s['evolution_stage'] else f"evolution_{s['evolution_stage']}"
            reasons.append({'applied_rule': 'provisional:evolution'})
        lab['state'] = CharacterState.model_validate(s).model_dump(mode='json')
        log = {'event_id': ident, 'source_event': copy.deepcopy(cmd), 'kind': kind,
               'before': before, 'after': copy.deepcopy(lab['state']), 'applied_rules': reasons,
               'reason': '; '.join(x.get('reason', x['applied_rule']) for x in reasons),
               'timestamp': datetime.now(timezone.utc).isoformat(), 'virtual_test_date': day,
               'result_virtual_date': lab['state']['virtual_test_date'], 'dry_run': dry_run,
               'rule_version': RULES['version'], 'synthetic': True, 'result': detail}
        if kind in ('conversation', 'food'):
            log.update(model_identifier=p['model_identifier'], prompt_version=p['prompt_version'])
        lab['logs'].append(log)
        lab['events'].append({'event_id': ident, 'kind': kind, 'payload': copy.deepcopy(p),
                              'virtual_test_date': day, 'result': detail})
        lab['processed'][ident] = fingerprint
        results.append(log)
    Session.model_validate(lab)
    return {'session': lab, 'before': batch_before, 'after': lab['state'], 'results': results,
            'target': 'synthetic preview', 'dry_run': dry_run, 'production_write': False,
            'rule_version': RULES['version'], 'evolution': evolution(lab['state']), 'quests': quest_view(lab)}
