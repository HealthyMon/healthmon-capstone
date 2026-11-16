import time
import cv2
import numpy as np
from .runtime import Models
from .tracking import PersonTracker, histogram
from .duplicates import DuplicateResolver
from .counter import ExerciseCounter, joint_observations, required_joints, SIDES

EDGES=[(5,7),(7,9),(6,8),(8,10),(5,6),(5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16),(0,1),(0,2),(1,3),(2,4)]


class Pipeline:
    def __init__(self,cfg,exercise='pushup',models=None):
        self.cfg=cfg
        self.models=models or Models(cfg)
        self.counter=ExerciseCounter(cfg,exercise)
        self.tracker=PersonTracker(cfg['tracking'])
        self.frame_number=0
        self.last_detect=-1e10
        self.last_frame_time=None
        self.frame_shape=None
        self.boxes=np.empty((0,4),np.float32)
        self.click=None
        self.manual_box=None
        self.manual_locked=False
        self.manual_missing_since=None
        self.manual_status=''
        self.revision=0
        self.duplicate_resolver=DuplicateResolver(cfg)
        self.duplicate_reference=None
        self.raw_boxes=self.boxes.copy()
        self.duplicate_events=[]
        self.manual_anchor=None
        self.fallback_generation=self.models.fallback_generation

    def reset_selection(self):
        self.revision+=1
        self.manual_box=None
        self.manual_locked=False
        self.manual_missing_since=None
        self.click=None
        self.last_detect=-1e10
        self.tracker.clear()
        self.duplicate_resolver.clear()
        self.duplicate_reference=None
        self.manual_anchor=None
        self.counter.new_target()

    def select_point(self,point):
        self.reset_selection()
        self.click=point

    def set_manual_region(self,box,frame_shape):
        # Only an explicit user rectangle can enter this mode. No detector
        # failure ever substitutes a full-frame or arbitrary background crop.
        b=np.asarray(box,dtype=np.float32)
        if b.shape!=(4,) or not np.isfinite(b).all():return False
        h,w=frame_shape[:2]
        b[[0,2]]=np.clip(b[[0,2]],0,w-1);b[[1,3]]=np.clip(b[[1,3]],0,h-1)
        if np.any(b[2:]-b[:2]<self.cfg['manual_region']['min_size_px']):return False
        self.reset_selection()
        self.manual_box=b
        self.tracker.identity+=1
        self.manual_status='수동 영역 · 준비 자세 확인 · 전신 재식별 아님'
        return True

    def _lock_manual(self,reason):
        self.manual_locked=True
        self.manual_status=reason+' · 사람 영역을 다시 지정하세요'
        self.counter.cancel()

    def process(self,frame,t,before_count=None):
        started=time.perf_counter();rt=self.cfg['runtime'];force=False;pose_cache={};flow_valid=False
        if self.frame_shape is not None and self.frame_shape!=frame.shape[:2]:
            self.reset_selection()
            self.tracker.lose('입력 크기 변경 · 대상 또는 영역을 다시 선택하세요')
            force=True
        self.frame_shape=frame.shape[:2]
        if self.last_frame_time is not None and (t<=self.last_frame_time or t-self.last_frame_time>self.cfg['quality']['max_sample_gap_s']):
            self.counter.cancel()
            if self.manual_box is not None:self._lock_manual('입력 시간 단절')
            elif self.tracker.box is not None:self.tracker.lose('입력 지연 · 같은 사람을 다시 클릭하세요')
            force=True
        self.last_frame_time=t
        if self.manual_box is None and self.tracker.box is not None:
            flow_valid=self.tracker.flow(frame)
            if not flow_valid:force=True
        elif self.manual_box is not None and not self.manual_locked:
            flow_valid=True # fixed user ROI; fresh pose continuity still required
            if self.manual_anchor is None:self.manual_anchor=histogram(frame,self.manual_box)
        detect=(force or self.click is not None or self.frame_number%rt['detection_every']==0 or t-self.last_detect>=rt['max_detection_gap_s'])
        if detect:
            self.boxes=self.models.detect(frame)
            sizes=self.boxes[:,2:]-self.boxes[:,:2]
            self.boxes=self.boxes[np.all(sizes>=self.cfg['tracking']['min_box_size_px'],axis=1)]
            self.raw_boxes=self.boxes.copy()
            anchor_box=self.manual_box if self.manual_box is not None else self.tracker.box
            anchor_hist=self.manual_anchor if self.manual_box is not None else self.tracker.anchor
            self.boxes,pose_cache,self.duplicate_events=self.duplicate_resolver.resolve(
                frame,self.boxes,self.models.estimate,self.duplicate_reference,anchor_box,anchor_hist,t,
                self.tracker.identity,self.counter.side,self.counter.exercise,flow_valid)
            if self.manual_box is not None:
                # A manually selected single-person region must not contain two
                # detected people. Missing detections alone don't invent a pose.
                inside=0
                for box in self.boxes:
                    wh=np.maximum(0,np.minimum(box[2:],self.manual_box[2:])-np.maximum(box[:2],self.manual_box[:2]))
                    if np.prod(wh)/max(np.prod(box[2:]-box[:2]),1)>=self.cfg['manual_region']['multiple_person_overlap']:
                        inside+=1
                        if self.duplicate_resolver.previously_distinct(frame,box,t):self._lock_manual('별도로 보였던 다른 사람이 영역에 진입')
                if inside>1:self._lock_manual('영역 안에 여러 사람 탐지')
            elif self.click is not None:
                if self.tracker.select(frame,self.boxes,self.click):self.counter.new_target()
                self.click=None
            else:
                identity=self.tracker.identity
                self.tracker.associate(frame,self.boxes,t)
                if self.tracker.box is None and self.tracker.recoverable and self.duplicate_resolver.known_other_seen:
                    self.tracker.lose('다른 사람이 있던 장면에서 추적 손실 · 같은 사람을 다시 선택하세요',now=t)
                if identity>0 and self.tracker.box is not None and self.duplicate_resolver.previously_distinct(frame,self.tracker.box,t):
                    self.tracker.lose('다른 사람과 대상이 불확실함 · 같은 사람을 다시 선택하세요',now=t)
                if identity!=self.tracker.identity:self.counter.new_target()
            self.duplicate_resolver.remember_distinct(frame,self.boxes,self.manual_box if self.manual_box is not None else self.tracker.box,t)
            self.last_detect=t
        box=self.manual_box if self.manual_box is not None and not self.manual_locked else self.tracker.box
        if self.manual_box is not None and self.manual_locked:box=None
        points=scores=None;revision=self.revision
        if box is not None:
            points,scores=pose_cache.get(tuple(box),(None,None))
            if points is None:points,scores=self.models.estimate(frame,box)
        if self.manual_box is not None and not self.manual_locked and points is not None:
            obs=joint_observations(points,scores,frame.shape,self.cfg['quality'],self.manual_box)
            sides=[self.counter.side] if self.counter.side else list(SIDES)
            any_required=any(all(obs[i]['valid'] for i in required_joints(self.counter.exercise,s)) for s in sides)
            if any_required:self.manual_missing_since=None
            else:
                if self.manual_missing_since is None:self.manual_missing_since=t
                if t-self.manual_missing_since>=self.cfg['manual_region']['loss_lock_s']:
                    self._lock_manual('필수 관절 손실');box=None
        if before_count is not None:before_count()
        # A selection/region/exercise command arriving during inference must not
        # count the old frame with the new selection or coordinate system.
        if revision!=self.revision:points=scores=None;box=None
        if self.models.fallback_generation!=self.fallback_generation:
            self.counter.cancel();self.fallback_generation=self.models.fallback_generation
        snap=self.counter.update(points,scores,t,frame.shape,tracked=box is not None,observation_bounds=self.manual_box)
        if self.manual_locked:snap['message']=self.manual_status
        self.duplicate_reference=None
        if box is not None and points is not None and self.counter.side is not None:
            ids=required_joints(self.counter.exercise,self.counter.side)
            obs=joint_observations(points,scores,frame.shape,self.cfg['quality'],self.manual_box)
            if all(obs[i]['valid'] for i in ids):
                self.duplicate_reference={'pose':(points.copy(),scores.copy()),'box':box.copy(),'t':t,
                                          'identity':self.tracker.identity,'side':self.counter.side,'exercise':self.counter.exercise}
        self.frame_number+=1
        pose_valid=bool(points is not None and any(all(j['valid'] for j in snap['diagnostics']['joints'] if j['id'] in required_joints(self.counter.exercise,s)) for s in SIDES)) if snap['diagnostics']['joints'] else False
        snap['diagnostics'].update({'detection_ran':detect,'detected_people':len(self.boxes),
                                   'detection_age_s':round(t-self.last_detect,3),
                                   'raw_detected_people':len(self.raw_boxes),'duplicate_boxes_suppressed':len(self.raw_boxes)-len(self.boxes),
                                   'duplicate_evidence':self.duplicate_events,
                                   'pose_ran':points is not None,'required_pose_valid':pose_valid,
                                   'region_mode':'manual' if self.manual_box is not None else 'detector',
                                   'manual_locked':self.manual_locked})
        snap.update({'track':self.manual_status if self.manual_box is not None else self.tracker.status,
                     'identity':self.tracker.identity,'tracked':box is not None,'providers':self.models.providers,
                     'fallback_reason':self.models.fallback_reason,'processing_ms':(time.perf_counter()-started)*1000,
                     'detected':detect,'timestamp':t})
        return snap,points,scores

    def draw(self,frame,points,scores):
        canvas=frame.copy()
        for box in self.raw_boxes:
            a,b,c,d=box.astype(int);cv2.rectangle(canvas,(a,b),(c,d),(100,110,130),1)
        box=self.manual_box if self.manual_box is not None else self.tracker.box
        if box is not None:
            a,b,c,d=box.astype(int)
            color=(60,180,255) if self.manual_box is not None else (80,220,120)
            cv2.rectangle(canvas,(a,b),(c,d),color,2)
            cv2.putText(canvas,'MANUAL REGION' if self.manual_box is not None else f'PERSON {self.tracker.identity}',(a,max(20,b-8)),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
        if points is not None:
            observations=self.counter.diagnostics.get('joints') or joint_observations(points,scores,frame.shape,self.cfg['quality'],self.manual_box)
            valid=[v['valid'] for v in observations]
            for a,b in EDGES:
                if valid[a] and valid[b]:cv2.line(canvas,tuple(points[a].astype(int)),tuple(points[b].astype(int)),(100,220,245),3,cv2.LINE_AA)
            for i,pt in enumerate(points):
                if valid[i]:cv2.circle(canvas,tuple(pt.astype(int)),4,(255,165,80) if i%2 else (160,120,255),-1,cv2.LINE_AA)
        return canvas
