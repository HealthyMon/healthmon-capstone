import numpy as np
from exercise_counter.config import load_config
from exercise_counter.tracking import PersonTracker


def scene(boxes,colors):
    frame=np.zeros((600,900,3),np.uint8)
    for b,c in zip(boxes,colors):
        x1,y1,x2,y2=np.asarray(b,dtype=int);frame[y1:y2,x1:x2]=c
    return frame


def test_size_order_does_not_replace_target():
    a=np.array([70,80,270,550],np.float32);b=np.array([450,50,880,590],np.float32)
    boxes=np.array([a,b]); frame=scene(boxes,[(40,80,220),(220,80,30)])
    tr=PersonTracker(load_config()["tracking"])
    assert tr.select(frame,boxes,(150,200))
    assert tr.associate(frame,boxes[::-1])
    np.testing.assert_array_equal(tr.box,a)


def test_lost_target_does_not_jump_to_other_or_reacquire_immediately():
    a=np.array([70,80,270,550],np.float32);b=np.array([450,50,880,590],np.float32)
    frame=scene([a,b],[(40,80,220),(220,80,30)])
    tr=PersonTracker(load_config()["tracking"]);tr.select(frame,np.array([a,b]),(150,200))
    assert not tr.associate(frame,np.array([b]))
    assert tr.locked_out and tr.box is None
    assert not tr.associate(frame,np.array([a]))
    assert tr.select(frame,np.array([a]),(150,200))


def test_brief_detector_dropout_recovers_same_identity_after_stable_hold():
    a=np.array([70,80,270,550],np.float32)
    frame=scene([a],[(40,80,220)])
    tr=PersonTracker(load_config()["tracking"]);tr.select(frame,np.array([a]))
    identity=tr.identity
    assert not tr.associate(frame,np.empty((0,4)),now=1.)
    assert not tr.associate(frame,np.array([a]),now=1.1)
    assert not tr.associate(frame,np.array([a]),now=1.2)
    assert tr.associate(frame,np.array([a]),now=1.4)
    assert tr.identity==identity


def test_recovery_rejects_different_appearance_and_expired_identity():
    a=np.array([70,80,270,550],np.float32)
    frame=scene([a],[(40,80,220)]);other=scene([a],[(220,80,30)])
    tr=PersonTracker(load_config()["tracking"]);tr.select(frame,np.array([a]))
    tr.associate(frame,np.empty((0,4)),now=1.)
    for now in (1.1,1.4,1.8):assert not tr.associate(other,np.array([a]),now=now)
    assert not tr.associate(frame,np.array([a]),now=5.)
    assert tr.box is None and tr.locked_out


def test_initial_multiple_people_requires_explicit_selection():
    a=[70,80,270,550];b=[450,50,880,590]
    tr=PersonTracker(load_config()["tracking"])
    assert not tr.associate(scene([a,b],[(0,0,200),(200,0,0)]),np.array([a,b],np.float32))


def test_overlap_locks_out_instead_of_identity_switch():
    a=np.array([70,80,270,550],np.float32);b=np.array([100,50,300,590],np.float32)
    frame=scene([a],[(40,80,220)])
    tr=PersonTracker(load_config()["tracking"]);tr.select(frame,np.array([a]))
    assert not tr.associate(frame,np.array([a,b]))
    assert tr.locked_out
