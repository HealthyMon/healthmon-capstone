import argparse
import copy
import json
import sys
import time
from pathlib import Path
from collections import deque
import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QCameraPermission
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QLabel,QPushButton,
    QComboBox,QFileDialog,QHBoxLayout,QVBoxLayout,QFrame,QMessageBox,QDialog,QPlainTextEdit)
from PySide6.QtMultimedia import QMediaDevices
from .config import ROOT,load_config
from .counter import STATE_LABELS, EXERCISE_GUIDES
from .worker import Worker

EXERCISES=[("팔굽혀펴기","pushup"),("스쿼트","squat"),("덤벨 컬","curl")]
ANGLE_LABELS={"elbow":"팔꿈치","knee":"무릎","torso_horizontal":"몸통/수평","body_line":"몸통 정렬","hip_drop":"골반 하강/다리","left_elbow":"왼팔","right_elbow":"오른팔"}


class VideoView(QWidget):
    clicked=Signal(float,float)
    region_selected=Signal(object,object)
    def __init__(self):
        super().__init__()
        self.image=None
        self.region_mode=False
        self.drag_start=None
        self.drag_end=None
        self.rect=QRectF()
        self.setMinimumSize(640,400)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_frame(self,frame):
        rgb=np.ascontiguousarray(frame[:,:,::-1])
        self.image=QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.contentsRect(),QColor("#111a28"))
        if self.image is None:
            painter.setPen(QColor("#aebcd0"))
            painter.setFont(QFont("Apple SD Gothic Neo",18))
            painter.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignCenter,"운동을 선택하고 시작하세요\n\n카메라 영상은 저장·전송하지 않습니다")
        else:
            scale=min(self.width()/self.image.width(),self.height()/self.image.height())
            w,h=self.image.width()*scale,self.image.height()*scale
            self.rect=QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
            painter.drawImage(self.rect,self.image)
            if self.drag_start is not None and self.drag_end is not None:
                painter.setPen(QColor("#ffbd68"))
                painter.drawRect(QRectF(self.drag_start,self.drag_end).normalized().intersected(self.rect))

    def source_point(self,p):
        return ((p.x()-self.rect.x())/self.rect.width()*self.image.width(),
                (p.y()-self.rect.y())/self.rect.height()*self.image.height())

    def mousePressEvent(self,event):
        if self.image is not None and self.rect.contains(event.position()):
            if self.region_mode:
                self.drag_start=self.drag_end=event.position();self.update()
            else:self.clicked.emit(*self.source_point(event.position()))

    def mouseMoveEvent(self,event):
        if self.drag_start is not None:self.drag_end=event.position();self.update()

    def mouseReleaseEvent(self,event):
        if self.drag_start is not None:
            rect=QRectF(self.drag_start,event.position()).normalized().intersected(self.rect)
            a=self.source_point(rect.topLeft());b=self.source_point(rect.bottomRight())
            self.drag_start=self.drag_end=None;self.region_mode=False;self.update()
            self.region_selected.emit((*a,*b),(self.image.height(),self.image.width()))


class Window(QMainWindow):
    def __init__(self,args):
        super().__init__()
        self.args=args
        self.cfg=load_config(args.config)
        if args.provider: self.cfg["runtime"]["provider"]=args.provider
        self.worker=None
        self.last_worker=None
        self.seen=0
        self.paused=False
        self.closing=False
        self.source=args.video if args.video else args.camera
        self.displayed=deque(maxlen=90)
        self.started_at=None
        self.setWindowTitle("Local Motion · 오프라인 운동 카운터")
        self.resize(1240,810)
        central=QWidget(); self.setCentralWidget(central)
        outer=QVBoxLayout(central); outer.setContentsMargins(24,20,24,20); outer.setSpacing(14)
        header=QHBoxLayout()
        title=QLabel("LOCAL MOTION"); title.setObjectName("title")
        badge=QLabel("●  ON DEVICE   /   RTMPose-L · 17 관절"); badge.setObjectName("badge")
        header.addWidget(title); header.addStretch(); header.addWidget(badge); outer.addLayout(header)
        controls=QHBoxLayout()
        self.exercise=QComboBox()
        for text,key in EXERCISES: self.exercise.addItem(text,key)
        self.exercise.setCurrentIndex([k for _,k in EXERCISES].index(args.exercise))
        self.exercise.currentIndexChanged.connect(self.change_exercise)
        self.camera=QComboBox()
        self.refresh_cameras()
        self.camera.setCurrentIndex(max(0,min(args.camera,self.camera.count()-1)))
        self.camera.activated.connect(self.change_camera)
        self.file_btn=QPushButton("동영상 열기"); self.file_btn.clicked.connect(self.open_video)
        self.start_btn=QPushButton("시작"); self.start_btn.setObjectName("primary"); self.start_btn.clicked.connect(self.start)
        self.pause_btn=QPushButton("일시정지"); self.pause_btn.clicked.connect(self.pause)
        self.stop_btn=QPushButton("종료"); self.stop_btn.clicked.connect(self.stop)
        self.reset_btn=QPushButton("횟수 초기화"); self.reset_btn.clicked.connect(self.reset)
        self.target_btn=QPushButton("대상 재선택"); self.target_btn.clicked.connect(self.retarget)
        for w in [self.exercise,self.camera,self.file_btn,self.start_btn,self.pause_btn,self.stop_btn,self.reset_btn,self.target_btn]: controls.addWidget(w)
        outer.addLayout(controls)
        region_controls=QHBoxLayout()
        self.roi_btn=QPushButton("사람 영역 직접 지정");self.roi_btn.setCheckable(True);self.roi_btn.toggled.connect(self.begin_region)
        region_controls.addWidget(self.roi_btn)
        region_controls.addWidget(QLabel("스쿼트 시점"))
        self.squat_view=QComboBox()
        for text,key in [("자동 (양쪽 골반)","auto"),("측면","side"),("정면","front")]:self.squat_view.addItem(text,key)
        self.squat_view.setCurrentIndex(["auto","side","front"].index(self.cfg["squat"]["view"]))
        self.squat_view.setEnabled(args.exercise=="squat");self.squat_view.currentIndexChanged.connect(self.change_squat_view)
        region_controls.addWidget(self.squat_view);region_controls.addStretch()
        self.diag_btn=QPushButton("인식 진단");self.diag_btn.clicked.connect(self.show_diagnostics);region_controls.addWidget(self.diag_btn)
        outer.addLayout(region_controls)
        self.diag_dialog=QDialog(self);self.diag_dialog.setWindowTitle("인식 진단 · 영상 저장 없음");self.diag_dialog.resize(720,530)
        diag_layout=QVBoxLayout(self.diag_dialog);self.diag_text=QPlainTextEdit();self.diag_text.setReadOnly(True);diag_layout.addWidget(self.diag_text)
        self.latest_snapshot=None
        body=QHBoxLayout(); body.setSpacing(20)
        self.video=VideoView(); self.video.clicked.connect(self.select_target); self.video.region_selected.connect(self.select_region); body.addWidget(self.video,1)
        panel=QFrame(); panel.setObjectName("panel"); panel.setFixedWidth(270)
        stats=QVBoxLayout(panel); stats.setContentsMargins(20,22,20,22); stats.setSpacing(18)
        self.count_label=QLabel("0"); self.count_label.setObjectName("count"); self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setWordWrap(True)
        stats.addWidget(QLabel("완료한 반복")); stats.addWidget(self.count_label)
        self.state_label=QLabel("준비 자세 확인"); self.state_label.setWordWrap(True); self.state_label.setObjectName("state"); stats.addWidget(self.state_label)
        self.track_label=QLabel("추적 대기"); self.track_label.setWordWrap(True); stats.addWidget(self.track_label)
        self.angle_label=QLabel("주요 관절 각도\n—"); self.angle_label.setWordWrap(True); stats.addWidget(self.angle_label)
        stats.addStretch()
        self.fps_label=QLabel("처리 — FPS\n표시 — FPS\n입력→표시 — ms"); stats.addWidget(self.fps_label)
        self.provider_label=QLabel("ONNX Runtime\n모델 로딩 전"); self.provider_label.setWordWrap(True); self.provider_label.setObjectName("muted"); stats.addWidget(self.provider_label)
        body.addWidget(panel); outer.addLayout(body,1)
        self.message=QLabel(EXERCISE_GUIDES[args.exercise]); self.message.setWordWrap(True); self.message.setObjectName("message"); outer.addWidget(self.message)
        self.source_label=QLabel("입력: "+(Path(args.video).name if args.video else "카메라")); self.source_label.setObjectName("muted"); outer.addWidget(self.source_label)
        note=QLabel("컬·팔굽혀펴기: 보이는 팔의 어깨·팔꿈치·손목 · 스쿼트: 골반·무릎·발목 · 좌/우는 본인 기준 · 맨손 컬도 셉니다."); note.setWordWrap(True); note.setObjectName("muted"); outer.addWidget(note)
        self.timer=QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(16)
        if args.autostart: QTimer.singleShot(300,self.start)
        if args.seconds: QTimer.singleShot(int(args.seconds*1000),self.close)
        self.update_buttons(False)

    def refresh_cameras(self):
        devices=QMediaDevices.videoInputs()
        for i,device in enumerate(devices): self.camera.addItem(f"카메라 {i} · {device.description()}",i)
        if not devices:
            for i in range(3): self.camera.addItem(f"카메라 {i}",i)

    def update_buttons(self,running):
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)
        self.camera.setEnabled(not running)
        self.file_btn.setEnabled(not running)
        self.roi_btn.setEnabled(running)

    def change_camera(self):
        self.source=self.camera.currentData()
        self.source_label.setText("입력: "+self.camera.currentText())

    def open_video(self):
        file,_=QFileDialog.getOpenFileName(self,"로컬 운동 동영상",str(ROOT),"Video (*.mp4 *.mov *.avi *.mkv *.m4v)")
        if file:
            self.source=file
            self.source_label.setText("입력: "+Path(file).name+" · 원본 시간 기준, 모든 프레임 처리")

    def start(self):
        if self.worker and self.worker.is_alive(): return
        if isinstance(self.source,int):
            app=QApplication.instance()
            permission=QCameraPermission()
            status=app.checkPermission(permission)
            print("CAMERA_PERMISSION",status,flush=True)
            if status==Qt.PermissionStatus.Undetermined:
                self.message.setText("macOS 카메라 권한 허용을 기다리는 중…")
                app.requestPermission(permission,self,lambda *_: self.start())
                return
            if status==Qt.PermissionStatus.Denied:
                self.message.setText("카메라 권한이 필요합니다. 시스템 설정 → 개인정보 보호 및 보안 → 카메라에서 Local Motion(또는 실행한 터미널/Codex)을 허용하고 앱을 다시 여세요.")
                return
        self.worker=Worker(copy.deepcopy(self.cfg),self.source,self.exercise.currentData())
        self.video.region_mode=False;self.roi_btn.setChecked(False)
        self.last_worker=self.worker
        self.worker.start()
        self.seen=0; self.paused=False; self.displayed.clear()
        self.started_at=time.perf_counter()
        self.pause_btn.setText("일시정지")
        self.message.setText("모델과 입력을 준비하는 중…")
        self.update_buttons(True)

    def pause(self):
        self.paused=not self.paused
        if self.worker: self.worker.control("pause",self.paused)
        self.pause_btn.setText("재개" if self.paused else "일시정지")
        self.state_label.setText("일시정지" if self.paused else "준비 자세 확인")

    def reset(self):
        if self.worker: self.worker.control("reset")
        self.count_label.setText("왼팔 0\n오른팔 0" if self.exercise.currentData()=="curl" else "0")
        self.state_label.setText("준비 자세 확인")

    def change_exercise(self):
        self.squat_view.setEnabled(self.exercise.currentData()=="squat")
        self.message.setText(EXERCISE_GUIDES[self.exercise.currentData()])
        if self.worker: self.worker.control("exercise",self.exercise.currentData())
        self.state_label.setText("준비 자세 확인")
        self.count_label.setText("—")

    def retarget(self):
        if self.worker:self.worker.control("retarget")
        self.roi_btn.setChecked(False)
        self.message.setText("자동 탐지로 전환 · 보이는 사람 영역을 클릭하세요")

    def begin_region(self,enabled):
        self.video.region_mode=enabled
        self.video.drag_start=self.video.drag_end=None
        self.video.update()
        if enabled:self.message.setText("영상에서 한 사람의 측정 부위를 드래그하세요. 필요한 관절 전체와 여백을 포함하세요. 수동 영역은 인물 재식별을 보장하지 않습니다.")

    def select_region(self,box,shape):
        self.roi_btn.setChecked(False)
        if min(box[2]-box[0],box[3]-box[1])<self.cfg['manual_region']['min_size_px']:
            self.message.setText("영역이 너무 작습니다. 필요한 관절 전체를 포함해 다시 지정하세요.");return
        if self.worker:self.worker.control('region',(box,shape))
        self.message.setText("수동 영역 선택 · 진행 중 반복 취소 · 준비 자세부터 확인합니다")

    def change_squat_view(self):
        value=self.squat_view.currentData()
        self.cfg['squat']['view']=value
        if self.worker:self.worker.control('squat_view',value)

    def show_diagnostics(self):
        self.update_diagnostics(self.latest_snapshot)
        self.diag_dialog.show();self.diag_dialog.raise_()

    def update_diagnostics(self,snap):
        if snap is None:self.diag_text.setPlainText('입력을 시작하면 현재 관측값을 표시합니다.');return
        d=snap.get('diagnostics',{})
        lines=[f"영역: {d.get('region_mode','—')} · 추적: {snap['track']}",
               f"최근 사람 탐지: {d.get('detected_people',0)}명 · {d.get('detection_age_s',0):.2f}초 전 · 이번 프레임 실행: {d.get('detection_ran',False)}",
               f"탐지 박스 원본 {d.get('raw_detected_people',0)}개 → 유효 {d.get('detected_people',0)}개 · 같은 대상 중복 제외 {d.get('duplicate_boxes_suppressed',0)}개",
               f"Pose 실행: {d.get('pose_ran',False)} · 필수 관절 세트 유효: {d.get('required_pose_valid',False)}",
               f"사용 관절: {snap['side'] or '좌우 팔 독립 / 선택 대기'} · 스쿼트 시점: {d.get('squat_view') or '—'}",
               f"카운터: {snap['states']} · 횟수: {snap['counts']}",
               f"각도: {snap['angles']} · 처리 {snap.get('processing_fps',0):.1f} FPS",
               f"입력 관측 시각: {snap.get('timestamp',0):.3f}초 · 일시정지: {snap['paused']}",
               f"전신 자세 평가: {d.get('body_assessment','보류')}",
               '현재 안내: '+snap['message'],'']
        joints={j['id']:j for j in d.get('joints',[])}
        for side,ids in d.get('required',{}).items():
            lines.append(('왼쪽' if side=='left' else '오른쪽')+' 필수 관절')
            for i in ids:
                j=joints.get(i)
                lines.append(f"  {j['name']}: 신뢰도 {j['confidence']} · {'유효' if j['valid'] else j['reason']}" if j else f'  관절 {i}: 현재 관측 없음')
            reason=d.get('reasons',{}).get(side,'')
            if reason:lines.append('  보류 이유: '+reason)
        lines+=['','신뢰도/경계 검사는 현재 원본 좌표 기준입니다. 숨겨진 관절의 이전 좌표는 사용하지 않습니다.']
        self.diag_text.setPlainText('\n'.join(lines))

    def select_target(self,x,y):
        if self.worker: self.worker.control("select",(x,y))

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.message.setText("카메라를 해제하는 중…")
        self.pause_btn.setEnabled(False); self.stop_btn.setEnabled(False)

    def poll(self):
        if not self.worker: return
        packet=self.worker.take_latest(self.seen)
        if packet:
            self.seen,canvas,snap=packet
            self.latest_snapshot=snap
            if self.diag_dialog.isVisible():self.update_diagnostics(snap)
            self.video.set_frame(canvas)
            now=time.perf_counter(); self.displayed.append(now)
            latency=(now-snap["arrival"])*1000
            self.worker.metrics["display_latency_ms"].append(latency)
            self.worker.metrics["display_times"].append(now)
            for key in ("display_latency_ms","display_times"):
                if len(self.worker.metrics[key])>18000: self.worker.metrics[key]=self.worker.metrics[key][-18000:]
            dfps=(len(self.displayed)-1)/(self.displayed[-1]-self.displayed[0]) if len(self.displayed)>1 else 0
            if snap["exercise"]==self.exercise.currentData():
                if snap["exercise"]=="curl":
                    self.count_label.setText(f"왼팔 {snap['counts']['left']}\n오른팔 {snap['counts']['right']}")
                    self.count_label.setStyleSheet("font-size:42px")
                else:
                    self.count_label.setText(str(next(iter(snap["counts"].values()))))
                    self.count_label.setStyleSheet("font-size:88px")
                self.state_label.setText("일시정지" if self.paused else " / ".join(STATE_LABELS[v] for v in snap["states"].values()))
                self.angle_label.setText("주요 관절 각도\n"+"\n".join(f"{ANGLE_LABELS.get(k,k)}  {v}{'' if k=='hip_drop' else '°'}" for k,v in snap["angles"].items()))
            self.track_label.setText(snap["track"]+("\n고정 관절: "+("왼쪽" if snap["side"]=="left" else "오른쪽") if snap["side"] else ""))
            self.message.setText("일시정지 · 재개 후 준비 자세를 확인합니다." if self.paused else snap["message"])
            self.fps_label.setText(f"처리 {snap['processing_fps']:.1f} FPS\n표시 {dfps:.1f} FPS\n입력→표시 {latency:.0f} ms")
            names=set(p for ps in snap["providers"].values() for p in ps)
            provider="CoreML + CPU" if "CoreMLExecutionProvider" in names else "CPU"
            self.provider_label.setText("ONNX Runtime · "+provider+("\nCoreML 실패 → CPU 복구" if snap["fallback_reason"] else ""))
        elif not self.seen: self.message.setText(self.worker.info)
        if self.worker.finished:
            self.update_buttons(False)
            released = self.worker.camera is None or self.worker.metrics["camera_released"]
            self.message.setText(self.worker.error or ("입력 종료 · 장치 해제 완료 · 시작하면 새 세션" if released else "카메라 종료 확인 중"))
            self.write_metrics()
            self.worker=None
            if self.closing: self.close()

    def write_metrics(self):
        if not self.args.report or not self.last_worker: return
        m=dict(self.last_worker.metrics)
        times=m.pop("display_times",[])
        m["displayed_frames"]=len(times)
        m["display_fps"]=(len(times)-1)/(times[-1]-times[0]) if len(times)>1 else 0
        for key in ("processing_ms","display_latency_ms"):
            values=m.pop(key,[])
            m[key+"_mean"]=float(np.mean(values)) if values else None
            m[key+"_p95"]=float(np.percentile(values,95)) if values else None
        m["source"]=str(self.source); m["error"]=self.last_worker.error
        Path(self.args.report).write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n")

    def closeEvent(self,event):
        if self.worker and self.worker.is_alive():
            self.closing=True
            self.stop()
            event.ignore()
        else:
            self.write_metrics()
            event.accept()


def main():
    parser=argparse.ArgumentParser(description="로컬 RTMPose-L 운동 카운터")
    parser.add_argument("--video",help="로컬 동영상 경로")
    parser.add_argument("--camera",type=int,default=0)
    parser.add_argument("--exercise",choices=[k for _,k in EXERCISES],default="pushup")
    parser.add_argument("--provider",choices=["cpu","coreml"])
    parser.add_argument("--config")
    parser.add_argument("--autostart",action="store_true")
    parser.add_argument("--seconds",type=float,help="검증용 자동 종료 시간")
    parser.add_argument("--report",help="영상 없이 실행 통계만 JSON으로 저장")
    args=parser.parse_args()
    if args.video:
        args.video=str(Path(args.video).expanduser().resolve())
        if not Path(args.video).is_file(): parser.error("로컬 동영상 파일이 없습니다.")
    app=QApplication(sys.argv)
    app.setApplicationName("Local Motion")
    apply_style(app)
    window=Window(args); window.show()
    sys.exit(app.exec())


def apply_style(app):
    app.setStyleSheet('''
      QWidget {background:#0b121d;color:#e9eef7;font-family:"Apple SD Gothic Neo";font-size:14px;}
      QLabel#title {font-size:25px;font-weight:800;letter-spacing:2px;}
      QLabel#badge {color:#78e5b1;font-size:12px;}
      QPushButton,QComboBox {background:#1d2a3e;border:1px solid #344760;border-radius:8px;padding:10px 12px;min-height:22px;}
      QPushButton:hover {background:#2b3d57;} QPushButton:disabled {color:#65758a;background:#152031;}
      QPushButton#primary {background:#60ddb0;color:#0c2720;font-weight:700;}
      QPushButton#primary:disabled {background:#183c35;color:#6c9186;}
      QFrame#panel {background:#131f30;border-radius:14px;}
      QFrame#panel QLabel {background:transparent;} QLabel#count {font-size:88px;font-weight:800;color:#78e5b1;}
      QLabel#state {font-size:18px;font-weight:700;} QLabel#muted {color:#93a5bd;font-size:12px;}
      QLabel#message {background:#192a3b;border-radius:10px;padding:12px;color:#cfebff;}
    ''')


if __name__=="__main__": main()
