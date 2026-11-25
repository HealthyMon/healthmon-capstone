using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Healthmon.Common;
using UnityEngine;

[Serializable] public sealed class PoseWorkoutRecord { public string session_id, exercise, completed_at; public int count,left_count,right_count; public float duration_seconds; }
[Serializable] public sealed class PoseWorkoutHistory { public List<PoseWorkoutRecord> records=new List<PoseWorkoutRecord>(); }

/// <summary>Owns camera/session lifetime; the pose service owns repetition counting.</summary>
public sealed class HealthMonPoseScreen : MonoBehaviour
{
    public HealthMonPoseView view;
    private HealthMonPoseClient client;
    private WebCamTexture cameraTexture;
    private Texture2D frameTexture, resultTexture;
    private Color32[] inputPixels, outputPixels;
    private int selected, cameraIndex, sequence, generation;
    private string session;
    private bool prepared, running, paused, finishing, faulted, changing;
    private bool cameraChosen, applicationPaused, restoreCamera, restoring;
    private int previousSleepTimeout;
#if UNITY_ANDROID && !UNITY_EDITOR
    private ScreenOrientation previousOrientation;
    private bool orientationCaptured;
    private readonly List<UnityEngine.XR.ARFoundation.ARSession> suspendedArSessions=new List<UnityEngine.XR.ARFoundation.ARSession>();
#endif
    private float elapsed, nextFrame;
    private PoseSnapshot latest;
    private HealthMonPoseWorkoutSync.Entry workoutBinding;
    private string resultEventId;
    public bool IsRunning => running;
    public bool IsPaused => paused;
    public bool IsTransitioning => changing || finishing || restoring;
    public bool HasConnectionError => faulted;
    public PoseSnapshot Latest => latest;
    public HealthMonPoseClient Client => client;
#if UNITY_EDITOR
    // Explicit Editor verification source. Never included in Android/player builds.
    private Texture2D verificationFrame;
    private double verificationTimestamp;
    private bool verificationFresh;
    public bool VerificationHistoryIsolated { get; set; }
    public string VerificationEndpoint { get; set; }
    public void SetVerificationFrame(Texture2D texture,double timestamp)
    { verificationFrame=texture; verificationTimestamp=timestamp; verificationFresh=true; prepared=true; if(view!=null)view.SetPreview(texture); }
#endif
    private void Awake()
    {
        view.Build(); client=gameObject.AddComponent<HealthMonPoseClient>();
        view.ExerciseSelected+=SelectExercise; view.Prepare+=PrepareCamera; view.StartWorkout+=BeginWorkout;
        view.PauseWorkout+=TogglePause; view.FinishWorkout+=Finish; view.Retarget+=Retarget;
        view.SwitchCamera+=SwitchCamera; view.Close+=Close; view.Retry+=Open;
        previousSleepTimeout=Screen.sleepTimeout;
        if(HealthMonPoseWorkoutSync.Instance!=null)
        {
            HealthMonPoseWorkoutSync.Instance.Recorded+=WorkoutRecorded;
            HealthMonPoseWorkoutSync.Instance.Deferred+=WorkoutDeferred;
        }
        view.gameObject.SetActive(false);
    }
    public void Open()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        if(!orientationCaptured){previousOrientation=Screen.orientation;orientationCaptured=true;}
        Screen.orientation=ScreenOrientation.Portrait;
#endif
        if(running) { view.gameObject.SetActive(true); return; }
        // Release the AR/food camera and conversation before opening another camera workflow.
        FindAnyObjectByType<UIManager>()?.ShowHome();
#if UNITY_ANDROID && !UNITY_EDITOR
        // ARSession can be outside the disabled XR Origin and still own the phone camera.
        foreach(var ar in FindObjectsByType<UnityEngine.XR.ARFoundation.ARSession>(FindObjectsSortMode.None))
            if(ar.enabled){suspendedArSessions.Add(ar);ar.enabled=false;}
#endif
        view.gameObject.SetActive(true);view.transform.SetAsLastSibling();view.ShowSelection();SelectExercise(selected);
    }
    public void SelectExercise(int index)
    {
        if(running||changing||index<0||index>=HealthMonPoseView.Keys.Length)return;
        selected=index;view.SelectExercise(index);
    }
    public void PrepareCamera() { if(!running&&!changing)StartCoroutine(PrepareRoutine()); }
    private IEnumerator PrepareRoutine(bool resume=false)
    {
        changing=true; int version=++generation;ReleaseCamera(); prepared=false;view.SetPreview(null);view.ShowCamera(resume);
        if(!resume)view.count.text="—";
        view.status.text="촬영 준비";view.message.text=view.CameraGuide;view.startButton.interactable=false;
#if UNITY_EDITOR
        if(verificationFrame!=null) { prepared=true;view.SetPreview(verificationFrame);view.sourceLabel.text="검증용 실제 운동 영상";view.startButton.interactable=true;changing=false;yield break; }
#endif
#if UNITY_ANDROID && !UNITY_EDITOR
        if(!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera))
        {
            bool answered=false;
            var callbacks=new UnityEngine.Android.PermissionCallbacks();
            callbacks.PermissionGranted+=_=>answered=true;
            callbacks.PermissionDenied+=_=>answered=true;
            callbacks.PermissionDeniedAndDontAskAgain+=_=>answered=true;
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.Camera,callbacks);
            float permissionDeadline=Time.realtimeSinceStartup+60;
            while(!answered&&version==generation&&Time.realtimeSinceStartup<permissionDeadline)yield return null;
            // The native permission dialog must finish before opening the camera.
            yield return null;
        }
        bool authorized=UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.Camera);
#else
        yield return Application.RequestUserAuthorization(UserAuthorization.WebCam);
        bool authorized=Application.HasUserAuthorization(UserAuthorization.WebCam);
#endif
        if(version!=generation){changing=false;yield break;}
        if(!authorized)
        { view.message.text="카메라 권한 필요\n기기 설정에서 권한 허용 후 재시도";changing=false;yield break; }
        var cameras=WebCamTexture.devices;
        if(cameras.Length==0) {view.message.text="카메라 감지 실패 · 연결 확인 후 카메라 전환";view.sourceLabel.text="카메라 없음";changing=false;yield break;}
        if(!cameraChosen)
        {
            for(int i=0;i<cameras.Length;i++)if(cameras[i].isFrontFacing){cameraIndex=i;break;}
            cameraChosen=true;
        }
        while(applicationPaused&&version==generation)yield return null;
        if(version!=generation){changing=false;yield break;}
        cameraIndex%=cameras.Length;cameraTexture=new WebCamTexture(cameras[cameraIndex].name,640,480,15);cameraTexture.Play();
        float deadline=Time.realtimeSinceStartup+3;
        while(cameraTexture!=null&&cameraTexture.width<=16&&Time.realtimeSinceStartup<deadline&&version==generation)yield return null;
        if(version!=generation){changing=false;yield break;}
        if(cameraTexture!=null&&cameraTexture.width<=16)
        {
            // Some Windows drivers reject a requested resolution/FPS; retry their default mode.
            cameraTexture.Stop();Destroy(cameraTexture);cameraTexture=new WebCamTexture(cameras[cameraIndex].name);cameraTexture.Play();
            deadline=Time.realtimeSinceStartup+5;
            while(cameraTexture!=null&&cameraTexture.width<=16&&Time.realtimeSinceStartup<deadline&&version==generation)yield return null;
        }
        if(version!=generation){changing=false;yield break;}
        prepared=cameraTexture!=null&&cameraTexture.width>16;
        view.startButton.interactable=prepared; view.sourceLabel.text=prepared?"카메라 준비 완료 · 영상 저장 안 함":"카메라 시작 실패";
        if(prepared)Screen.sleepTimeout=SleepTimeout.NeverSleep;
        if(!prepared) {ReleaseCamera();view.SetPreview(null);view.message.text="카메라 시작 실패\n사용 중인 다른 앱 종료 또는 카메라 전환";}
        else if (!resume) view.message.text = view.CameraGuide;
        changing=false;
    }
    private void SwitchCamera() { if(running||changing)return;cameraChosen=true;cameraIndex++;PrepareCamera(); }
    public void BeginWorkout() { if(prepared&&!running&&!changing&&!restoring&&!applicationPaused)StartCoroutine(BeginRoutine()); }
    private IEnumerator BeginRoutine()
    {
        string endpoint=HealthMonPoseClient.ConfiguredEndpoint;
#if UNITY_EDITOR
        if(VerificationEndpoint!=null)endpoint=VerificationEndpoint;
#endif
        if(!client.Configure(endpoint)) {view.message.text="훈련 준비 실패 · 잠시 후 재시도";yield break;}
        changing=true;view.startButton.interactable=false;view.message.text="훈련 준비 중…";
        view.SetSquatViewEditable(false);
        var binding=HealthMonPoseWorkoutSync.BindCurrentAccount(DateTime.UtcNow.ToString("o"));
        int version=generation;PoseSnapshot response=null;string error=null;
        var options = new PoseSessionRequest { exercise = HealthMonPoseView.Keys[selected] };
        if (options.exercise == "squat") options.squat_view = view.SquatView;
        yield return client.Json("POST","/sessions",options,(s,e)=>{response=s;error=e;});
        changing=false;
        if(version!=generation) { if(response!=null&&!string.IsNullOrEmpty(response.session_id))StartCoroutine(client.Json("DELETE","/sessions/"+response.session_id,null,(s,e)=>{}));yield break; }
        if(error!=null||response==null||string.IsNullOrEmpty(response.session_id)) {view.message.text=error??"훈련 시작 실패 · 재시도 필요";view.startButton.interactable=prepared;view.SetSquatViewEditable(true);yield break;}
        session=response.session_id;sequence=0;elapsed=0;paused=faulted=finishing=false;running=true;latest=response;
        workoutBinding=binding;resultEventId=null;
#if UNITY_EDITOR
        verificationFresh=false;
#endif
        view.ShowCamera(true);view.pauseLabel.text="일시정지";Apply(response);nextFrame=0;
    }
    private void Update()
    {
        if(view==null||!view.gameObject.activeInHierarchy||applicationPaused||restoring||restoreCamera)return;
        if(running&&!paused&&!faulted&&!finishing)elapsed+=Time.unscaledDeltaTime;
        if(!prepared||changing||finishing)return;
        bool fresh=cameraTexture!=null&&cameraTexture.isPlaying&&cameraTexture.didUpdateThisFrame;
        double stamp=Time.realtimeSinceStartupAsDouble;
        Texture2D source=null;
#if UNITY_EDITOR
        if(verificationFrame!=null) {fresh=verificationFresh;source=verificationFrame;stamp=verificationTimestamp;}
#endif
        if(!fresh||Time.unscaledTime<nextFrame||client.Busy)return;
        if(running&&(paused||faulted))return;
        nextFrame=Time.unscaledTime+.08f;
        if(source==null)source=CaptureUpright();
        if(source==null)return;
        if(!running) {view.SetPreview(source);return;}
#if UNITY_EDITOR
        verificationFresh=false;
#endif
        byte[] jpeg=source.EncodeToJPG(80);
        int version=generation;
        StartCoroutine(client.Frame(session,++sequence,stamp,jpeg,(snapshot,error)=>
        {
            if(version!=generation||!running)return;
            if(error!=null) {faulted=true;view.status.text="연결 확인";view.message.text=error;view.pauseLabel.text="연결 재시도";return;}
            Apply(snapshot);
        }));
    }
    private Texture2D CaptureUpright()
    {
        if(cameraTexture==null||cameraTexture.width<=16)return null;
        int width=cameraTexture.width,height=cameraTexture.height,angle=cameraTexture.videoRotationAngle;
        // Some phones ignore the requested camera size. Bound CPU rotation/JPEG work too.
        HealthMonPoseFrame.GetSize(width,height,angle,960,out int outWidth,out int outHeight);
        if(inputPixels==null||inputPixels.Length!=width*height)inputPixels=new Color32[width*height];
        if(outputPixels==null||outputPixels.Length!=outWidth*outHeight)outputPixels=new Color32[outWidth*outHeight];
        cameraTexture.GetPixels32(inputPixels);
        HealthMonPoseFrame.CopyUpright(inputPixels,outputPixels,width,height,angle,cameraTexture.videoVerticallyMirrored,outWidth,outHeight);
        if(frameTexture==null||frameTexture.width!=outWidth||frameTexture.height!=outHeight)
        {if(frameTexture!=null)Destroy(frameTexture);frameTexture=new Texture2D(outWidth,outHeight,TextureFormat.RGB24,false);}
        frameTexture.SetPixels32(outputPixels);frameTexture.Apply(false);return frameTexture;
    }
    private void Apply(PoseSnapshot snapshot)
    {
        if(snapshot==null)return;latest=snapshot;
        view.count.text=selected==2?$"왼팔 {snapshot.left_count}  /  오른팔 {snapshot.right_count}":snapshot.count+"회";
        view.status.text=paused?"일시정지":snapshot.phase;view.angles.text=snapshot.angle_text;
        view.message.text=paused?"일시정지 · 재개 시 준비 자세부터":snapshot.message;
        view.sourceLabel.text=$"{(snapshot.tracked?"관절 인식 중":"대상 확인 중")}  ·  {FormatTime(elapsed)}";
        if(!string.IsNullOrEmpty(snapshot.jpeg_base64))
        {
            try {if(resultTexture==null)resultTexture=new Texture2D(2,2);resultTexture.LoadImage(Convert.FromBase64String(snapshot.jpeg_base64));view.SetPreview(resultTexture);}catch(FormatException){view.message.text="영상 갱신 실패";}
        }
    }
    public void TogglePause()
    {
        if(!running||changing||finishing||restoring||applicationPaused)return;
        if(!prepared){restoreCamera=true;StartCoroutine(RestoreRoutine());return;}
        StartCoroutine(ControlPause());
    }
    private IEnumerator ControlPause()
    {
        changing=true;while(client.Busy)yield return null;
        bool target=faulted||!paused;
        yield return client.Json("POST","/sessions/"+session+"/control",new PoseControlRequest{command="pause",paused=target},(s,e)=>
        {if(e!=null){view.message.text=e;faulted=true;view.pauseLabel.text="연결 재시도";}else{paused=target;faulted=false;view.pauseLabel.text=paused?"훈련 재개":"일시정지";Apply(s);}});
        changing=false;
    }
    public void Retarget() {if(running&&!changing&&!finishing&&!restoring&&!applicationPaused)StartCoroutine(RetargetRoutine());}
    private IEnumerator RetargetRoutine()
    {
        changing=true;while(client.Busy)yield return null;
        yield return client.Json("POST","/sessions/"+session+"/control",new PoseControlRequest{command="retarget"},(s,e)=>{if(e!=null)view.message.text=e;else Apply(s);});changing=false;
    }
    public void Finish() {if(running&&!finishing&&!changing&&!restoring&&!applicationPaused)StartCoroutine(FinishRoutine());}
    private IEnumerator FinishRoutine()
    {
        finishing=true;while(client.Busy)yield return null;
        string finishError=null;
        yield return client.Json("DELETE","/sessions/"+session,null,(s,e)=>{finishError=e;if(s!=null)latest=s;});
        running=false;session=null;generation++;ReleaseCamera();view.ShowResult();
        view.resultCount.text=selected==2?$"왼팔 {latest?.left_count??0}\n오른팔 {latest?.right_count??0}":$"{latest?.count??0}회";
        view.resultTime.text=HealthMonPoseView.Names[selected]+"  ·  "+FormatTime(elapsed);
        view.resultNote.text=SaveRecord()?"기기 내 훈련 기록 저장 완료":"기록 저장 실패 · 기기 저장 공간 확인";
        if(finishError!=null)view.resultNote.text="연결 종료 전 확인된 기록 기준";
        QueueWorkout();
        finishing=false;
    }
    private void QueueWorkout()
    {
        if(workoutBinding==null||latest==null||string.IsNullOrEmpty(latest.session_id))return;
#if UNITY_EDITOR
        // Old footage verification must never modify the user's real account.
        if((verificationFrame!=null||VerificationHistoryIsolated)&&
           (CommonServerConnection.Instance.EnvironmentName!="test"||Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP")!="1"))return;
#endif
        var request=workoutBinding.request;
        request.event_id="pose-"+latest.session_id;
        request.occurred_at=DateTime.UtcNow.ToString("o");
        request.workout_type=latest.exercise=="curl"?"dumbbell":latest.exercise;
        request.actual=Math.Max(0,latest.count);
        request.duration_seconds=Mathf.Max(0,Mathf.FloorToInt(elapsed));
#if UNITY_EDITOR
        request.synthetic=verificationFrame!=null||VerificationHistoryIsolated;
#endif
        resultEventId=request.event_id;
        bool queued=HealthMonPoseWorkoutSync.Instance!=null&&HealthMonPoseWorkoutSync.Instance.Enqueue(workoutBinding);
        view.resultNote.text=queued?"훈련 기록 저장 · 성장 반영 대기":"성장 기록 저장 실패 · 저장 공간 확인";
        workoutBinding=null;
    }
    private void WorkoutRecorded(string id,WorkoutSubmissionResult result)
    {
        if(id!=resultEventId||view==null)return;
        view.resultNote.text=result.evaluation_status=="archive_only"?"훈련 기록 저장 · 지난 기록은 성장 반영 제외":
            result.evaluation_status=="recorded_unscored"?"훈련 기록 저장 · 목표와 측정 단위 확인":
            $"성장 반영 완료\n상체 {result.state.upper_body:0.#} · 하체 {result.state.lower_body:0.#}";
    }
    private void WorkoutDeferred(string id)
    {if(id==resultEventId&&view!=null)view.resultNote.text="훈련 기록 보관 · 연결 복구 후 자동 반영";}
    private bool SaveRecord()
    {
        if(latest==null||string.IsNullOrEmpty(latest.session_id))return false;
        try
        {
            string path=Path.Combine(Application.persistentDataPath,"pose-workouts.json");
#if UNITY_EDITOR
            if(verificationFrame!=null||VerificationHistoryIsolated)
            {
                path=Path.Combine(Directory.GetParent(Application.dataPath).FullName,"Temp/PoseVerification/pose-workouts.json");
                Directory.CreateDirectory(Path.GetDirectoryName(path));
            }
#endif
            var history=File.Exists(path)?JsonUtility.FromJson<PoseWorkoutHistory>(File.ReadAllText(path)):new PoseWorkoutHistory();
            if(history==null)history=new PoseWorkoutHistory();if(history.records==null)history.records=new List<PoseWorkoutRecord>();
            if(!history.records.Exists(x=>x.session_id==latest.session_id))history.records.Add(new PoseWorkoutRecord{session_id=latest.session_id,exercise=latest.exercise,count=latest.count,left_count=latest.left_count,right_count=latest.right_count,duration_seconds=elapsed,completed_at=DateTime.UtcNow.ToString("o")});
            if(history.records.Count>100)history.records.RemoveRange(0,history.records.Count-100);
            File.WriteAllText(path+".tmp",JsonUtility.ToJson(history,true));if(File.Exists(path))File.Replace(path+".tmp",path,null);else File.Move(path+".tmp",path);return true;
        }catch(Exception e) when(e is IOException||e is UnauthorizedAccessException||e is ArgumentException){return false;}
    }
    public void Close()
    {
        if(running){Finish();return;} if(changing)return;
        generation++;ReleaseCamera();view.gameObject.SetActive(false);
        RestoreOrientation();
    }
    private void ReleaseCamera()
    {prepared=false;Screen.sleepTimeout=previousSleepTimeout;if(cameraTexture!=null){cameraTexture.Stop();Destroy(cameraTexture);cameraTexture=null;}}
    private void OnApplicationPause(bool value)
    {
        applicationPaused=value;
        if(value)
        {
            // Don't send or count background frames. Keep confirmed counts until the server acknowledges pause.
            if(cameraTexture==null&&!running)return;
            restoreCamera=true;ReleaseCamera();view.SetPreview(null);
            if(running){paused=true;view.status.text="일시정지";view.pauseLabel.text="훈련 재개";}
        }
        else if(restoreCamera&&!restoring&&view.gameObject.activeInHierarchy)StartCoroutine(RestoreRoutine());
    }
    private IEnumerator RestoreRoutine()
    {
        restoring=true;
        while(changing||finishing||client.Busy)yield return null;
        if(!view.gameObject.activeInHierarchy||!view.cameraPage.activeSelf){restoreCamera=restoring=false;yield break;}
        if(running)
        {
            paused=true;
            yield return client.Json("POST","/sessions/"+session+"/control",new PoseControlRequest{command="pause",paused=true},(s,e)=>
            {faulted=e!=null;if(s!=null)Apply(s);});
        }
        yield return PrepareRoutine(running);
        restoreCamera=false;restoring=false;
        if(running)
        {
            view.pauseLabel.text=!prepared?"카메라 재시도":faulted?"연결 재시도":"훈련 재개";
            view.status.text="일시정지";
            if(prepared)view.message.text=faulted?"연결 재시도 필요 · 완료 횟수 유지":"카메라 복구 완료 · 준비 자세에서 훈련 재개";
        }
    }
    private void OnDestroy()
    {
        if(HealthMonPoseWorkoutSync.Instance!=null){HealthMonPoseWorkoutSync.Instance.Recorded-=WorkoutRecorded;HealthMonPoseWorkoutSync.Instance.Deferred-=WorkoutDeferred;}
        generation++;ReleaseCamera();RestoreOrientation();if(client!=null)client.Abort();if(frameTexture!=null)Destroy(frameTexture);if(resultTexture!=null)Destroy(resultTexture);
    }
    private void RestoreOrientation()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        if(orientationCaptured){Screen.orientation=previousOrientation;orientationCaptured=false;}
        foreach(var ar in suspendedArSessions)if(ar!=null)ar.enabled=true;
        suspendedArSessions.Clear();
#endif
    }
    private static string FormatTime(float value) {int seconds=Mathf.FloorToInt(value);return $"{seconds/60:00}:{seconds%60:00}";}
}
