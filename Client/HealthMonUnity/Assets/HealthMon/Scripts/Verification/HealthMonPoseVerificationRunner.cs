#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[Serializable] public sealed class PoseVerificationConfig
{ public bool isolated_fixture, design_only, verify_edges, verify_virtual_camera, verify_lifecycle; public string output; public PoseVerificationCase[] cases; }
[Serializable] public sealed class PoseVerificationCase { public int exercise; public string frames; public float fps=10; }
[Serializable] public sealed class PoseVerificationResult
{ public string status="running",error,camera_result; public string[] camera_devices; public int checks,frames,runtime_exceptions; public List<int> counts=new List<int>(); }

[InitializeOnLoad]
public static class HealthMonPoseVerification
{
    static HealthMonPoseVerification()
    {
        EditorApplication.playModeStateChanged+=state=>
        {
            if(state!=PlayModeStateChange.EnteredPlayMode||!SessionState.GetBool("PoseVerify",false))return;
            SessionState.SetBool("PoseVerify",false);new GameObject("Pose verification").AddComponent<HealthMonPoseVerificationRunner>();
        };
    }
    [MenuItem("HealthMon/Pose/Run native verification")]
    public static void Run()
    {
        var root=Directory.GetParent(Application.dataPath).Parent.Parent.FullName;
        var config=JsonUtility.FromJson<PoseVerificationConfig>(File.ReadAllText(Path.Combine(root,".runtime/pose-verification.json")));
        if(config==null||!config.isolated_fixture||string.IsNullOrWhiteSpace(config.output))throw new Exception("Explicit isolated pose verification config required");
        if(EditorApplication.isPlaying)throw new Exception("Exit Play Mode first");
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        SessionState.SetBool("PoseVerify",true);EditorApplication.isPlaying=true;
    }
}

public sealed class HealthMonPoseVerificationRunner : MonoBehaviour
{
    private PoseVerificationConfig config;
    private PoseVerificationResult result=new PoseVerificationResult();
    private void Start()
    {
        Application.logMessageReceived+=Log;
        var root=Directory.GetParent(Application.dataPath).Parent.Parent.FullName;
        config=JsonUtility.FromJson<PoseVerificationConfig>(File.ReadAllText(Path.Combine(root,".runtime/pose-verification.json")));
        Directory.CreateDirectory(config.output);StartCoroutine(Guard(Run()));
    }
    private void Log(string condition,string stack,LogType type) {if(type==LogType.Exception)result.runtime_exceptions++;}
    private IEnumerator Guard(IEnumerator work)
    {
        while(true)
        {
            object item;
            try { if(!work.MoveNext())break;item=work.Current; }
            catch(Exception ex){result.status="failed";result.error=ex.ToString();Write();yield break;}
            yield return item;
        }
        result.status=result.runtime_exceptions==0?"passed":"failed";Write();
    }
    private IEnumerator Run()
    {
        yield return new WaitForSecondsRealtime(2);
        var screen=FindAnyObjectByType<HealthMonPoseScreen>();Check(screen!=null,"screen installed");
        screen.VerificationHistoryIsolated=true;
        var entry=GameObject.Find("UI/Canvas/BottomNavV2/TopRow/PoseButton").GetComponent<Button>();
        entry.onClick.Invoke();yield return null;Check(screen.view.selection.activeSelf,"navigation opens selection");
        yield return Capture("01-selection");
        // The source is explicitly labelled as verification footage; no synthetic pose or counter result.
        var texture=new Texture2D(2,2);
        if(config.design_only)
        {
            screen.SelectExercise(0);screen.SetVerificationFrame(texture,0);screen.PrepareCamera();yield return new WaitForSecondsRealtime(.5f);
            yield return Capture("02-prepare");yield break;
        }
        foreach(var test in config.cases)
        {
            screen.Open();screen.SelectExercise(test.exercise);
            string[] frames=Directory.GetFiles(test.frames,"*.jpg");Array.Sort(frames,StringComparer.Ordinal);Check(frames.Length>10,"real frame fixture exists");
            texture.LoadImage(File.ReadAllBytes(frames[0]));screen.SetVerificationFrame(texture,0);screen.PrepareCamera();yield return new WaitForSecondsRealtime(.2f);
            screen.BeginWorkout();yield return Wait(()=>screen.IsRunning,20,"session start");
            for(int i=0;i<frames.Length;i++)
            {
                texture.LoadImage(File.ReadAllBytes(frames[i]));screen.SetVerificationFrame(texture,i/(double)test.fps);
                int wanted=i+1;yield return Wait(()=>screen.Latest!=null&&screen.Latest.sequence>=wanted,15,"real inference frame "+i);
                result.frames++;
                if(i==frames.Length/2)yield return Capture("03-live-"+HealthMonPoseView.Keys[test.exercise]);
            }
            Check(screen.Latest.count>0,"completed real repetitions: "+HealthMonPoseView.Keys[test.exercise]);
            int before=screen.Latest.count;screen.TogglePause();yield return Wait(()=>screen.IsPaused,15,"pause acknowledged");
            yield return Capture("04-paused-"+HealthMonPoseView.Keys[test.exercise]);
            Check(screen.Latest.count==before,"pause retains count");screen.TogglePause();yield return Wait(()=>!screen.IsPaused&&!screen.Client.Busy,15,"resume acknowledged");
            screen.Finish();yield return Wait(()=>!screen.IsRunning&&screen.view.resultPage.activeSelf,15,"finish");
            Check(screen.Latest.count==before,"finish retains count");result.counts.Add(before);
            yield return Capture("05-result-"+HealthMonPoseView.Keys[test.exercise]);screen.Close();
            Check(!screen.view.gameObject.activeSelf,"close returns to previous screen");
        }
        if(config.verify_edges)
        {
            screen.Open();screen.SelectExercise(0);
            var blank=new Texture2D(160,120,TextureFormat.RGB24,false);blank.SetPixels32(new Color32[160*120]);blank.Apply();
            screen.SetVerificationFrame(blank,0);screen.PrepareCamera();yield return Wait(()=>!screen.IsTransitioning,10,"prepare verification source");
            yield return Capture("02-prepare");
            screen.VerificationEndpoint="not-a-url";screen.BeginWorkout();yield return null;
            Check(!screen.IsRunning&&screen.view.message.text.Contains("준비 실패"),"invalid configuration gives player guidance");
            screen.VerificationEndpoint="http://127.0.0.1:18096";screen.BeginWorkout();
            yield return Wait(()=>!screen.IsTransitioning,16,"offline start returns");
            Check(!screen.IsRunning&&screen.view.message.text.Contains("재시도"),"offline start stays in preparation");
            yield return Capture("07-server-offline");
            screen.VerificationEndpoint=null;screen.BeginWorkout();yield return Wait(()=>screen.IsRunning,20,"automatic connection starts session");
            screen.SetVerificationFrame(blank,0);yield return Wait(()=>screen.Latest.sequence==1,15,"blank real inference");
            Check(screen.Latest.count==0&&!screen.Latest.tracked,"blank image cannot invent repetitions");
            screen.Client.Configure("http://127.0.0.1:18096");screen.SetVerificationFrame(blank,.1);
            yield return Wait(()=>screen.HasConnectionError,16,"mid-workout connection loss");
            Check(screen.Latest.count==0,"loss keeps confirmed count");yield return Capture("08-disconnected");
            screen.Client.Configure("http://127.0.0.1:18095");screen.TogglePause();
            yield return Wait(()=>screen.IsPaused&&!screen.HasConnectionError&&!screen.IsTransitioning,16,"recovery pauses safely");
            screen.TogglePause();yield return Wait(()=>!screen.IsPaused&&!screen.IsTransitioning,16,"recovery resume");
            screen.SetVerificationFrame(blank,.3);yield return Wait(()=>screen.Latest.sequence==3,15,"fresh frame after recovery");
            screen.Retarget();yield return Wait(()=>!screen.IsTransitioning,16,"retarget");
            screen.Finish();screen.Finish();yield return Wait(()=>!screen.IsRunning&&!screen.IsTransitioning,16,"finish once");
            var history=JsonUtility.FromJson<PoseWorkoutHistory>(File.ReadAllText(Path.Combine(Directory.GetParent(Application.dataPath).FullName,"Temp/PoseVerification/pose-workouts.json")));
            Check(history.records.FindAll(record=>record.session_id==screen.Latest.session_id).Count==1,"one local record per session");
            screen.Close();screen.SetVerificationFrame(null,0);screen.Open();screen.PrepareCamera();
            yield return Wait(()=>!screen.IsTransitioning,12,"physical camera preparation");
            result.camera_result=WebCamTexture.devices.Length==0?"no_camera_device":screen.view.startButton.interactable?"camera_preview_ready":"camera_unavailable_or_permission_denied";
            result.camera_devices=Array.ConvertAll(WebCamTexture.devices,device=>device.name);
            Check(screen.view.startButton.interactable||!screen.IsRunning,"camera unavailable does not start counting");
            yield return Capture("09-camera-preparation");screen.Close();Destroy(blank);
        }
        if(config.verify_virtual_camera)
        {
            screen.Open();screen.SelectExercise(0);screen.SetVerificationFrame(null,0);screen.PrepareCamera();
            yield return Wait(()=>!screen.IsTransitioning,12,"virtual camera opens");
            Check(screen.view.startButton.interactable,"WebCamTexture receives real video frames");
            result.camera_devices=Array.ConvertAll(WebCamTexture.devices,device=>device.name);
            yield return Wait(()=>screen.view.preview.enabled&&screen.view.preview.texture!=null,6,"camera preview rendered before capture");
            yield return Capture("10-webcam-preview");
            screen.VerificationEndpoint=null;screen.BeginWorkout();yield return Wait(()=>screen.IsRunning,20,"camera session start");
            yield return Wait(()=>screen.Latest!=null&&screen.Latest.count>0,30,"WebCamTexture -> JPEG -> actual pose -> counted rep");
            yield return Capture("11-webcam-live");result.counts.Add(screen.Latest.count);result.frames=screen.Latest.sequence;
            if(config.verify_lifecycle)
            {
                while(screen.Client.Busy)yield return null;
                int confirmed=screen.Latest.count,seq=screen.Latest.sequence;
                screen.SendMessage("OnApplicationPause",true);
                yield return new WaitForSecondsRealtime(.5f);
                Check(screen.IsPaused&&screen.Latest.sequence==seq,"background sends no new frames");
                Check(screen.Latest.count==confirmed,"background preserves confirmed count");
                screen.SendMessage("OnApplicationPause",false);
                yield return Wait(()=>!screen.IsTransitioning&&screen.IsPaused,15,"camera restored paused");
                Check(!screen.HasConnectionError&&screen.Latest.paused,"server acknowledges background pause");
                yield return Capture("13-camera-restored");
                screen.TogglePause();yield return Wait(()=>!screen.IsPaused&&!screen.IsTransitioning,15,"explicit resume after background");
                yield return Wait(()=>screen.Latest.sequence>seq,15,"fresh camera frame after resume");
                Check(screen.Latest.count>=confirmed,"resume preserves counted repetitions");
            }
            result.camera_result="OBS virtual camera: public video -> production WebCamTexture -> real RTMPose";
            screen.Finish();yield return Wait(()=>!screen.IsRunning&&!screen.IsTransitioning,16,"camera end and release");
            yield return Capture("12-webcam-result");screen.Close();
        }
        Destroy(texture);
        screen.Open();yield return Capture("06-final-selection");
    }
    private IEnumerator Wait(Func<bool> condition,float seconds,string name)
    {
        float deadline=Time.realtimeSinceStartup+seconds;
        while(!condition())
        {
            if(Time.realtimeSinceStartup>deadline){result.status="failed";result.error="Timed out: "+name;Write();StopAllCoroutines();yield break;}
            yield return null;
        }
        result.checks++;
    }
    private IEnumerator Capture(string name)
    {
        yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(config.output,name+".png"));yield return new WaitForSecondsRealtime(.15f);
    }
    private void Check(bool condition,string message) {if(!condition)throw new Exception(message);result.checks++;}
    private void Write() {File.WriteAllText(Path.Combine(config.output,"result.json"),JsonUtility.ToJson(result,true));Debug.Log("HEALTHMON_POSE_NATIVE_"+result.status.ToUpperInvariant());}
    private void OnDestroy(){Application.logMessageReceived-=Log;}
}
#endif
