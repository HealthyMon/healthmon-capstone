import threading
import time
import cv2


class LatestCamera(threading.Thread):
    """Capture owns VideoCapture and releases it on the same thread.

    Exactly one mailbox slot: inference never consumes a growing frame queue.
    """
    def __init__(self,index,cfg):
        super().__init__(daemon=True,name="camera-capture")
        self.index,self.cfg=index,cfg
        self.stop_event=threading.Event()
        self.condition=threading.Condition()
        self.latest=None
        self.sequence=0
        self.error=None
        self.released=False

    def run(self):
        cap=cv2.VideoCapture()
        try:
            if not cap.open(self.index,cv2.CAP_AVFOUNDATION):
                self.error="카메라를 열 수 없습니다. 시스템 설정 → 개인정보 보호 및 보안 → 카메라에서 실행 앱(Codex 또는 터미널)을 허용한 뒤 다시 시작하세요."
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,self.cfg["camera_width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self.cfg["camera_height"])
            cap.set(cv2.CAP_PROP_FPS,self.cfg["camera_fps"])
            cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
            failures=0
            while not self.stop_event.is_set():
                ok,frame=cap.read()
                if not ok:
                    failures+=1
                    if failures>20:
                        self.error="카메라 입력이 끊겼습니다. 카메라 연결과 다른 앱의 사용 여부를 확인하세요."
                        break
                    self.stop_event.wait(.05)
                    continue
                failures=0
                with self.condition:
                    self.sequence+=1
                    self.latest=(self.sequence,time.perf_counter(),frame)
                    self.condition.notify_all()
        except Exception as exc:
            self.error=str(exc)
        finally:
            cap.release()
            self.released=True
            with self.condition: self.condition.notify_all()

    def read_latest(self,after):
        with self.condition:
            self.condition.wait_for(lambda:self.sequence>after or self.released or self.stop_event.is_set(),timeout=.1)
            if self.latest is not None and self.latest[0]>after:
                return self.latest
        return None

    def stop(self):
        self.stop_event.set()
        with self.condition: self.condition.notify_all()
