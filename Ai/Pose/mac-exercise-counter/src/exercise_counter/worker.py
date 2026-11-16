import collections
import queue
import threading
import time
import traceback
import cv2
from .capture import LatestCamera
from .pipeline import Pipeline


class Worker(threading.Thread):
    def __init__(self,cfg,source,exercise):
        super().__init__(daemon=True,name="local-inference")
        self.cfg,self.source,self.exercise=cfg,source,exercise
        self.stop_event=threading.Event()
        self.commands=queue.SimpleQueue()
        self.lock=threading.Lock()
        self.latest=None
        self.version=0
        self.error=None
        self.finished=False
        self.camera=None
        self.pipeline=None
        self.info="로컬 모델을 불러오는 중…"
        self.metrics={"processed":0,"tracked_frames":0,"dropped_input_frames":0,"processing_ms":[],"display_latency_ms":[],"display_times":[],"camera_released":False,"control_events":[],"identity_events":[]}

    def control(self,name,value=None):
        self.commands.put((name,value))

    def apply_commands(self):
        while not self.commands.empty():
            name,value=self.commands.get()
            c=self.pipeline.counter
            self.metrics['control_events'].append({'command':name,'value':value,'processed':self.metrics['processed'],
                                                  'identity_before':self.pipeline.tracker.identity})
            self.metrics['control_events']=self.metrics['control_events'][-256:]
            if name=="pause": c.set_paused(value)
            elif name=="exercise": c.set_exercise(value); self.pipeline.revision+=1
            elif name=="reset": c.reset()
            elif name=="select": self.pipeline.select_point(value)
            elif name=="retarget": self.pipeline.reset_selection()
            elif name=="region": self.pipeline.set_manual_region(*value)
            elif name=="squat_view":
                c.cfg["squat"]["view"]=value; c.cancel(); self.pipeline.revision+=1

    def run(self):
        cap=None
        try:
            self.pipeline=Pipeline(self.cfg,self.exercise)
            self.metrics["providers"]=self.pipeline.models.providers
            self.metrics["fallback_reason"]=self.pipeline.models.fallback_reason
            self.info="입력을 기다리는 중…"
            is_camera=isinstance(self.source,int)
            if is_camera:
                self.camera=LatestCamera(self.source,self.cfg["runtime"])
                self.camera.start()
            else:
                cap=cv2.VideoCapture(self.source)
                if not cap.isOpened(): raise RuntimeError("동영상 파일을 열 수 없습니다.")
                fps=cap.get(cv2.CAP_PROP_FPS)
                if fps<=0: raise RuntimeError("동영상 FPS를 읽을 수 없습니다.")
            seq=0
            completed=collections.deque(maxlen=60)
            while not self.stop_event.is_set():
                self.apply_commands()
                if not is_camera and self.pipeline.counter.paused:
                    self.stop_event.wait(.025)
                    continue
                if is_camera:
                    packet=self.camera.read_latest(seq)
                    if packet is None:
                        if self.camera.error: raise RuntimeError(self.camera.error)
                        if self.camera.released: break
                        continue
                    number,arrival,frame=packet
                    self.metrics["dropped_input_frames"]+=max(0,number-seq-1)
                    seq=number
                    stamp=arrival
                else:
                    ok,frame=cap.read()
                    if not ok: break
                    arrival=time.perf_counter()
                    stamp=seq/fps
                    seq+=1
                max_w=self.cfg["runtime"]["max_frame_width"]
                if frame.shape[1]>max_w:
                    frame=cv2.resize(frame,(max_w,round(frame.shape[0]*max_w/frame.shape[1])))
                snap,points,scores=self.pipeline.process(frame,stamp,self.apply_commands)
                canvas=self.pipeline.draw(frame,points,scores)
                completed.append(time.perf_counter())
                snap["processing_fps"]=(len(completed)-1)/(completed[-1]-completed[0]) if len(completed)>1 else 0
                snap["arrival"]=arrival
                snap["source_frame"]=seq
                snap["dropped_input_frames"]=self.metrics["dropped_input_frames"]
                self.metrics["processed"]+=1
                self.metrics["tracked_frames"]+=int(snap["tracked"])
                self.metrics["frame_wh"]=[canvas.shape[1],canvas.shape[0]]
                self.metrics["processing_ms"].append(snap["processing_ms"])
                if len(self.metrics["processing_ms"])>18000: self.metrics["processing_ms"]=self.metrics["processing_ms"][-18000:]
                previous=self.metrics.get('last_snapshot')
                if previous is None or (previous['identity'],previous['tracked'])!=(snap['identity'],snap['tracked']):
                    self.metrics['identity_events'].append({'frame':seq,'identity':snap['identity'],'tracked':snap['tracked'],'track':snap['track']})
                    self.metrics['identity_events']=self.metrics['identity_events'][-256:]
                self.metrics["last_snapshot"]=snap
                self.info=snap["message"]
                with self.lock:
                    self.version+=1
                    self.latest=(self.version,canvas,snap)
                if not is_camera:
                    # Deterministic offline replay: every frame, original media
                    # timestamps. Playback slows if inference cannot keep up.
                    self.stop_event.wait(max(0,1/fps-(time.perf_counter()-arrival)))
        except Exception as exc:
            self.error=str(exc)
            traceback.print_exc()
        finally:
            if cap is not None: cap.release()
            if self.camera is not None:
                self.camera.stop()
                while self.camera.is_alive(): self.camera.join(timeout=.2)
                self.metrics["camera_released"]=self.camera.released
            self.finished=True

    def take_latest(self,after):
        with self.lock:
            return self.latest if self.latest is not None and self.version>after else None

    def stop(self):
        self.stop_event.set()
        if self.camera: self.camera.stop()
