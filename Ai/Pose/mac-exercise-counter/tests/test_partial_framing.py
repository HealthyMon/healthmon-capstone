"""State/visibility tests. Real pixel-level crops are evaluated separately."""
import copy
import numpy as np
import pytest
from exercise_counter.config import load_config
from exercise_counter.counter import ExerciseCounter, required_joints
from exercise_counter.pipeline import Pipeline
from exercise_counter.worker import Worker
from test_counter import pose, frames


def sequence(counter,exercise,keep,bent,occlude=None):
    t=0.
    for phase,(degrees,n) in enumerate([(170,16),(bent,25),(170,20)]):
        p,s=pose(exercise,degrees)
        remove=[i for i in range(17) if i not in keep]
        p[remove]=np.nan;s[remove]=np.nan
        for i in range(n):
            c_s=s.copy()
            if occlude is not None and phase==1 and i==20:c_s[occlude]=0
            counter.update(p,c_s,t,(720,1280,3));t+=.04
    return counter.snapshot()


@pytest.mark.parametrize('side',['left','right'])
def test_single_curl_arm_without_any_other_joint(side):
    c=ExerciseCounter(load_config(),'curl')
    result=sequence(c,'curl',required_joints('curl',side),45)
    assert result['counts'][side]==1
    assert result['counts']['right' if side=='left' else 'left']==0
    assert result['diagnostics']['reasons'][side]==''


@pytest.mark.parametrize('side',['left','right'])
def test_squat_one_leg_without_face_shoulders_or_other_leg(side):
    c=ExerciseCounter(load_config(),'squat')
    result=sequence(c,'squat',required_joints('squat',side),80)
    assert result['counts']['squat']==1 and result['side']==side


@pytest.mark.parametrize('side',['left','right'])
def test_pushup_arm_only_counts_but_defers_full_body_assessment(side):
    c=ExerciseCounter(load_config(),'pushup')
    result=sequence(c,'pushup',required_joints('pushup',side),85)
    assert result['counts']['pushup']==1 and result['side']==side
    assert result['diagnostics']['body_assessment']=='보류'
    assert '전신 자세 평가 보류' in result['message']


@pytest.mark.parametrize('missing',[11,13,15])
def test_required_leg_joint_missing_cancels_but_never_switches_side(missing):
    c=ExerciseCounter(load_config(),'squat')
    result=sequence(c,'squat',list(range(17)),80,occlude=missing)
    assert result['counts']['squat']==0 and result['side']=='left'


def test_missing_one_arm_cancels_only_that_arm():
    c=ExerciseCounter(load_config(),'curl')
    result=sequence(c,'curl',[5,7,9,6,8,10],45,occlude=9)
    assert result['counts']=={'left':0,'right':1}


@pytest.mark.parametrize('mode',['nan','outside','low_confidence'])
def test_unusable_required_joint_does_not_reuse_old_coordinate(mode):
    c=ExerciseCounter(load_config(),'curl');t=frames(c,0,.6,'curl')
    p,s=pose('curl',45)
    if mode=='nan':p[9]=np.nan
    elif mode=='outside':p[9,0]=-5
    else:s[9]=0
    c.update(p,s,t,(720,1280,3))
    assert np.isnan(c.smooth[9]).all() and c.machines['left'].state=='waiting'
    p,s=pose('curl',45);c.update(p,s,t+.04,(720,1280,3))
    np.testing.assert_allclose(c.smooth[9],p[9])
    assert c.machines['left'].count==0


def test_duplicate_hallucinated_arm_is_not_independent_evidence():
    c=ExerciseCounter(load_config(),'curl');t=0.
    for degrees,n in [(170,16),(45,25),(170,20)]:
        p,s=pose('curl',degrees)
        p[[6,8,10]]=p[[5,7,9]];s[[6,8,10]]=.65
        for _ in range(n):c.update(p,s,t,(720,1280,3));t+=.04
    assert c.snapshot()['counts']=={'left':1,'right':0}
    assert '구분 보류' in c.diagnostics['reasons']['right']


def test_nan_on_unused_face_does_not_cancel_a_rep():
    c=ExerciseCounter(load_config(),'curl')
    assert sequence(c,'curl',[5,7,9,6,8,10],45)['counts']=={'left':1,'right':1}


def test_boundary_is_based_on_raw_not_smoothed_wrist():
    c=ExerciseCounter(load_config(),'curl');t=frames(c,0,.6,'curl');t=frames(c,t,1,'curl',45)
    p,s=pose('curl',45);p[9,0]=2;c.update(p,s,t,(720,1280,3))
    assert c.machines['left'].state=='waiting'
    frames(c,t+.04,.7,'curl')
    assert c.snapshot()['counts']=={'left':0,'right':1}


class ModelsStub:
    fallback_generation=0
    fallback_reason=None
    providers={'pose':['CPUExecutionProvider'],'detector':['CPUExecutionProvider']}
    def __init__(self,people=False,valid=True):
        self.people=people;self.valid=valid;self.estimates=0
    def detect(self,frame):
        return np.array([[250,100,700,650]],np.float32) if self.people else np.empty((0,4),np.float32)
    def estimate(self,frame,box):
        self.estimates+=1
        p,s=pose('curl')
        if not self.valid:s[:]=0
        return p,s


FRAME=np.full((720,1280,3),100,np.uint8)


def test_detector_failure_never_implicitly_runs_full_frame_pose():
    m=ModelsStub();p=Pipeline(load_config(),'curl',models=m)
    for i in range(20):snap,_,_=p.process(FRAME,i*.04)
    assert m.estimates==0 and snap['counts']=={'left':0,'right':0}
    assert snap['diagnostics']['detected_people']==0 and not snap['diagnostics']['pose_ran']


def test_explicit_roi_can_run_pose_without_detection_and_reports_both():
    m=ModelsStub();p=Pipeline(load_config(),'curl',models=m)
    assert p.set_manual_region((250,100,700,650),FRAME.shape)
    snap,_,_=p.process(FRAME,0.)
    assert m.estimates==1 and snap['diagnostics']['region_mode']=='manual'
    assert snap['diagnostics']['detected_people']==0 and snap['diagnostics']['pose_ran']
    assert snap['counts']=={'left':0,'right':0}


def test_manual_background_low_confidence_locks_without_count():
    m=ModelsStub(valid=False);p=Pipeline(load_config(),'curl',models=m)
    p.set_manual_region((250,100,700,650),FRAME.shape)
    for i in range(25):snap,_,_=p.process(FRAME,i*.04)
    assert p.manual_locked and snap['counts']=={'left':0,'right':0}
    before=m.estimates;p.process(FRAME,1.04);assert m.estimates==before


def test_reselect_during_inference_discards_previous_region_pose():
    p=Pipeline(load_config(),'curl',models=ModelsStub(people=True))
    p.counter.machines['left'].count=4
    def change():p.set_manual_region((300,100,650,650),FRAME.shape)
    snap,points,_=p.process(FRAME,0.,before_count=change)
    assert points is None and snap['counts']['left']==4
    assert snap['states']['left']=='waiting'


def test_region_resize_preserves_counts_cancels_pending_and_clears_roi():
    p=Pipeline(load_config(),'curl',models=ModelsStub())
    p.set_manual_region((250,100,700,650),FRAME.shape)
    p.process(FRAME,0.)
    p.counter.machines['left'].count=3;p.counter.machines['left'].state='bent'
    snap,_,_=p.process(FRAME[:600],.04)
    assert p.manual_box is None and snap['counts']['left']==3 and snap['states']['left']=='waiting'
    assert p.tracker.locked_out


def test_small_or_invalid_roi_does_not_change_existing_selection():
    p=Pipeline(load_config(),'curl',models=ModelsStub());p.set_manual_region((250,100,700,650),FRAME.shape)
    before=p.manual_box.copy()
    assert not p.set_manual_region((10,10,12,12),FRAME.shape)
    assert not p.set_manual_region((np.nan,1,200,300),FRAME.shape)
    np.testing.assert_array_equal(p.manual_box,before)


def test_view_change_cancels_pending_preserves_counts_and_side():
    cfg=load_config();w=Worker(cfg,0,'squat');w.pipeline=Pipeline(cfg,'squat',models=ModelsStub())
    c=w.pipeline.counter;c.side='left';c.machines['squat'].count=2;c.machines['squat'].state='bent'
    w.control('squat_view','front');w.apply_commands()
    assert c.side=='left' and c.machines['squat'].count==2 and c.machines['squat'].state=='waiting'


def test_partial_pushup_does_not_upgrade_on_hallucinated_lower_body_mid_rep():
    c=ExerciseCounter(load_config(),'pushup');t=0.
    for degrees,n in [(170,16),(85,25),(170,20)]:
        p,s=pose('pushup',degrees)
        if t==0:s[11:]=0
        else:
            # Optional lower-body coordinates suddenly appear in an incompatible
            # direction. They must not upgrade a repetition begun as arm-only.
            p[11]=p[5]+[0,180];p[15]=p[11]+[0,180]
        for _ in range(n):c.update(p,s,t,(720,1280,3));t+=.04
    assert c.machines['pushup'].count==1
    assert c.diagnostics['body_assessment']=='보류'
