"""V2 continuous Lucan design compiler. No GPU, asset selection or fabricated history.

All coefficients are explicit game-art heuristics, not medical measurements.
Mood lives outside the persistent body recipe and its cache key.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

VERSION = 'individual-v2.11-grounded-wholeform'
ROOT = Path(__file__).resolve().parents[2]
LEVELS = (0, 15, 30, 50)
FIELDS = ('UpperBody','LowerBody','Nutrition','EnergyBalance','Activity','Affinity','Initiative','Mood')
BODY_FIELDS = FIELDS[:-1]
DIET_FIELDS = ('protein_g','carbohydrate_g','fat_g','vegetable_servings','meal_kcal')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name}: finite number in [{low}, {high}] required')
    return float(value)


def scores(values):
    if not isinstance(values, dict): raise ValueError('stats must be an object')
    missing = set(FIELDS)-values.keys()
    if missing: raise ValueError(f'Missing stats: {sorted(missing)}')
    return {k:number(values[k], k, -1 if k=='EnergyBalance' else 0, 1 if k=='EnergyBalance' else 100) for k in FIELDS}


def stage_for_level(level):
    level = number(level, 'level', 0, 100)
    return sum(level >= threshold for threshold in LEVELS[1:])


def diet_record(value):
    if value is None: return None
    if not isinstance(value, dict) or set(value)-set(DIET_FIELDS): raise ValueError('Unknown diet fields or units')
    limits = (1000, 2000, 1000, 30, 15000)
    return {k:number(value[k], k, 0, limit) for k,limit in zip(DIET_FIELDS,limits) if k in value}


def history_summary(profile, current):
    records = profile.get('history', [])
    if not isinstance(records,list) or len(records)>3650: raise ValueError('history must be an ordered array, at most 3650 records')
    rows=[]
    for r in records:
        if not isinstance(r,dict): raise ValueError('Invalid history record')
        s=scores(r['stats']); days=number(r['days'],'days',.01,3650)
        rows.append(dict(stats=s,days=days,diet=diet_record(r.get('diet'))))
    total=sum(r['days'] for r in rows)
    if total>36500: raise ValueError('History exceeds 100 years')
    mean={k:sum(r['stats'][k]*r['days'] for r in rows)/total for k in BODY_FIELDS} if total else {k:current[k] for k in BODY_FIELDS}
    # Strength of memory grows smoothly with available evidence, never creates days.
    memory=.65*(1-math.exp(-total/28))
    effective={k:(1-memory)*current[k]+memory*mean[k] for k in BODY_FIELDS}
    trend={k:(rows[-1]['stats'][k]-rows[0]['stats'][k])/100 if len(rows)>1 else 0 for k in ('UpperBody','LowerBody','Activity')}
    peak={k:max([current[k]]+[r['stats'][k] for r in rows]) for k in ('UpperBody','LowerBody')}
    diets=[(r['diet'],r['days']) for r in rows if r['diet']]
    if profile.get('diet') is not None: diets.append((diet_record(profile['diet']),1))
    diet={k:sum(d[k]*w for d,w in diets if k in d)/sum(w for d,w in diets if k in d) for k in DIET_FIELDS if any(k in d for d,w in diets)}
    origin=profile.get('history_origin','unspecified' if rows else 'missing')
    if origin not in ('missing','synthetic_test','user_supplied','unspecified'): raise ValueError('Invalid history_origin')
    if rows and origin=='missing': raise ValueError('History supplied but marked missing')
    return dict(available=bool(rows), origin=origin, days=total, record_count=len(rows), mean=mean, effective=effective,
                trend=trend, peak=peak, memory_weight=memory, diet=diet or None,
                records=rows, chronological_order='oldest_to_newest',
                limitation=None if rows else 'No historical records; current snapshot only. No duration inferred.')


def reference_principles():
    """Only abstract processes enter prompts; franchise names/art do not."""
    path=ROOT/'records/v2/reference_analysis.json'
    if path.exists():
        data=json.loads(path.read_text())
        signature=dict(version=data['version'],principles=data['principles'],
                       chains=[r['chain_sha256'] for r in data['lineages']],
                       art=[r['sha256'] for r in data['licensed_art']])
        return dict(version=data['version'],principles=data['principles'],source_manifest_sha256=digest(signature))
    return dict(version='builtin-processes-v1',principles=[
        'Retain palette and thematic motifs while freely reorganizing the entire anatomy.',
        'Redistribute mass, negative space, support and locomotion as one coherent organism.',
        'Enclosure, release, orientation reversal and motif repurposing are processes, not fixed final forms.',
        'Branches may have different body plans. Do not copy an existing franchise character.'])


def compile_individual(profile, species_contract=None, *, game_contract='legacy'):
    species = profile.get('species')
    if species_contract is None and species != 'lucan':
        raise ValueError('A species contract is required outside the legacy Lucan lineage')
    if species_contract is not None:
        from .species_contract import validate_contract
        species_contract = validate_contract(species_contract, species)
    version = VERSION if species_contract is None else 'individual-v2.12-species-contracts'
    v22 = game_contract == 'healthmon.v2.2'
    if game_contract not in ('legacy', 'healthmon.v2.2'):
        raise ValueError('Unsupported game contract')
    if v22:
        # Mood has never entered the persistent body recipe. Do not invent one
        # merely to satisfy the old expression-only channel's required field.
        if set(profile['stats']) != set(BODY_FIELDS) or profile.get('history'):
            raise ValueError('v2.2 requires exactly seven observed body/personality axes and no fabricated history')
        current={k:number(profile['stats'][k], k, -1 if k=='EnergyBalance' else 0, 1 if k=='EnergyBalance' else 100) for k in BODY_FIELDS}
        version = 'individual-common-v2.2-no-expression'
    else:
        current=scores(profile['stats'])
    level=number(profile['level'],'level',0,100)
    if v22:
        if type(profile['level']) is not int:
            raise ValueError('v2.2 level must be an authoritative integer')
        source=profile['source_stage']
        if isinstance(source,bool) or not isinstance(source,int) or not 0 <= source <= 3:
            raise ValueError('A verified source stage is required')
        target=sum(level >= threshold for threshold in (10,20,30))
        if profile.get('target_stage') != target:
            raise ValueError('v2.2 target stage must match authoritative level 10/20/30')
    else:
        previous=number(profile['previous_level'],'previous_level',0,100)
        source=stage_for_level(previous); target=stage_for_level(level)
        if level<previous: raise ValueError('Level cannot go backwards')
    if target==source: return None
    if target!=source+1: raise ValueError('Generate each crossed stage sequentially; stage skipping is forbidden')
    seed=profile.get('seed',42)
    if isinstance(seed,bool) or not isinstance(seed,int) or not 0<=seed<2**63: raise ValueError('Invalid seed')
    h=history_summary(profile,current); e=h['effective']
    u,l,n,a,f,i=(e[k]/100 for k in ('UpperBody','LowerBody','Nutrition','Activity','Affinity','Initiative'))
    energy=e['EnergyBalance']; diet=h['diet'] or {}
    protein_support=0
    if all(k in diet for k in ('protein_g','carbohydrate_g','fat_g')):
        kcal=4*(diet['protein_g']+diet['carbohydrate_g'])+9*diet['fat_g']
        protein_support=4*diet['protein_g']/kcal-.2 if kcal else 0
    # Condition is a separate channel; low activity never automatically means fat.
    adiposity=max(0,min(1,.28+.65*energy))
    condition=dict(adiposity=round(adiposity,6),energy_balance=energy,
                   exercise_development=round((u+l)/2,6),nutrition_support=n,
                   dietary_protein_evidence=protein_support,
                   role='physical condition informs, but does not select, the evolved body plan')
    # Every value describes the WHOLE organism. No dimensions are limb measurements,
    # no thresholds select anatomy, and no finished-form library is consulted.
    d=dict(
        adiposity=adiposity,
        kinetic_flow=.35*a+.25*l+.20*i+.20*(1-adiposity),
        support_distribution=.5+.28*(u-l)*(.5+.5*a)+.12*(f-i),
        spatial_spread=.22+.22*a+.18*i+.16*(1-adiposity)+.12*(u+l)/2,
        visual_density=.18+.26*adiposity+.20*(u+l)/2+.18*(1-a)+.12*n,
        social_openness=.15+.40*f+.20*n+.15*(1-i),
        self_direction=.15+.35*i+.25*a+.15*(1-f),
        surface_integration=.20+.40*n+.20*f+.10*protein_support,
        developmental_momentum=.5+.15*h['trend']['UpperBody']+.15*h['trend']['LowerBody']+.10*h['trend']['Activity'],
        structural_persistence=.20+.30*h['memory_weight']+.20*(u+l)/2+.15*n,
        contrast_rhythm=.20+.25*abs(u-l)+.20*i+.20*(1-f),
        coiled_to_expansive=.15+.25*a+.20*l+.20*i+.10*(1-f),
        overall_presence=.12+.22*(u+l)/2+.18*n+.18*i+.12*((energy+1)/2)+.18*h['memory_weight'],
    )
    d={k:round(max(0,min(1,v)),6) for k,v in d.items()}
    tendencies={k:d[k] for k in ('kinetic_flow','support_distribution','spatial_spread','visual_density',
                  'social_openness','self_direction','developmental_momentum','contrast_rhythm','coiled_to_expansive')}
    raw=hashlib.sha256(f'{species}-individual-v1:{seed}'.encode()).digest()
    variation={k:round(int.from_bytes(raw[j*4:j*4+4],'big')/(2**32-1),6)
               for j,k in enumerate(('contour_rhythm','symmetry_play','motif_migration','negative_space','movement_invention','surface_rhythm'))}
    process_weights={
        'orientation_reinvention':.25+.25*i+.20*(1-f)+.15*abs(u-l)+.15*variation['movement_invention'],
        'enclosure_and_release':.20+.25*(1-a)+.20*n+.15*adiposity+.20*variation['negative_space'],
        'mass_redistribution':.15+.35*abs(u-l)+.20*(u+l)/2+.15*i+.15*variation['contour_rhythm'],
        'rhythmic_repetition':.15+.30*a+.20*l+.15*n+.20*variation['surface_rhythm'],
        'motif_repurposing':.20+.25*f+.20*n+.15*h['memory_weight']+.20*variation['motif_migration'],
        'locomotor_metamorphosis':.15+.30*a+.20*l+.20*(1-u)+.15*variation['movement_invention'],
        'negative_space_composition':.15+.25*(1-adiposity)+.20*i+.20*(1-f)+.20*variation['negative_space'],
    }
    process_weights={k:round(v,6) for k,v in process_weights.items()}
    stage_contract={
        1:'First transition: leave the infant form behind and establish a fresh stylized fantasy creature silhouette. Invent an acquired thunder-related visual structure that can be transformed at later stages. Preserve recognizable lineage, not realistic mammalian anatomy.',
        2:'Second transition: substantially redesign the whole-body mass organization, organizing axis, proportions and structural silhouette. The descendant may be compact or immense, graceful or monumental, mythical rather than zoologically realistic. If a final bipedal transition develops, provide preparatory balance in pelvis, hindquarters and tail here. These are possibilities, not mandatory destinations.',
        3:'Third transition: resolve the individual lineage into a distinctive mature mythical creature. A quadruped MAY become a biped at this final stage when its previous balance structures develop accordingly. Quadrupedal, elongated or other coherent fantastical organizations remain possible. Colossal scale and presence are allowed; never force humanoid warriors or repeat a larger realistic wolf.'}[target]
    if species_contract is not None:
        stage_contract = species_contract['stage_directions'][str(target)]
    principles=reference_principles()
    effective_level=profile['level'] if v22 else LEVELS[target]
    intent=dict(version=version,species=species,source_stage=source,target_stage=target,level=effective_level,seed=seed,
                current={k:current[k] for k in BODY_FIELDS},history={k:v for k,v in h.items() if k!='records'},
                history_records=[dict(r,stats={k:v for k,v in r['stats'].items() if k!='Mood'}) for r in h['records']],
                dimensions=d,tendencies=tendencies,condition=condition,individual_variation=variation,process_weights=process_weights,
                transformation_reference=principles,structural_brief=stage_contract)
    if v22:
        intent['authoritative_game_profile'] = profile['authoritative_game_profile']
        intent['game_rule_version'] = 'healthmon.v2.2'
    prompt=('Create a newly invented evolved Lucan from the full combined design state below. '
            'The previous image supplies lineage identity, not target proportions. Preserve selected charcoal/ivory/gold '
            'and thunder motifs while freely redesigning the entire mythical body, scale, structural rhythm and locomotion. '
            'Natural anatomy is not mandatory; fantasy anatomy must read as a deliberate connected design. Final-stage bipedal evolution is optional when prepared by previous-stage balance. '
            'Do not reduce the outcome to a realistic animal, automatic armored humanoid, muscular warrior or weight-only edit. '
            'Use a calm expression; mood is a separate runtime channel.\n'+json.dumps(intent,ensure_ascii=False,sort_keys=True))
    if species_contract is not None:
        intent['species_contract'] = species_contract
        prompt = ('Design one newly evolved individual of the explicitly registered species. '
                  'Use the actual previous image and its declared lineage anchors. '
                  'Preserve the family identity while reorganizing coherent whole-body shapes for this stage. '
                  'Mood controls expression only. Full combined design state:\n'
                  + json.dumps(intent, ensure_ascii=False, sort_keys=True))
    recipe={**intent,'prompt':prompt}
    body_key=digest(recipe)
    expression = None
    if not v22:
        mood=current['Mood'];expression=dict(mood=mood,smile=(mood-50)/50,ear_tilt=(mood-50)/250,
        implementation='expression_parameters_only',body_regeneration_required=False,
        note_ko='표정용 값만 갱신합니다. 현재 GLB에는 표정 블렌드셰이프가 없어 자동 표정 변형은 아직 적용하지 않습니다.')
    return dict(version=version,body_key=body_key,expression_key=None if v22 else digest([body_key,expression]),recipe=recipe,
                expression=expression,history=h,dimensions=d,tendencies=tendencies,condition=condition,
                individual_variation=variation,prompt=prompt,
                transition=dict(source_stage=source,target_stage=target,level=effective_level),stats=current,seed=seed,
                visual_quality='REQUIRES_REVIEW',explanations_ko=[
                    f'활동·하체·주도성·에너지를 함께 해석한 운동 흐름 {d["kinetic_flow"]:.3f}',
                    f'상하체 균형·활동·친화성·주도성 → 몸 전체의 지지 분포 {d["support_distribution"]:.3f}; 팔다리 크기를 직접 지정하지 않음',
                    f'복합 수치 → 공간 확장 {d["spatial_spread"]:.3f}, 시각 밀도 {d["visual_density"]:.3f}, 형태 리듬 {d["contrast_rhythm"]:.3f}',
                    f'친화성·영양·주도성 → 관계 표현 {d["social_openness"]:.3f}; 활동·독립성·주도성 → 자기 방향성 {d["self_direction"]:.3f}',
                    f'신체 상태 채널: 지방 지수 {adiposity:.3f}; 낮은 활동성 자체로 비만을 만들지 않음',
                    f'관측 이력 {h["days"]:g}일 ({h["origin"]}), 개체 시드 {seed}; '+('v2.2는 Mood를 만들지 않고 표정 채널을 평가하지 않음' if v22 else 'Mood는 표정 채널만 갱신'),
                    '몸 구조와 이동 방식을 Qwen이 새로 설계합니다. 수치 지수의 연속성이 이미지의 연속성을 보장하지는 않습니다.'],
                exp_policy=('Authoritative v2.2 server Level preserved; the generator does not recompute EXP.' if v22 else 'No EXP conversion exists in the inspected release; accept authoritative current Level. Do not invent EXP.'))


AXIS_SOURCES={
    'kinetic_flow':['Activity','LowerBody','Initiative','EnergyBalance'],
    'support_distribution':['UpperBody','LowerBody','Activity','Affinity','Initiative'],
    'spatial_spread':['Activity','Initiative','EnergyBalance','UpperBody','LowerBody'],
    'visual_density':['EnergyBalance','UpperBody','LowerBody','Activity','Nutrition'],
    'social_openness':['Affinity','Nutrition','Initiative'],
    'self_direction':['Initiative','Activity','Affinity'],
    'surface_integration':['Nutrition','Affinity','diet'],
    'developmental_momentum':['history'],
    'structural_persistence':['history','UpperBody','LowerBody','Nutrition'],
    'contrast_rhythm':['UpperBody','LowerBody','Initiative','Affinity'],
    'coiled_to_expansive':['Activity','LowerBody','Initiative','Affinity'],
    'overall_presence':['UpperBody','LowerBody','Nutrition','Initiative','EnergyBalance','history'],
}


def design_planning_request(compiled):
    """Ask the installed Qwen3-VL head to invent anatomy, not choose a body preset."""
    r=compiled['recipe']
    if r.get('species_contract') is not None:
        from .species_contract import planning_request
        return planning_request(compiled, AXIS_SOURCES)
    # Physical condition remains recorded, but does not dominate the art director.
    state={k:v for k,v in r.items() if k not in ('prompt','history_records','condition','dimensions','current','history','tendencies')}
    state['whole_form_axes']={k:v for k,v in r['dimensions'].items() if k!='adiposity'}
    state['physical_condition']=dict(reserve_density=r['condition']['adiposity'],exercise_development=r['condition']['exercise_development'],food_support=r['condition']['nutrition_support'],
        role='Secondary whole-body physical nuance; reserves are not magical power. Never select the final anatomy from these alone.')
    state['condition_role']='Secondary physical nuance only; first invent the entire evolved form from all persistent attributes.'
    state['visual_principles']=[
        'A small ancestor may become a monumental mythical presence through a new distribution of whole-body masses, not a swollen belly.',
        'Identity can survive a change of organizing axis and anatomy through graphic motifs, color relationships and thematic continuity.',
        'Use broad designed volumes, intentional negative space and few iconic shapes; intricate realistic fur obscures silhouette.',
        'Fantasy form is allowed, including integrated supernatural structures; acquired motifs should explain new structures visually, never random accessories.']
    return dict(version='lucan-generative-director-v7-grounded',seed=r['seed'],
        grounding=dict(current=r['current'],history=r['history'],axis_sources=AXIS_SOURCES),system=(
        'You are the art director of a stylized monster-raising fantasy game. Invent ONE original evolved creature from the combined evidence. '
        'Return ONLY valid JSON with keys design_thesis_ko (one concise Korean sentence), reasoning (three entries), structural_changes (three English phrases), lineage_anchors (two English phrases), image_prompt (130-170 English words). '
        'Each reasoning entry has source_axes (two or more exact names from whole_form_axes), decision_ko and form_why_ko (concise Korean sentences about the chosen shapes). '
        'Raw numeric interpretation and historical evidence are calculated by code and attached separately. You receive coupled WHOLE-FORM coordinates, not anatomical measurements. Do not make factual claims about exercise, diet, calories or unobserved history. Explain only how your proposed shapes express the supplied axes. '
        'First decide ONE coherent main identity and explain WHY the input mixture supports its mass arrangement, movement and overall impression. Then create the image prompt from that plan. '
        'Different mixtures should produce different overall feelings and organizing structures, not a single body with many accessories. Do not default to long-necked thunder dragons for every mixture. '
        'An evolution may look gentle, awkward, quirky, imposing, ungainly, elegant or formidable. Do not make every result majestic, ornate or aggressively cool. '
        'Start with a distinctive WHOLE-BODY silhouette and organizing structure, then describe locomotion, scale and presence. '
        'Read ALL physical, behavioral and historical inputs together. Lean, fat, muscular and reserve-carrying bodies are valid when supported by exercise, food and energy evidence; Activity alone never determines fatness. Body condition participates in a new whole form, not a weight edit. '
        'Invent three coordinated structural transformations: a new distribution of main body volumes, a new relation of head/trunk/support, and a transformed inherited thunder motif that participates in the silhouette. '
        'The creature can become a powerful mythical being, including immense forms. Natural mammalian anatomy, paws, bilateral symmetry, fixed appendage counts, all-over fur and a realistic animal silhouette are NOT requirements. '
        'A quadruped may remain quadrupedal with a completely new design; at the FINAL evolution it may become bipedal when connected to previous balance structures. Never force a default humanoid warrior. '
        'The form must be appealing, intentional, connected and legible as one creature. Fantasy locomotion is allowed; avoid random grotesque protrusions and unexplained aquatic paddles. '
        'Scale ranges from compact to colossal, guided by overall_presence and the full condition mixture, not a template or single threshold. '
        'kinetic_flow and coiled_to_expansive influence the entire movement rhythm; support_distribution places the center of visual gravity, never sizes an isolated limb. '
        'social_openness, self_direction and spatial_spread influence open/contained forms and negative space across the whole organism. '
        'History and persistent seed influence structural rhythm and motif migration. Abstract process weights are soft priorities, never finished-form IDs. '
        'Retain TWO Lucan identity anchors from charcoal/ivory/gold relationships, amber eyes, lightning brow or branching thunder motif. Transform face, ears, coat, limbs and tail as needed. '
        'No ordinary photoreal wolf or cat with decorative stripes. No named franchise character, copied silhouette, clothing, props, weapons or letters. '
        'Art style: iconic stylized animation creature, bold graphic color blocks, smooth simplified sculpted surfaces, clean expressive shapes, cel-shaded game concept. No realistic fur strands, wildlife photography, anatomical realism or grim horror. '
        'Full body in central sixty percent, all structures inside frame, wide white margins, plain white background.'),
        user=json.dumps(state,ensure_ascii=False,sort_keys=True),
        inference=dict(do_sample=True,temperature=.7,top_p=.9,repetition_penalty=1.05,max_new_tokens=1100))


def ground_design_concept(raw,request):
    """Validate the proposed rationale and attach exact supplied evidence, never invented values."""
    value=raw.strip()
    if value.startswith('```'):
        value=value.split('\n',1)[1].rsplit('```',1)[0].strip()
    concept=json.loads(value)
    required={'design_thesis_ko','reasoning','structural_changes','lineage_anchors','image_prompt'}
    if not isinstance(concept,dict) or not required<=set(concept):raise ValueError('Missing structured design fields')
    state=json.loads(request['user']);grounding=request['grounding'];used=set()
    if len(concept['reasoning'])!=3:raise ValueError('Expected three coupled design reasons')
    for reason in concept['reasoning']:
        axes=reason.get('source_axes',[])
        if len(set(axes))<2 or set(axes)-set(state['whole_form_axes']):raise ValueError('Design reason must use known coupled whole-form axes')
        fields=set(field for axis in axes for field in AXIS_SOURCES[axis])
        if len(fields&set(BODY_FIELDS))<2:raise ValueError('Design reason must combine persistent attributes')
        evidence={}
        for field in fields:
            if field=='history':
                evidence[field]={k:grounding['history'][k] for k in ('available','origin','days','mean','trend')}
            elif field=='diet':
                evidence[field]=grounding['history']['diet']
            else:
                evidence[field]=dict(current=grounding['current'][field],effective=grounding['history']['effective'][field])
        interpretation=reason.get('form_why_ko') or reason.get('why_ko')
        if not isinstance(reason.get('decision_ko'),str) or not isinstance(interpretation,str) or not interpretation.strip():raise ValueError('Missing design reasoning')
        reason['form_why_ko']=interpretation
        reason['source_fields']=[k for k in BODY_FIELDS if k in fields]
        reason['supplied_axes']={axis:state['whole_form_axes'][axis] for axis in axes}
        reason['supplied_evidence']=evidence
        labels=dict(UpperBody='상체',LowerBody='하체',Nutrition='식생활',EnergyBalance='열량 균형',Activity='활동',Affinity='친화',Initiative='주도')
        facts=[]
        for field in reason['source_fields']:
            v=grounding['history']['effective'][field]
            if field=='EnergyBalance':facts.append('열량 '+('유지' if v==0 else ('잉여' if v>0 else '부족'))+f'({v:+.3f})')
            else:facts.append(f'{labels[field]} {v:.1f}/100')
        reason['why_ko']='이력 반영 통합값: '+', '.join(facts)+'. 복합 지수 '+', '.join(f'{axis}={state["whole_form_axes"][axis]:.3f}' for axis in axes)+'로 계산했습니다.'
        reason['evidence_origin']='Deterministic compiler and declared dependency graph; model text is a separate artistic interpretation'
        used.update(fields)
    if not set(BODY_FIELDS)<=used:raise ValueError('Design rationale omitted persistent attributes')
    if len(concept['structural_changes'])<3 or len(concept['lineage_anchors'])<2:raise ValueError('Insufficient structural changes or lineage anchors')
    if not isinstance(concept['image_prompt'],str) or not 80<len(concept['image_prompt'])<7000:raise ValueError('Invalid image prompt')
    concept['rationale_kind']='Artistic hypothesis from supplied game data, not proof that the generated image follows it'
    return concept


def infer_design_brief(pipe,request,path,implementation,visual_references=None):
    """Recorded local language inference; reuses this model's existing vision encoder."""
    import torch
    import time
    from PIL import Image
    paths=[Path(p) for p in (visual_references or [])]
    refs=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    key=digest(dict(request=request,implementation=implementation,visual_references=refs))
    if path.exists():
        previous=json.loads(path.read_text())
        if previous.get('key')!=key or previous.get('prompt_sha256')!=hashlib.sha256(previous['prompt'].encode()).hexdigest():
            raise ValueError('Design-planner cache changed; use a new generation key')
        return previous['prompt']
    images=[]
    for p in paths:
        with Image.open(p) as im:
            image=im.convert('RGB');image.thumbnail((512,512));images.append(image)
    started=time.monotonic()
    perception=None
    if images:
        perception_system=('Read this actual previous creature and extract only heritable visual signatures for a designer. '
            'Write 30 to 50 English words describing ONLY visible coat colors, fur material, eye color and distinctive markings. '
            'Do not describe claws, appendages, anatomy, props, translucent objects or infer unusual accents from rendering artifacts. If uncertain omit the feature. '
            'Do not propose a new evolution. Describe only features actually visible. No mood or invented history.')
        perception_system = request.get('perception_system', perception_system)
        perception_key=digest(dict(system=perception_system,implementation=implementation,visual_references=refs))
        perception_path=ROOT/'outputs/v2/lineage_cache'/f'{perception_key}.json'
        if perception_path.exists():
            perception=json.loads(perception_path.read_text())
            if perception.get('key')!=perception_key or perception.get('signature_sha256')!=digest_prompt_text(perception['signature']):raise ValueError('Invalid cached lineage signature')
            perception={**perception,'reused':True}
        else:
            content=[dict(type='image',image=str(p)) for p in paths]+[dict(type='text',text='Extract the lineage signature; anatomy will be freely redesigned.')]
            perception_messages=[dict(role='system',content=perception_system),dict(role='user',content=content)]
            formatted=pipe.processor.apply_chat_template(perception_messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            visual_inputs=pipe.processor(text=[formatted],images=images,return_tensors='pt').to('cuda')
            with torch.inference_mode():perceived=pipe.text_encoder.generate(**visual_inputs,do_sample=False,max_new_tokens=160)
            signature=pipe.processor.tokenizer.decode(perceived[0,visual_inputs['input_ids'].shape[1]:],skip_special_tokens=True).strip()
            if '</think>' in signature:signature=signature.split('</think>')[-1].strip()
            perception=dict(key=perception_key,system=perception_system,signature=signature,signature_sha256=digest_prompt_text(signature),input_tokens=visual_inputs['input_ids'].shape[1],output_tokens=int(perceived.shape[1]-visual_inputs['input_ids'].shape[1]),visual_references=refs,reused=False)
            perception_path.parent.mkdir(parents=True,exist_ok=True);perception_path.write_text(json.dumps(perception,ensure_ascii=False,indent=2)+'\n')
            del visual_inputs,perceived
        path.with_suffix('.lineage.json').write_text(json.dumps(perception,ensure_ascii=False,indent=2)+'\n')
    user=request['user']+'\n\nACTUAL INHERITED VISUAL SIGNATURE (not an anatomical template):\n'+(perception['signature'] if perception else request.get('fallback_signature', 'Charcoal, ivory and gold; amber eyes; an organic thunder motif.'))
    messages=[dict(role='system',content=request['system']),dict(role='user',content=user)]
    formatted=pipe.processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
    inputs=pipe.processor(text=[formatted],return_tensors='pt').to('cuda')
    # Common persistent random seed gives reproducible exploration. Small state
    # changes share random draws; neither discrete body bins nor random UUIDs exist.
    with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
        torch.manual_seed(request.get('seed',42))
        with torch.inference_mode():output=pipe.text_encoder.generate(**inputs,**request['inference'])
    tokens=output[0,inputs['input_ids'].shape[1]:]
    raw=pipe.processor.tokenizer.decode(tokens,skip_special_tokens=True).strip()
    if '</think>' in raw:raw=raw.split('</think>')[-1].strip()
    try:concept=ground_design_concept(raw,request)
    except (ValueError,TypeError,KeyError) as exc:
        path.with_suffix('.invalid.json').write_text(json.dumps(dict(raw_output=raw,request=request,error=str(exc)),ensure_ascii=False,indent=2)+'\n')
        raise
    prompt=concept['image_prompt']
    record=dict(key=key,request=request,implementation=implementation,visual_references=refs,perception=perception,
        concept=concept,raw_output=raw,prompt=prompt,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        input_tokens=inputs['input_ids'].shape[1],output_tokens=len(tokens),seconds=time.monotonic()-started,
        actual_language_generation=True,training_performed=False,do_sample=request['inference'].get('do_sample',False),planner_seed=request.get('seed',42),
        anatomy_planning_receives_images=False,perception_receives_actual_previous_images=bool(images))
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    return prompt


def digest_prompt_text(value):
    return hashlib.sha256(value.encode()).hexdigest()
