"""Time-based, conservative repetition state machines; no frame-count timers."""
from dataclasses import dataclass
import math
import numpy as np

SIDES = {"left": (5, 7, 9, 11, 13, 15), "right": (6, 8, 10, 12, 14, 16)}
STATE_LABELS = {"waiting": "준비 자세 확인", "ready": "준비 · 굽히세요", "bent": "굽힘 확인 · 복귀하세요"}


def angle(a, b, c):
    u, v = a-b, c-b
    d = np.linalg.norm(u) * np.linalg.norm(v)
    if d < 1e-6:
        return float("nan")
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v)/d, -1, 1))))


def vertical_degrees(vector):
    return float(np.degrees(np.arctan2(abs(vector[0]), abs(vector[1]))))


@dataclass
class RepMachine:
    timing: dict
    count: int = 0
    state: str = "waiting"
    candidate: str | None = None
    since: float | None = None
    departure: float | None = None
    last_time: float | None = None

    def cancel(self):
        self.state = "waiting"
        self.candidate = self.since = self.departure = self.last_time = None

    def reset(self):
        self.cancel()
        self.count = 0

    def hold(self, condition, name, t, duration):
        if not condition:
            self.candidate = self.since = None
            return False
        if self.candidate != name:
            self.candidate, self.since = name, t
        return t - self.since + 1e-9 >= duration

    def update(self, t, extended, bent, valid=True, max_gap=0.45):
        if not valid or not math.isfinite(t):
            self.cancel()
            return
        if self.last_time is not None and (t <= self.last_time or t-self.last_time > max_gap):
            self.cancel()
        self.last_time = t
        if self.departure is not None and t-self.departure > self.timing["maximum_rep_s"]:
            self.cancel()
            self.last_time = t
        if self.state == "waiting":
            if self.hold(extended, "ready", t, self.timing["ready_hold_s"]):
                self.state, self.candidate = "ready", None
        elif self.state == "ready":
            if extended:
                self.departure = None
            elif self.departure is None:
                self.departure = t
            if self.hold(bent, "bent", t, self.timing["bent_hold_s"]):
                self.state, self.candidate = "bent", None
        elif self.state == "bent":
            if self.hold(extended, "return", t, self.timing["return_hold_s"]):
                if self.departure is not None and t-self.departure >= self.timing["minimum_rep_s"]:
                    self.count += 1
                self.state, self.candidate, self.departure = "ready", None, None


JOINT_NAMES = ['코','왼쪽 눈','오른쪽 눈','왼쪽 귀','오른쪽 귀','왼쪽 어깨','오른쪽 어깨','왼쪽 팔꿈치','오른쪽 팔꿈치','왼쪽 손목','오른쪽 손목','왼쪽 골반','오른쪽 골반','왼쪽 무릎','오른쪽 무릎','왼쪽 발목','오른쪽 발목']
EXERCISE_GUIDES = {
    'curl': '컬 측정: 보이는 팔의 어깨·팔꿈치·손목을 보여주세요. 한쪽 팔만 있어도 됩니다.',
    'squat': '스쿼트 측정을 위해 같은 쪽 골반부터 무릎·발목까지 보여주세요.',
    'pushup': '팔굽혀펴기 측정: 같은 쪽 어깨·팔꿈치·손목을 보여주세요. 하체가 없으면 전신 자세 평가는 보류합니다.',
}


def required_joints(exercise, side):
    sh, el, wr, hip, kn, an = SIDES[side]
    return (hip, kn, an) if exercise == 'squat' else (sh, el, wr)


def joint_observations(points, scores, shape, quality, bounds=None):
    """Current raw observations only; never infer visibility from smoothed data."""
    h, w = shape[:2]
    margin = quality['frame_margin_px']
    x1,y1,x2,y2 = (0,0,w,h) if bounds is None else bounds
    x1,y1,x2,y2 = max(0,x1),max(0,y1),min(w,x2),min(h,y2)
    rows=[]
    for i,(xy,score) in enumerate(zip(points,scores)):
        finite=bool(np.isfinite(xy).all() and np.isfinite(score))
        inside=finite and x1+margin < xy[0] < x2-margin and y1+margin < xy[1] < y2-margin
        confident=finite and score >= quality['keypoint_confidence']
        reason='' if inside and confident else ('좌표 무효' if not finite else '화면/영역 경계 밖' if not inside else '신뢰도 부족')
        rows.append({'id':i,'name':JOINT_NAMES[i],'confidence':round(float(score),3) if np.isfinite(score) else None,
                     'valid':bool(inside and confident),'reason':reason})
    return rows


class ExerciseCounter:
    def __init__(self, cfg, exercise='pushup'):
        self.cfg=cfg
        self.exercise=exercise
        self.machines={k:RepMachine(cfg['timing']) for k in ('pushup','squat','left','right')}
        self.paused=False
        self.side=None
        self.smooth=None
        self.previous_valid=None
        self.last_t=None
        self.baseline=None
        self.squat_view=None
        self.pushup_full_assessment=None
        self.last_message=EXERCISE_GUIDES[exercise]
        self.angles={}
        self.diagnostics={}

    def cancel(self):
        for machine in self.machines.values():machine.cancel()
        self.smooth=self.previous_valid=self.last_t=self.baseline=None
        self.squat_view=None
        self.pushup_full_assessment=None
        # Anatomical side remains locked after an occlusion, even between reps.

    def new_target(self):
        self.cancel()
        self.side=None

    def set_exercise(self,exercise):
        if exercise not in EXERCISE_GUIDES:raise ValueError(exercise)
        self.exercise=exercise
        self.new_target()
        self.last_message=EXERCISE_GUIDES[exercise]
        self.diagnostics={}

    def set_paused(self,paused):
        self.paused=paused
        self.cancel()

    def reset(self):
        for key in self.active_keys():self.machines[key].reset()
        self.new_target()

    def active_keys(self):
        return ('left','right') if self.exercise=='curl' else (self.exercise,)

    def snapshot(self):
        keys=self.active_keys()
        return {'exercise':self.exercise,'counts':{k:self.machines[k].count for k in keys},
                'states':{k:self.machines[k].state for k in keys},'angles':self.angles.copy(),
                'side':self.side,'message':self.last_message,'paused':self.paused,'diagnostics':self.diagnostics}

    def update(self,points,scores,t,frame_shape,tracked=True,observation_bounds=None):
        self.angles={}
        self.diagnostics={'required':{s:list(required_joints(self.exercise,s)) for s in SIDES},
                          'joints':[],'reasons':{},'body_assessment':'보류','squat_view':self.squat_view}
        if self.paused:
            # Keep current-frame diagnostic observations while counting remains
            # paused. File playback freezes this labelled observation, never
            # reuses it as evidence after resume.
            if tracked and points is not None and scores is not None and np.shape(points)==(17,2) and np.shape(scores)==(17,):
                raw=np.asarray(points,dtype=float)
                obs=joint_observations(raw,np.asarray(scores),frame_shape,self.cfg['quality'],observation_bounds)
                self.diagnostics['joints']=obs
                sides=list(SIDES) if self.exercise=='curl' else ([self.side] if self.side else [])
                for side in sides:
                    ids=required_joints(self.exercise,side)
                    if all(obs[i]['valid'] for i in ids):
                        value=angle(*(raw[i] for i in ids))
                        if math.isfinite(value):self.angles[side+'_elbow' if self.exercise=='curl' else 'knee' if self.exercise=='squat' else 'elbow']=round(value,1)
            self.last_message='일시정지 · 재개 후 준비 자세부터'
            return self.snapshot()
        if not tracked or points is None or scores is None:
            self.cancel()
            self.last_message='추적 보류 · '+EXERCISE_GUIDES[self.exercise]
            return self.snapshot()
        points,scores=np.asarray(points,dtype=float),np.asarray(scores,dtype=float)
        q=self.cfg['quality']
        if points.shape!=(17,2) or scores.shape!=(17,) or not math.isfinite(t):
            self.cancel();self.last_message='관절 출력 또는 입력 시간 무효';return self.snapshot()
        observations=joint_observations(points,scores,frame_shape,q,observation_bounds)
        visible=np.array([v['valid'] for v in observations],dtype=bool)
        if self.exercise=='curl' and visible[[5,7,9,6,8,10]].all():
            # A cropped-out arm is sometimes hallucinated on top of the visible
            # arm. Suppress the less confident duplicate; never transfer state
            # or counts between anatomical sides.
            if np.max(np.linalg.norm(points[[5,7,9]]-points[[6,8,10]],axis=1))<=q['duplicate_arm_distance_px']:
                loser='right' if min(scores[[5,7,9]])>=min(scores[[6,8,10]]) else 'left'
                for i in required_joints('curl',loser):
                    visible[i]=False;observations[i]['valid']=False
                    observations[i]['reason']='반대쪽 팔과 같은 위치로 추정되어 구분 보류'
        self.diagnostics['joints']=observations
        if self.last_t is None or t<=self.last_t or t-self.last_t>q['max_sample_gap_s']:
            self.cancel()
            self.smooth=np.full((17,2),np.nan)
            self.previous_valid=np.zeros(17,dtype=bool)
        alpha=1 if self.last_t is None else 1-math.exp(-(t-self.last_t)/max(q['smoothing_tau_s'],1e-6))
        continuous=visible & self.previous_valid
        self.smooth[continuous]+=alpha*(points[continuous]-self.smooth[continuous])
        self.smooth[visible & ~continuous]=points[visible & ~continuous]
        self.smooth[~visible]=np.nan # no stale coordinates after missing observations
        self.previous_valid=visible.copy();self.last_t=t
        p=self.smooth

        def valid(ids):return bool(visible[list(ids)].all())
        def missing(ids):
            absent=[i for i in ids if not visible[i]]
            if not absent:return ''
            i=absent[0];particle='이' if (ord(JOINT_NAMES[i][-1])-0xac00)%28 else '가'
            return f"{JOINT_NAMES[i]}{particle} 보이지 않습니다 ({observations[i]['reason']})"
        def segments(ids):
            a,b,c=ids
            return min(np.linalg.norm(p[a]-p[b]),np.linalg.norm(p[c]-p[b]))>=q['min_segment_px']

        if self.exercise!='curl' and self.side is None:
            eligible=[s for s in SIDES if valid(required_joints(self.exercise,s))]
            if eligible:
                def visibility(side):
                    ids=required_joints(self.exercise,side)
                    confidence=float(min(scores[list(ids)]))
                    if self.exercise=='pushup':
                        a,b,c=ids
                        # Prefer the better resolved arm at initial acquisition;
                        # a far arm can score well while nearly edge-on/occluded.
                        extent=min(np.linalg.norm(p[a]-p[b]),np.linalg.norm(p[c]-p[b]))
                        return confidence*math.sqrt(extent)
                    return confidence
                self.side=max(eligible,key=visibility)

        if self.exercise=='curl':
            labels=[]
            for side in SIDES:
                sh,el,wr=ids=required_joints('curl',side)
                machine=self.machines[side];c=self.cfg['curl']
                name='왼팔' if side=='left' else '오른팔'
                reason=missing(ids)
                if not reason:
                    value=angle(p[sh],p[el],p[wr])
                    measurable=segments(ids) and math.isfinite(value)
                    # No pelvis, opposite shoulder, face or leg requirements.
                    ok=vertical_degrees(p[el]-p[sh])<=c['max_upper_arm_vertical_deg'] and p[el,1]>p[sh,1]
                    machine.update(t,measurable and value>=c['extended_angle'],measurable and value<=c['bent_angle'],ok,q['max_sample_gap_s'])
                    if math.isfinite(value):self.angles[side+'_elbow']=round(value,1)
                    if not ok:reason='위팔을 몸 옆으로 내린 방향으로 유지하세요'
                    elif not measurable:reason='팔이 겹쳐 각도 전이 보류'
                else:machine.update(t,False,False,False)
                self.diagnostics['reasons'][side]=reason
                labels.append(f'{name} 측정 보류: {reason}' if reason else f'{name} 측정 중 · {STATE_LABELS[machine.state]}')
            self.last_message=' / '.join(labels)
            return self.snapshot()

        if self.side is None:
            self.last_message=EXERCISE_GUIDES[self.exercise]
            for side in SIDES:self.diagnostics['reasons'][side]=missing(required_joints(self.exercise,side))
            return self.snapshot()
        ids=required_joints(self.exercise,self.side)
        reason=missing(ids)
        machine=self.machines[self.exercise]
        if reason:
            machine.cancel();self.baseline=None;self.squat_view=None;self.pushup_full_assessment=None
            self.last_message=reason
            self.diagnostics['reasons'][self.side]=reason
            return self.snapshot()
        sh,el,wr,hip,kn,an=SIDES[self.side]
        c=self.cfg[self.exercise]
        value=angle(*(p[i] for i in ids))
        measurable=segments(ids) and math.isfinite(value)
        if not measurable:
            machine.cancel();self.baseline=None;self.squat_view=None;self.pushup_full_assessment=None
            self.last_message='필수 관절 사이 거리가 너무 짧아 측정을 보류합니다'
            self.diagnostics['reasons'][self.side]=self.last_message
            return self.snapshot()
        ok=True
        if self.exercise=='pushup':
            extended,bent=value>=c['extended_angle'],value<=c['bent_angle']
            self.angles={'elbow':round(value,1)}
            body_visible=valid((sh,hip,an)) and min(np.linalg.norm(p[sh]-p[hip]),np.linalg.norm(p[an]-p[hip]))>=q['min_segment_px']
            if self.pushup_full_assessment is None and extended:
                self.pushup_full_assessment=body_visible
            # Do not upgrade an arm-only repetition because a missing ankle
            # briefly acquires a plausible model coordinate later in the rep.
            if self.pushup_full_assessment and body_visible:
                torso=90-vertical_degrees(p[hip]-p[sh]);line=angle(p[sh],p[hip],p[an])
                ok=torso<=c['max_torso_horizontal_deg'] and line>=c['min_body_line_angle']
                self.angles.update(torso_horizontal=round(torso,1),body_line=round(line,1))
                self.diagnostics['body_assessment']='관측된 2D 몸통 조건 충족' if ok else '관측된 몸통 방향/정렬 조건 미충족'
                suffix=' · 2D 몸통 조건 확인' if ok else ' · 몸통 방향/정렬 조건 확인 필요'
            else:
                suffix=' · 팔 반복만 측정 · 전신 자세 평가 보류'
            reason='' if ok else '몸통을 수평에 가깝게 유지하세요'
        else:
            # Scale is measured once from the visible leg in the ready pose.
            # Neither shoulder coordinates nor unseen pelvis/ankle are used.
            leg_length=float(np.linalg.norm(p[hip]-p[kn])+np.linalg.norm(p[an]-p[kn]))
            if machine.state=='waiting' and value>=c['extended_angle']:
                self.baseline=(float(p[hip,1]-p[an,1]),leg_length,p[an].copy(),value)
                mode=c['view']
                if mode=='auto':
                    mode='front' if valid((11,12)) and np.linalg.norm(p[12]-p[11])/leg_length>=c['front_hip_width_leg'] else 'side'
                self.squat_view=mode
            drop=0.
            if self.baseline is not None:
                height,scale,ankle,ready_knee=self.baseline
                drop=float((p[hip,1]-p[an,1]-height)/scale)
                ok=np.linalg.norm(p[an]-ankle)/scale<=c['max_ankle_shift_leg']
            extended=value>=c['extended_angle'] and drop<=c['max_return_hip_drop_leg']
            bent=self.baseline is not None and value<=c['bent_angle'] and drop>=c['min_hip_drop_leg']
            if self.squat_view=='front' and self.baseline is not None:
                bent=value<=c['front_bent_angle'] and self.baseline[3]-value>=c['front_min_knee_change_deg'] and drop>=c['front_min_hip_drop_leg']
            self.angles={'knee':round(value,1),'hip_drop':round(drop,2)}
            self.diagnostics['squat_view']=self.squat_view
            reason='' if ok else '발 또는 카메라 위치 변화 · 준비 자세를 다시 확인하세요'
            suffix=' · '+('정면' if self.squat_view=='front' else '측면')+' · 골반·무릎·발목 측정'
        machine.update(t,extended,bent,ok,q['max_sample_gap_s'])
        if not ok:self.baseline=None;self.squat_view=None
        self.diagnostics['reasons'][self.side]=reason
        self.last_message=(STATE_LABELS[machine.state]+suffix) if ok else reason
        return self.snapshot()
