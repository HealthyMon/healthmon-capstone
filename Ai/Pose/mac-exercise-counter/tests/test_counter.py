import numpy as np
import pytest
from exercise_counter.config import load_config
from exercise_counter.counter import RepMachine,ExerciseCounter,SIDES


def feed(machine,start,duration,extended=False,bent=False,valid=True):
    for t in (start+i*.04 for i in range(int(np.ceil(duration/.04-1e-9)))):
        machine.update(float(t),extended,bent,valid)
    return start+duration


def cycle(machine,t):
    t=feed(machine,t,.4,extended=True)
    t=feed(machine,t,.2)
    t=feed(machine,t,.4,bent=True)
    t=feed(machine,t,.2)
    return feed(machine,t,.4,extended=True)


def test_complete_and_multiple():
    m=RepMachine(load_config()["timing"])
    t=cycle(m,0); assert m.count==1
    for _ in range(4): t=cycle(m,t)
    assert m.count==5


def test_initial_bent_requires_ready():
    m=RepMachine(load_config()["timing"])
    t=feed(m,0,1,bent=True)
    t=feed(m,t,.5,extended=True)
    assert m.count==0
    cycle(m,t); assert m.count==1


def test_threshold_jitter_cannot_complete_holds():
    m=RepMachine(load_config()["timing"])
    t=feed(m,0,.4,extended=True)
    for _ in range(100):
        t=feed(m,t,.04,bent=True)
        t=feed(m,t,.04,bent=False)
    assert m.count==0 and m.state=="ready"
    t=feed(m,t,.4,bent=True)
    for _ in range(100):
        t=feed(m,t,.04,extended=True)
        t=feed(m,t,.04,extended=False)
    assert m.count==0
    feed(m,t,.4,extended=True); assert m.count==1


def test_long_bent_hold_does_not_duplicate():
    m=RepMachine(load_config()["timing"])
    t=feed(m,0,.4,extended=True)
    t=feed(m,t,10,bent=True)
    assert m.count==0
    t=feed(m,t,1,extended=True); assert m.count==1
    feed(m,t,5,extended=True); assert m.count==1


def test_overlong_rep_cancels():
    m=RepMachine(load_config()["timing"])
    t=feed(m,0,.4,extended=True)
    t=feed(m,t,30,bent=True)
    feed(m,t,1,extended=True); assert m.count==0


def test_partial_motion_and_fast_spike():
    m=RepMachine(load_config()["timing"])
    t=feed(m,0,.4,extended=True)
    t=feed(m,t,1)
    t=feed(m,t,.4,extended=True)
    assert m.count==0
    t=feed(m,t,.08,bent=True)
    feed(m,t,.4,extended=True); assert m.count==0


@pytest.mark.parametrize("failure",["occlusion","tracking","gap","pause"])
def test_interruption_preserves_count_cancels_incomplete(failure):
    m=RepMachine(load_config()["timing"])
    t=cycle(m,0)
    t=feed(m,t,.5,bent=True)
    if failure in ("occlusion","tracking"): m.update(t,False,False,False); t+=.1
    elif failure=="gap": t+=1
    else: m.cancel()
    t=feed(m,t,.5,extended=True)
    assert m.count==1
    cycle(m,t); assert m.count==2


def pose(exercise,degrees=170,drop=0):
    p=np.full((17,2),[450.,100.]); s=np.full(17,.95)
    for side,(sh,el,wr,hip,kn,an) in SIDES.items():
        dx=0 if side=="left" else 25
        if exercise=="pushup":
            p[sh]=[340+dx,240];p[el]=[340+dx,320]
            p[wr]=p[el]+80*np.array([np.sin(np.radians(degrees)),-np.cos(np.radians(degrees))])
            p[hip]=[550+dx,240];p[kn]=[650+dx,240];p[an]=[760+dx,240]
        elif exercise=="curl":
            p[sh]=[400+dx,200];p[el]=[400+dx,300]
            p[wr]=p[el]+90*np.array([np.sin(np.radians(degrees)),-np.cos(np.radians(degrees))])
            p[hip]=[400+dx,410];p[kn]=[400+dx,510];p[an]=[400+dx,620]
        else:
            # Side-view leg with fixed ankle, controllable knee flexion + hip Y.
            p[an]=[500+dx,620];p[kn]=[500+dx,500]
            p[hip]=p[kn]+120*np.array([-np.sin(np.radians(degrees)),np.cos(np.radians(degrees))])
            p[hip,1]+=drop
            p[sh]=p[hip]+[0,-160];p[el]=p[sh]+[0,80];p[wr]=p[el]+[20,70]
    return p,s


def frames(counter,t,duration,exercise,degrees=170,**kwargs):
    p,s=pose(exercise,degrees)
    for now in (t+i*.04 for i in range(int(np.ceil(duration/.04-1e-9)))): counter.update(p,s,float(now),(720,1280,3),**kwargs)
    return t+duration


@pytest.mark.parametrize("exercise,bent",[("pushup",85),("squat",80),("curl",45)])
def test_full_keypoint_pipeline(exercise,bent):
    c=ExerciseCounter(load_config(),exercise)
    t=frames(c,0,.6,exercise)
    t=frames(c,t,1,exercise,bent)
    frames(c,t,.7,exercise)
    assert all(c.machines[k].count==1 for k in c.active_keys()),c.snapshot()


def test_curl_arms_independent():
    c=ExerciseCounter(load_config(),"curl")
    t=frames(c,0,.6,"curl")
    p,s=pose("curl",45); normal,_=pose("curl")
    p[list(SIDES["right"])]=normal[list(SIDES["right"])]
    for now in (t+i*.04 for i in range(25)): c.update(p,s,float(now),(720,1280,3))
    frames(c,t+1,.7,"curl")
    assert c.machines["left"].count==1 and c.machines["right"].count==0


def test_side_does_not_switch_on_occlusion():
    c=ExerciseCounter(load_config(),"pushup")
    t=frames(c,0,.6,"pushup")
    assert c.side=="left"
    t=frames(c,t,1,"pushup",85)
    p,s=pose("pushup"); s[7]=.1
    c.update(p,s,t,(720,1280,3))
    assert c.side=="left" and c.machines["pushup"].count==0
    frames(c,t+.04,.7,"pushup")
    assert c.machines["pushup"].count==0


def test_pause_reset_exercise_change():
    c=ExerciseCounter(load_config(),"pushup")
    t=frames(c,0,.6,"pushup");t=frames(c,t,1,"pushup",85)
    c.set_paused(True);t=frames(c,t,1,"pushup")
    assert c.machines["pushup"].count==0
    c.set_paused(False);t=frames(c,t,.6,"pushup")
    t=frames(c,t,1,"pushup",85);t=frames(c,t,.7,"pushup")
    assert c.machines["pushup"].count==1
    t=frames(c,t,.7,"pushup",85); c.set_exercise("curl"); c.set_exercise("pushup")
    t=frames(c,t,.7,"pushup"); assert c.machines["pushup"].count==1
    c.reset();assert c.machines["pushup"].count==0 and c.side is None


def test_wrong_torso_and_out_of_frame_block():
    c=ExerciseCounter(load_config(),"pushup")
    t=frames(c,0,.6,"curl") # upright cannot ready pushup
    assert c.machines["pushup"].state=="waiting"
    p,s=pose("pushup"); p[15,0]=-10
    c.update(p,s,t,(720,1280,3))
    assert c.machines["pushup"].count==0


def test_nonmonotonic_time_and_nan_cancel():
    c=ExerciseCounter(load_config())
    t=frames(c,0,.6,"pushup");t=frames(c,t,.7,"pushup",85)
    p,s=pose("pushup")
    c.update(p,s,0,(720,1280,3)); assert c.machines["pushup"].count==0
    p[5,0]=np.nan;c.update(p,s,t,(720,1280,3)); assert c.machines["pushup"].state=="waiting"


@pytest.mark.parametrize("exercise,partial",[("pushup",125),("squat",135),("curl",100)])
def test_partial_keypoint_motion_does_not_count(exercise,partial):
    c=ExerciseCounter(load_config(),exercise)
    t=frames(c,0,.6,exercise)
    t=frames(c,t,1,exercise,partial)
    frames(c,t,.7,exercise)
    assert all(c.machines[k].count==0 for k in c.active_keys())


def test_visible_short_forearm_does_not_invent_bend_or_cancel_phase():
    c=ExerciseCounter(load_config(),"curl")
    t=frames(c,0,.6,"curl")
    p,s=pose("curl");p[9]=p[7]+[1,1]
    for i in range(10): c.update(p,s,t+i*.04,(720,1280,3))
    assert c.machines["left"].state=="ready" and c.machines["left"].count==0
    t=frames(c,t+.4,.8,"curl",45)
    frames(c,t,.7,"curl")
    assert c.machines["left"].count==1


def test_squat_requires_hip_drop_in_addition_to_knee_angle():
    c=ExerciseCounter(load_config(),"squat")
    t=frames(c,0,.6,"squat")
    p,s=pose("squat")
    for sh,el,wr,hip,kn,an in SIDES.values(): p[kn]=[p[hip,0]+120,(p[hip,1]+p[an,1])/2]
    for i in range(25): c.update(p,s,t+i*.04,(720,1280,3))
    frames(c,t+1,.7,"squat")
    assert c.machines["squat"].count==0


def test_curl_upper_body_crop_counts_without_hips_knees_ankles():
    c=ExerciseCounter(load_config(),"curl")
    t=0
    for degrees,duration in [(170,.6),(45,1),(170,.7)]:
        p,s=pose("curl",degrees)
        s[11:]=0 # lower body outside frame
        for i in range(int(np.ceil(duration/.04))):
            c.update(p,s,t+i*.04,(400,1280,3))
        t+=duration
    assert c.machines["left"].count==1 and c.machines["right"].count==1


def test_curl_upper_body_still_cancels_when_wrist_occluded():
    c=ExerciseCounter(load_config(),"curl")
    t=frames(c,0,.6,"curl");t=frames(c,t,1,"curl",45)
    p,s=pose("curl",45);s[9]=0
    c.update(p,s,t,(720,1280,3))
    frames(c,t+.04,.7,"curl")
    assert c.machines["left"].count==0 and c.machines["right"].count==1


def test_front_squat_uses_hip_drop_and_knee_change_with_hidden_wrists():
    c=ExerciseCounter(load_config(),"squat")
    t=0
    for bent,duration in [(False,.6),(True,1),(False,.7)]:
        p,s=pose("squat")
        for side,(sh,el,wr,hip,kn,an) in SIDES.items():
            if bent:
                dx=0 if side=="left" else 25
                p[hip]=[420+dx,440];p[sh]=[420+dx,280]
            if side=="right":p[list(SIDES[side]),0]+=100
            s[wr]=0
        for i in range(int(np.ceil(duration/.04-1e-9))):c.update(p,s,t+i*.04,(720,1280,3))
        t+=duration
    assert c.squat_view=="front" and c.machines["squat"].count==1,c.snapshot()
