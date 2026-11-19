"""Conservative aliases for an already tracked, frame-clipped squat leg.

Boxes alone never establish that two detections are the same person. We require
nested geometry, matching current poses, a fresh pose from the selected track,
and no history of the second box being a separately observed person. Unproven
pairs remain separate and reach the existing ambiguity/overlap safeguards.
"""
import cv2
import numpy as np
from .counter import joint_observations, required_joints
from .tracking import histogram, iou


def _area(box):
    return max(float(np.prod(np.maximum(0,box[2:]-box[:2]))),1.)


def _center_distance(a,b):
    return float(np.linalg.norm((a[:2]+a[2:]-b[:2]-b[2:])/2)/max(np.linalg.norm(b[2:]-b[:2]),1))


class DuplicateResolver:
    def __init__(self,cfg):
        self.cfg=cfg
        self.options=cfg['tracking']['duplicates']
        self.distinct=[]
        self.known_other_seen=False

    def clear(self):
        self.distinct=[]
        self.known_other_seen=False

    def _valid(self,pose,shape):
        p,s=pose
        return np.array([r['valid'] for r in joint_observations(p,s,shape,self.cfg['quality'])])

    def _geometry(self,a,b,shape):
        o=self.options;h,w=shape[:2]
        intersection=float(np.prod(np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]))))
        if iou(a,b)<o['min_iou'] or intersection/min(_area(a),_area(b))<o['min_containment']:return False
        height=min(a[3]-a[1],b[3]-b[1])
        if max(abs(a[1]-b[1]),abs(a[3]-b[3]))>height*o['vertical_edge_tolerance']:return False
        edge=o['frame_edge_px']
        # Narrow partial-body aliases share the same clipped image edge. Don't
        # turn this into generic NMS for overlapping people inside the frame.
        return bool((a[0]<=edge and b[0]<=edge) or (a[2]>=w-1-edge and b[2]>=w-1-edge))

    def previously_distinct(self,frame,box,t):
        self.distinct=[v for v in self.distinct if t-v['t']<=self.options['distinct_memory_s']]
        hist=histogram(frame,box)
        for item in self.distinct:
            nearby=iou(box,item['box'])>=self.options['distinct_iou'] or _center_distance(box,item['box'])<=self.options['distinct_center_distance']
            if nearby and cv2.compareHist(hist,item['hist'],cv2.HISTCMP_BHATTACHARYYA)<=self.cfg['tracking']['max_hist_distance']:
                return True
        return False

    def remember_distinct(self,frame,boxes,target,t):
        self.distinct=[v for v in self.distinct if t-v['t']<=self.options['distinct_memory_s']]
        if target is None:return
        for b in boxes:
            if iou(b,target)>=self.cfg['tracking']['min_iou']:continue
            # Only clearly separate observations create a veto, never aliases.
            self.distinct=[v for v in self.distinct if iou(v['box'],b)<.3]
            self.known_other_seen=True
            self.distinct.append({'box':b.copy(),'hist':histogram(frame,b),'t':t})
        self.distinct=self.distinct[-12:]

    def resolve(self,frame,boxes,estimate,reference,anchor_box,anchor_hist,t,identity,side,exercise,flow_valid):
        """Return effective boxes, a per-frame pose cache, and auditable evidence."""
        cache={};events=[];o=self.options;tr=self.cfg['tracking']
        if (not o['enabled'] or exercise!='squat' or side is None or reference is None or anchor_box is None or anchor_hist is None or not flow_valid or len(boxes)<2):
            return boxes,cache,events
        if (reference['identity']!=identity or reference['side']!=side or reference['exercise']!=exercise or not 0<t-reference['t']<=o['max_reference_age_s']):
            return boxes,cache,events
        ids=list(required_joints(exercise,side))
        if not self._valid(reference['pose'],frame.shape)[ids].all():return boxes,cache,events
        ranked=[]
        for i,b in enumerate(boxes):
            overlap=iou(anchor_box,b);distance=_center_distance(b,anchor_box)
            appearance=cv2.compareHist(anchor_hist,histogram(frame,b),cv2.HISTCMP_BHATTACHARYYA)
            if overlap>=tr['min_iou'] and distance<=tr['max_center_distance'] and appearance<=tr['max_hist_distance']:
                ranked.append((overlap-.4*appearance-.2*distance,i))
        if not ranked:return boxes,cache,events
        _,root=max(ranked)
        candidates=[i for i in range(len(boxes)) if i!=root and self._geometry(boxes[root],boxes[i],frame.shape)]
        if not candidates:return boxes,cache,events
        if self.previously_distinct(frame,boxes[root],t):
            return boxes,cache,[{'candidate':root,'decision':'keep_root_distinct_history'}]
        def get_pose(index):
            key=tuple(boxes[index])
            if key not in cache:cache[key]=estimate(frame,boxes[index])
            return cache[key]
        p,s=get_pose(root);valid=self._valid((p,s),frame.shape)
        if not valid[ids].all():return boxes,cache,events
        leg=min(sum(np.linalg.norm(p[a]-p[b]) for a,b in zip(ids,ids[1:])),
                sum(np.linalg.norm(reference['pose'][0][a]-reference['pose'][0][b]) for a,b in zip(ids,ids[1:])))
        if leg<2*self.cfg['quality']['min_segment_px']:return boxes,cache,events
        predicted=reference['pose'][0]+(anchor_box[:2]-reference['box'][:2])
        temporal=float(np.max(np.linalg.norm(p[ids]-predicted[ids],axis=1))/leg)
        if temporal>o['max_temporal_joint_distance']:return boxes,cache,events
        suppressed=[]
        for i in candidates:
            if self.previously_distinct(frame,boxes[i],t):
                events.append({'candidate':i,'decision':'keep_distinct_history'});continue
            other_p,other_s=get_pose(i);other_valid=self._valid((other_p,other_s),frame.shape)
            if not other_valid[ids].all():
                events.append({'candidate':i,'decision':'keep_missing_required_pose'});continue
            required_delta=float(np.max(np.linalg.norm(p[ids]-other_p[ids],axis=1))/leg)
            shared=valid & other_valid
            shared_delta=float(np.max(np.linalg.norm(p[shared]-other_p[shared],axis=1))/leg)
            if required_delta>o['max_required_joint_distance'] or shared_delta>o['max_shared_joint_distance']:
                events.append({'candidate':i,'decision':'keep_distinct_pose','required_delta':required_delta,'shared_delta':shared_delta});continue
            # Every removed box is compared directly with the retained root.
            # No transitive grouping through a chain of overlapping people.
            suppressed.append(i)
            events.append({'candidate':i,'retained':root,'decision':'same_tracked_leg','iou':iou(boxes[root],boxes[i]),
                           'required_delta':required_delta,'shared_delta':shared_delta,'temporal_delta':temporal,
                           'identity':identity,'side':side})
        return boxes[[i for i in range(len(boxes)) if i not in suppressed]],cache,events
