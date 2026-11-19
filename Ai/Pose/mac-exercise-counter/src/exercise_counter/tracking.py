"""Sticky single-person tracking; ambiguous/lost identity requires a user click.

Optical flow bridges detector frames. No sorting by size after acquisition;
no automatic identity replacement, even after the original person leaves.
"""
import cv2
import numpy as np
import time


def iou(a,b):
    a,b=np.asarray(a),np.asarray(b)
    wh=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]))
    intersection=float(np.prod(wh))
    return intersection/max(float(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-intersection),1)


def histogram(frame,box):
    x1,y1,x2,y2=np.asarray(box,dtype=int)
    crop=frame[max(0,y1):max(0,y2),max(0,x1):max(0,x2)]
    if crop.size==0: return np.zeros((24,16),np.float32)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256])
    return cv2.normalize(hist,hist,alpha=1,norm_type=cv2.NORM_L1)


class PersonTracker:
    def __init__(self,cfg):
        self.cfg=cfg
        self.box=None
        self.anchor=None
        self.previous_gray=None
        self.points=None
        self.locked_out=False
        self.status="사람을 찾는 중"
        self.identity=0
        self.recoverable=False
        self.lost_box=None
        self.lost_at=None
        self.recovery_since=None

    def clear(self):
        self.box=self.anchor=self.previous_gray=self.points=None
        self.locked_out=False
        self.status="사람을 찾는 중"
        self.recoverable=False
        self.lost_box=self.lost_at=self.recovery_since=None

    def lose(self,message="추적 손실 · 같은 사람을 클릭해 다시 선택",recoverable=False,now=None):
        self.lost_box=self.box.copy() if self.box is not None else None
        self.lost_at=time.monotonic() if now is None else now
        self.recovery_since=None
        self.recoverable=recoverable
        self.box=self.points=None
        self.locked_out=True
        self.status=message

    def select(self,frame,boxes,point=None):
        if len(boxes)==0:
            self.status="사람이 보이지 않음 · 카메라 각도와 구도를 확인하세요"
            return False
        if point is not None:
            x,y=point
            matches=[b for b in boxes if b[0]<=x<=b[2] and b[1]<=y<=b[3]]
        else:
            matches=list(boxes) if len(boxes)==1 else []
        if len(matches)!=1:
            self.status="한 사람의 보이는 사람 영역 안쪽을 클릭하세요"
            return False
        self.box=np.array(matches[0],np.float32)
        self.anchor=histogram(frame,self.box)
        self.locked_out=False
        self.recoverable=False
        self.identity+=1
        self.status=f"대상 {self.identity} 고정"
        self.refresh_flow(frame)
        return True

    def refresh_flow(self,frame):
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        mask=np.zeros_like(gray)
        if self.box is not None:
            x1,y1,x2,y2=self.box.astype(int)
            mask[max(0,y1):y2,max(0,x1):x2]=255
        self.points=cv2.goodFeaturesToTrack(gray,maxCorners=70,qualityLevel=.02,minDistance=7,mask=mask)
        self.previous_gray=gray

    def flow(self,frame):
        if self.box is None or self.points is None or len(self.points)<self.cfg["min_flow_points"]:
            return False
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        nxt,status,_=cv2.calcOpticalFlowPyrLK(self.previous_gray,gray,self.points,None,winSize=(21,21),maxLevel=3)
        if nxt is None: return False
        back,back_status,_=cv2.calcOpticalFlowPyrLK(gray,self.previous_gray,nxt,None,winSize=(21,21),maxLevel=3)
        if back is None: return False
        good=(status.ravel()==1)&(back_status.ravel()==1)&(np.linalg.norm(back-self.points,axis=2).ravel()<self.cfg["flow_error_px"])
        if good.sum()<self.cfg["min_flow_points"]: return False
        movement=np.median((nxt-self.points)[good,0,:],axis=0)
        diagonal=max(np.linalg.norm(self.box[2:]-self.box[:2]),1)
        if np.linalg.norm(movement)/diagonal>self.cfg["max_center_distance"]: return False
        self.box+=np.tile(movement,2)
        self.points=nxt[good].reshape(-1,1,2)
        self.previous_gray=gray
        return True

    def associate(self,frame,boxes,now=None):
        now=time.monotonic() if now is None else now
        if self.box is None:
            if not self.locked_out:
                return self.select(frame,boxes)
            if self.recoverable and self.lost_box is not None and now-self.lost_at<=self.cfg["recovery_window_s"]:
                if len(boxes)==1:
                    b=boxes[0]
                    diag=max(np.linalg.norm(self.lost_box[2:]-self.lost_box[:2]),1)
                    distance=np.linalg.norm((b[:2]+b[2:]-self.lost_box[:2]-self.lost_box[2:])/2)/diag
                    appearance=cv2.compareHist(self.anchor,histogram(frame,b),cv2.HISTCMP_BHATTACHARYYA)
                    match=iou(self.lost_box,b)>=self.cfg["recovery_min_iou"] and distance<=self.cfg["recovery_center_distance"] and appearance<=self.cfg["recovery_hist_distance"]
                    if match:
                        if self.recovery_since is None:self.recovery_since=now
                        self.status="같은 대상 확인 중 · 준비 자세를 유지하세요"
                        if now-self.recovery_since>=self.cfg["recovery_hold_s"]:
                            self.box=b.copy();self.locked_out=False;self.recoverable=False
                            self.status=f"대상 {self.identity} 복구 · 준비 자세부터"
                            self.refresh_flow(frame)
                            return True
                    else:self.recovery_since=None
                else:self.recovery_since=None
            else:
                self.recoverable=False
                self.status="추적 손실 · 보이는 사람 영역 클릭 또는 대상 재선택"
            return False
        ranked=[]
        diag=max(np.linalg.norm(self.box[2:]-self.box[:2]),1)
        for b in boxes:
            ov=iou(self.box,b)
            distance=np.linalg.norm((b[:2]+b[2:]-self.box[:2]-self.box[2:])/2)/diag
            appearance=cv2.compareHist(self.anchor,histogram(frame,b),cv2.HISTCMP_BHATTACHARYYA)
            if ov>=self.cfg["min_iou"] and distance<=self.cfg["max_center_distance"] and appearance<=self.cfg["max_hist_distance"]:
                ranked.append((ov-.4*appearance-.2*distance,b))
        ranked.sort(key=lambda v:v[0],reverse=True)
        if not ranked:
            self.lose("탐지 흔들림 · 같은 대상 복구 중",recoverable=True,now=now)
            return False
        candidate=ranked[0][1]
        ambiguous=(len(ranked)>1 and ranked[0][0]-ranked[1][0]<self.cfg["ambiguity_margin"])
        overlap=any(iou(candidate,b)>self.cfg["overlap_iou"] for b in boxes if not np.array_equal(b,candidate))
        if ambiguous or overlap:
            self.lose("사람이 겹침 · 분리된 뒤 같은 사람을 클릭하세요")
            return False
        self.box=candidate.copy()
        # Keep the original appearance anchor; never gradually learn a bystander.
        self.status=f"대상 {self.identity} 고정"
        self.refresh_flow(frame)
        return True
