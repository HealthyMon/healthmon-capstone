"""Identity-preserving alias evidence; real-video checks live in scripts/."""
import copy
import numpy as np
import pytest
from exercise_counter.config import load_config
from exercise_counter.duplicates import DuplicateResolver
from exercise_counter.tracking import histogram, PersonTracker
from exercise_counter.pipeline import Pipeline
from test_counter import pose

FRAME=np.full((720,900,3),(45,95,145),np.uint8)
OUTER=np.array([10,100,899,680],np.float32)
INNER=np.array([270,102,899,678],np.float32)


def inputs():
    cfg=load_config();resolver=DuplicateResolver(cfg);p,s=pose('squat')
    reference={'pose':(p.copy(),s.copy()),'box':OUTER.copy(),'t':.96,'identity':4,'side':'left','exercise':'squat'}
    return cfg,resolver,p,s,reference


def resolve(resolver,p,s,reference,boxes=None,other=None,**changes):
    boxes=np.array([OUTER,INNER]) if boxes is None else boxes
    def estimate(frame,box):
        return other if other is not None and np.array_equal(box,INNER) else (p.copy(),s.copy())
    args=dict(frame=FRAME,boxes=boxes,estimate=estimate,reference=reference,anchor_box=OUTER,
              anchor_hist=histogram(FRAME,OUTER),t=1.,identity=4,side='left',exercise='squat',flow_valid=True)
    args.update(changes)
    return resolver.resolve(**args)


def test_nested_alias_requires_pose_and_preserves_existing_box():
    _,r,p,s,ref=inputs();kept,cache,events=resolve(r,p,s,ref)
    np.testing.assert_array_equal(kept,np.array([OUTER]))
    assert len(cache)==2 and events[0]['decision']=='same_tracked_leg'
    assert events[0]['identity']==4 and events[0]['side']=='left'


def test_detection_order_does_not_change_selected_target_or_side():
    _,r,p,s,ref=inputs();a,_,_=resolve(r,p,s,ref);b,_,_=resolve(r,p,s,ref,boxes=np.array([INNER,OUTER]))
    np.testing.assert_array_equal(a,b)


@pytest.mark.parametrize('change',[{'reference':None},{'t':1.3},{'t':.96},{'identity':5},{'side':'right'},{'exercise':'curl'},{'flow_valid':False}])
def test_missing_stale_or_wrong_target_evidence_never_merges(change):
    _,r,p,s,ref=inputs();reference=change.pop('reference',ref) if 'reference' in change else ref
    kept,cache,_=resolve(r,p,s,reference,**change)
    assert len(kept)==2 and not cache


def test_different_visible_leg_keeps_both_people_and_original_overlap_lock():
    cfg,r,p,s,ref=inputs();other=p.copy();other[[11,13,15],0]+=80
    kept,_,events=resolve(r,p,s,ref,other=(other,s))
    assert len(kept)==2 and events[0]['decision']=='keep_distinct_pose'
    tracker=PersonTracker(cfg['tracking']);tracker.select(FRAME,np.array([OUTER]));identity=tracker.identity
    assert not tracker.associate(FRAME,kept,now=1.)
    assert tracker.box is None and tracker.locked_out and tracker.identity==identity


def test_different_shared_upper_body_prevents_merging_matching_legs():
    _,r,p,s,ref=inputs();other=p.copy();other[5,0]+=100
    kept,_,events=resolve(r,p,s,ref,other=(other,s))
    assert len(kept)==2 and events[0]['decision']=='keep_distinct_pose'


def test_low_confidence_on_one_required_joint_is_not_alias_evidence():
    _,r,p,s,ref=inputs();other_s=s.copy();other_s[13]=.1
    kept,_,events=resolve(r,p,s,ref,other=(p,other_s))
    assert len(kept)==2 and events[0]['decision']=='keep_missing_required_pose'


def test_another_person_cannot_replace_target_using_matching_current_boxes():
    _,r,p,s,ref=inputs();replacement=p.copy();replacement[[11,13,15],0]+=100
    kept,_,events=resolve(r,replacement,s,ref)
    assert len(kept)==2 and not events # both current poses match, but not selected track


def test_previously_separate_person_remains_distinct_even_if_pose_collapses():
    _,r,p,s,ref=inputs()
    # A bystander was separately visible; later both crops may focus on the
    # foreground target. Identical crop outputs must not erase that history.
    r.remember_distinct(FRAME,np.array([[50,100,500,680]],np.float32),np.array([600,100,899,680],np.float32),.90)
    kept,_,events=resolve(r,p,s,ref)
    assert len(kept)==2 and events[0]['decision'] in ('keep_distinct_history','keep_root_distinct_history')


def test_unclipped_overlapping_people_never_receive_partial_leg_exception():
    _,r,p,s,ref=inputs();boxes=np.array([[30,100,800,680],[240,102,800,678]],np.float32)
    kept,cache,_=resolve(r,p,s,ref,boxes=boxes)
    assert len(kept)==2 and not cache


def test_no_transitive_merge_through_a_chain_of_boxes():
    _,r,p,s,ref=inputs();third=np.array([500,102,899,678],np.float32)
    kept,_,events=resolve(r,p,s,ref,boxes=np.array([OUTER,INNER,third]))
    assert len(kept)==2
    assert any(np.array_equal(b,third) for b in kept)
    assert len([e for e in events if e['decision']=='same_tracked_leg'])==1


def test_disjoint_bystander_is_not_removed_with_duplicate():
    _,r,p,s,ref=inputs();bystander=np.array([20,2,180,80],np.float32)
    kept,_,_=resolve(r,p,s,ref,boxes=np.array([OUTER,INNER,bystander]))
    assert len(kept)==2 and any(np.array_equal(b,bystander) for b in kept)


class ModelsStub:
    fallback_generation=0
    fallback_reason=None
    providers={'pose':['CPUExecutionProvider'],'detector':['CPUExecutionProvider']}
    def __init__(self):self.boxes=np.array([OUTER]);self.calls=0;self.different=False
    def detect(self,frame):return self.boxes.copy()
    def estimate(self,frame,box):
        self.calls+=1;p,s=pose('squat')
        if self.different and np.array_equal(box,INNER):p[[11,13,15],0]+=80
        return p,s


@pytest.mark.parametrize('manual',[False,True])
def test_pipeline_alias_does_not_reselect_or_clear_counts(manual):
    cfg=load_config();cfg['runtime']['detection_every']=1;m=ModelsStub();pipe=Pipeline(cfg,'squat',m)
    if manual:pipe.set_manual_region((0,0,899,719),FRAME.shape)
    first,_,_=pipe.process(FRAME,0.)
    pipe.counter.machines['squat'].count=7
    pipe.tracker.flow=lambda _: True
    m.boxes=np.array([INNER,OUTER])
    snap,_,_=pipe.process(FRAME,.04)
    assert snap['tracked'] and snap['identity']==first['identity'] and snap['side']==first['side']
    assert snap['counts']=={'squat':7} and not pipe.manual_locked
    assert snap['diagnostics']['raw_detected_people']==2 and snap['diagnostics']['detected_people']==1
    assert snap['diagnostics']['duplicate_boxes_suppressed']==1
    assert m.calls== (4 if manual else 3) # root pose cache reused in detector mode


@pytest.mark.parametrize('manual',[False,True])
def test_pipeline_real_ambiguity_still_holds_and_preserves_count(manual):
    cfg=load_config();cfg['runtime']['detection_every']=1;m=ModelsStub();pipe=Pipeline(cfg,'squat',m)
    if manual:pipe.set_manual_region((0,0,899,719),FRAME.shape)
    first,_,_=pipe.process(FRAME,0.);pipe.counter.machines['squat'].count=7
    pipe.counter.machines['squat'].state='bent';pipe.tracker.flow=lambda _:True
    m.boxes=np.array([OUTER,INNER]);m.different=True
    snap,_,_=pipe.process(FRAME,.04)
    assert not snap['tracked'] and snap['identity']==first['identity']
    assert snap['counts']=={'squat':7} and snap['states']['squat']=='waiting'
    assert pipe.manual_locked if manual else pipe.tracker.locked_out


def test_previously_distinct_root_cannot_absorb_the_original_target():
    _,r,p,s,ref=inputs()
    r.remember_distinct(FRAME,np.array([OUTER]),np.array([0,690,899,719],np.float32),.9)
    kept,cache,events=resolve(r,p,s,ref)
    assert len(kept)==2 and not cache and events[0]['decision']=='keep_root_distinct_history'


@pytest.mark.parametrize('manual',[False,True])
def test_known_bystander_entering_old_location_never_inherits_target(manual):
    cfg=load_config();cfg['runtime']['detection_every']=1;m=ModelsStub();pipe=Pipeline(cfg,'squat',m)
    if manual:pipe.set_manual_region((0,0,899,719),FRAME.shape)
    first,_,_=pipe.process(FRAME,0.);pipe.counter.machines['squat'].count=5
    pipe.tracker.flow=lambda _:True
    # Known independent person, now at the target location, with adversarially
    # identical clothing and even an identical pose output.
    pipe.duplicate_resolver.remember_distinct(FRAME,np.array([OUTER]),np.array([0,690,899,719],np.float32),.02)
    snap,_,_=pipe.process(FRAME,.04)
    assert not snap['tracked'] and snap['counts']=={'squat':5}
    assert snap['identity']==first['identity']
    assert pipe.manual_locked if manual else pipe.tracker.locked_out


def test_loss_in_multi_person_scene_requires_explicit_reselection():
    cfg=load_config();cfg['runtime']['detection_every']=1;m=ModelsStub();pipe=Pipeline(cfg,'squat',m)
    pipe.process(FRAME,0.);pipe.counter.machines['squat'].count=3
    pipe.duplicate_resolver.remember_distinct(FRAME,np.array([[10,2,200,80]],np.float32),OUTER,.01)
    assert pipe.duplicate_resolver.known_other_seen
    m.boxes=np.empty((0,4),np.float32);pipe.tracker.flow=lambda _:True
    snap,_,_=pipe.process(FRAME,.04)
    assert not snap['tracked'] and not pipe.tracker.recoverable
    # Even a matching-looking person later occupying exactly the old location
    # cannot inherit the counter automatically after a multi-person loss.
    m.boxes=np.array([OUTER])
    for i in range(1,20):snap,_,_=pipe.process(FRAME,.04+i*.04)
    assert not snap['tracked'] and snap['counts']=={'squat':3}
    pipe.reset_selection();assert not pipe.duplicate_resolver.known_other_seen
