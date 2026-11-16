"""Run the same real model, tracker and counter deterministically on a local file.
Only explicit evaluation reports/public sample thumbnails are written. No camera.
"""
import argparse,json,sys,time,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import cv2
import numpy as np
from exercise_counter.config import ROOT,load_config
from exercise_counter.pipeline import Pipeline

p=argparse.ArgumentParser()
p.add_argument("video");p.add_argument("--exercise",required=True,choices=["pushup","squat","curl"])
p.add_argument("--provider",choices=["cpu","coreml"],default="coreml")
p.add_argument("--thumbnails",action="store_true")
a=p.parse_args()
cfg=load_config();cfg["runtime"]["provider"]=a.provider
pipeline=Pipeline(cfg,a.exercise)
c=cv2.VideoCapture(a.video)
if not c.isOpened(): raise ValueError(a.video)
fps=c.get(cv2.CAP_PROP_FPS);total=int(c.get(cv2.CAP_PROP_FRAME_COUNT))
rows=[];times=[];thumbs=[];detection_count=0;tracked_count=0
start=time.perf_counter();i=0
try:
    while True:
        ok,frame=c.read()
        if not ok:break
        max_w=cfg["runtime"]["max_frame_width"]
        if frame.shape[1]>max_w:frame=cv2.resize(frame,(max_w,round(frame.shape[0]*max_w/frame.shape[1])))
        snap,k,s=pipeline.process(frame,i/fps)
        times.append(snap["processing_ms"])
        tracked_count+=int(snap["tracked"])
        if snap["detected"] and len(pipeline.boxes):detection_count+=1
        rows.append({"frame":i,"t":round(i/fps,3),"tracked":snap["tracked"],"counts":snap["counts"],"states":snap["states"],"angles":snap["angles"],"message":snap["message"],"side":snap["side"],"scores":s.tolist() if s is not None else None})
        if a.thumbnails and (i%(max(total//12,1))==0):
            img=pipeline.draw(frame,k,s)
            img=cv2.resize(img,(480,270));cv2.putText(img,f"{i/fps:.2f}s {snap['counts']}",(10,24),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
            thumbs.append(img)
        i+=1
finally:c.release()
elapsed=time.perf_counter()-start
name=Path(a.video).stem+"-"+a.provider
result={"video":str(a.video),"exercise":a.exercise,"frames":i,"source_fps":fps,"duration_s":i/fps,
        "elapsed_s":elapsed,"offline_processing_fps":i/elapsed,"includes_capture_display":False,
        "providers":pipeline.models.providers,"fallback_reason":pipeline.models.fallback_reason,
        "tracked_frames":tracked_count,"tracked_fraction":tracked_count/max(i,1),"detections_with_person":detection_count,
        "mean_processing_ms":float(np.mean(times)),"p95_processing_ms":float(np.percentile(times,95)),
        "counts":pipeline.counter.snapshot()["counts"]}
(ROOT/f"reports/eval-{name}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
(ROOT/f"reports/frames-{name}.json").write_text(json.dumps(rows,ensure_ascii=False)+"\n")
if thumbs:
    while len(thumbs)%3: thumbs.append(np.zeros_like(thumbs[0]))
    sheet=np.vstack([np.hstack(thumbs[j:j+3]) for j in range(0,len(thumbs),3)])
    cv2.imwrite(str(ROOT/f"reports/contact-{name}.jpg"),sheet)
print(json.dumps(result,indent=2))
