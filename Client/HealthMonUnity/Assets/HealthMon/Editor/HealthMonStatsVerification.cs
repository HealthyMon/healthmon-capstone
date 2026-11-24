using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using Healthmon.Beta;
using Healthmon.Common;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Networking;
using TMPro;

[InitializeOnLoad]
public static class HealthMonStatsVerification
{
    static HealthMonStatsVerification() { EditorApplication.playModeStateChanged += s => {
        if(s==PlayModeStateChange.EnteredPlayMode && SessionState.GetBool("HM.StatsCheck",false)) {
            SessionState.SetBool("HM.StatsCheck",false);new GameObject("Stats verification").AddComponent<HealthMonStatsRunner>();
        }
    }; }
    public static void Run() {
        if(Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP")!="1" || string.IsNullOrEmpty(Environment.GetEnvironmentVariable("HEALTHMON_POSE_QUEUE_TEST_PATH")))throw new Exception("Isolated preferences and queue required");
        PlayerPrefs.SetInt("HealthMon_Offline_Mode_v1",0);PlayerPrefs.Save();
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        SessionState.SetBool("HM.StatsCheck",true);EditorApplication.isPlaying=true;
    }
}
public sealed class HealthMonStatsRunner : MonoBehaviour
{
    [Serializable] class Sample { public string label,status_text,combat;public PetState state; }
    [Serializable] class Report { public bool passed;public string error; public string input="Synthetic workout counts and meal values; production UI, API and PostgreSQL";public List<Sample> samples=new List<Sample>(); public List<string> checks=new List<string>(),screenshots=new List<string>(),runtime_errors=new List<string>(); }
    Report report=new Report();string output;EditorWindow game;object group;int originalIndex,customIndex=-1;
    readonly BindingFlags flags=BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic;
    T Field<T>(object obj,string name)=>(T)obj.GetType().GetField(name,flags).GetValue(obj);
    void Check(bool value,string name){if(!value)throw new Exception(name);report.checks.Add(name);}
    async Task Until(Func<bool> condition,int seconds,string error){var deadline=DateTime.UtcNow.AddSeconds(seconds);while(!condition()){if(DateTime.UtcNow>deadline)throw new Exception(error);await Task.Delay(100);}}
    void Observe(string message,string trace,LogType type){if(type==LogType.Error||type==LogType.Exception)report.runtime_errors.Add(message+"\n"+trace);}
    CommonServerConnection c;UIManager ui;HealthMonPoseScreen pose;
    async Task SampleState(string name){
        ui.ShowStatus();await Task.Delay(400);
        var view=FindAnyObjectByType<PetExperienceUI>().StatusView;
        view.RefreshNow();
        var text=string.Join(" / ",Enumerable.Range(0,6).Select(i=>HealthMonStatusSnapshot.AxisNames[i]+" "+view.AxisText(i)))+" / 에너지 균형 "+view.EnergyText;
        var s=c.LatestState;PetCombatStatsSource.TryGetCurrent(out var combat,out _);
        var scores=new[]{s.upper_body,s.affinity,s.activity,s.nutrition,s.initiative,s.lower_body};
        Check(Enumerable.Range(0,6).All(i=>view.AxisText(i)==HealthMonStatusSnapshot.Number(scores[i])),name+" Unity radar labels equal server lifestyle stats");
        Check(view.CurrentSnapshot.Energy==s.energy_balance,name+" Unity energy gauge equals server meal stats");
        var values=new[]{combat.ATK,combat.DEF,combat.RES,combat.SPD,combat.LUK};
        Check(Enumerable.Range(0,5).All(i=>view.CombatText(i)==values[i].ToString()),name+" Unity combat slots equal battle values");
        Check(combat.StatusText==PetCombatStats.FromState(s).StatusText,name+" combat projection equals current state");
        report.samples.Add(new Sample{label=name,state=JsonUtility.FromJson<PetState>(JsonUtility.ToJson(s)),status_text=text,combat=combat.StatusText});
        await Capture(name+".png");
    }
    async Task<string> Post(string suffix,string body){
        await Until(()=>!c.Api.IsBusy,30,"API busy");
        using(var req=new UnityWebRequest(c.BaseUrl+"/pets/"+c.Api.PetId+suffix,"POST")){
            req.uploadHandler=new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));req.downloadHandler=new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type","application/json");req.SetRequestHeader("Authorization","Bearer "+Environment.GetEnvironmentVariable("HEALTHMON_USER_TOKEN"));
            var op=req.SendWebRequest();await Until(()=>op.isDone,30,"POST timeout");
            Check(req.result==UnityWebRequest.Result.Success,"Production POST "+suffix);return req.downloadHandler.text;
        }
    }
    async Task Refresh(){c.RefreshState();await Until(()=>!c.Api.IsStateBusy,30,"State refresh");await Task.Delay(250);}
    async Task Exercise(int index,float upper,float lower){
        pose.Open();pose.SelectExercise(index);var texture=new Texture2D(2,2);pose.VerificationHistoryIsolated=true;
        pose.VerificationEndpoint="http://127.0.0.1:18132";pose.SetVerificationFrame(texture,0);pose.PrepareCamera();
        await Until(()=>!pose.IsTransitioning,20,"Prepare pose");pose.BeginWorkout();await Until(()=>pose.IsRunning,20,"Begin pose fixture");
        var binding=Field<HealthMonPoseWorkoutSync.Entry>(pose,"workoutBinding");
        Check(binding!=null,"Workout bound before training");pose.Finish();await Until(()=>!pose.IsTransitioning&&!pose.IsRunning,20,"Finish pose fixture");
        await Until(()=>c.LatestState.upper_body==upper&&c.LatestState.lower_body==lower&&HealthMonPoseWorkoutSync.Instance.PendingCount==0,35,"Pose result did not change stats");
        Check(pose.view.resultNote.text.Contains("성장 반영 완료"),"Result acknowledges server growth");
        await Capture("pose-"+index+"-recorded.png");
        WorkoutSubmissionResult retry=null;string error=null;await Until(()=>!c.Api.IsBusy,30,"Retry busy");
        var previous=JsonUtility.ToJson(c.LatestState);
        c.Api.SubmitPoseWorkout(binding.request,result=>retry=result,f=>error=f.ToString());
        await Until(()=>retry!=null||error!=null,30,"Retry response");
        Check(error==null&&retry.duplicate,"Same pose session is idempotent");
        Check(previous==JsonUtility.ToJson(c.LatestState),"Duplicate leaves all stats and rewards unchanged");
        pose.Close();await SampleState("after-"+HealthMonPoseView.Keys[index]);Destroy(texture);
    }
    async void Start(){
        output=Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");Directory.CreateDirectory(output);Application.runInBackground=true;Application.targetFrameRate=30;Application.logMessageReceived+=Observe;
        try{
            SetSize(720,1280);
            await Until(()=>CommonServerConnection.Instance!=null&&CommonServerConnection.Instance.IsConnected,60,"Connect isolated backend");c=CommonServerConnection.Instance;
            Check(c.EnvironmentName=="test"&&c.OwnerId=="stat-review-owner"&&c.ServerInstanceId=="stat-review-20261124","Isolated test identity");
            await Until(()=>!c.Api.IsBusy&&!c.Api.IsStateBusy,30,"Initial state");
            ui=FindAnyObjectByType<UIManager>();pose=FindAnyObjectByType<HealthMonPoseScreen>(FindObjectsInactive.Include);
            await SampleState("before");
            await Exercise(0,50,52);await Exercise(1,52,52);await Exercise(2,53,52);
            Check(c.LatestState.activity==50,"Activity remains weekly, not per-workout");
            var now=DateTime.UtcNow.ToString("o");
            string watch="{\"event_id\":\"watch-fixture\",\"occurred_at\":\""+now+"\",\"started_at\":\""+now+"\",\"workout_type\":\"walking\",\"actual\":6000,\"unit\":\"steps\",\"source\":\"watch\",\"synthetic\":true}";
            await Post("/workouts",watch);await Refresh();Check(c.LatestState.lower_body==53,"Watch record obeys daily lower-body cap");await SampleState("after-watch");
            string meal="{\"event_id\":\"meal-fixture\",\"occurred_at\":\""+DateTime.UtcNow.ToString("o")+"\",\"food_name\":\"Stat verification meal\",\"meal_type\":\"breakfast\",\"confirmed\":true,\"quantity_confirmed\":true,\"grams\":300,\"carbohydrate_g\":55,\"protein_g\":20,\"fat_g\":12,\"vegetable_fruit_g\":80,\"kcal\":450,\"source\":\"user\",\"synthetic\":true}";
            await Post("/meals",meal);await Refresh();Check(c.LatestState.nutrition==52&&c.LatestState.energy_balance==0,"Balanced meal updates nutrition, balanced energy remains zero");await SampleState("after-meal");
            var prior=JsonUtility.ToJson(c.LatestState);await Post("/meals",meal);await Refresh();Check(prior==JsonUtility.ToJson(c.LatestState),"Duplicate meal leaves state unchanged");
            var sync=HealthMonPoseWorkoutSync.Instance;sync.enabled=false;
            var pending=HealthMonPoseWorkoutSync.BindCurrentAccount(DateTime.UtcNow.ToString("o"));pending.request.event_id="pose-reconnect-fixture";pending.request.occurred_at=DateTime.UtcNow.ToString("o");pending.request.workout_type="squat";pending.request.actual=50;pending.request.synthetic=true;
            Check(sync.Enqueue(pending),"Pending workout persisted before send");
            var foreign=JsonUtility.FromJson<HealthMonPoseWorkoutSync.Entry>(JsonUtility.ToJson(pending));foreign.pet="another-pet";foreign.request.event_id="pose-other-pet-fixture";
            Check(sync.Enqueue(foreign)&&!HealthMonPoseWorkoutSync.Matches(foreign,c),"Pending queue isolates selected pet");
            Destroy(sync);await Task.Delay(200);c.gameObject.AddComponent<HealthMonPoseWorkoutSync>();
            await Until(()=>HealthMonPoseWorkoutSync.Instance.PendingCount==1,30,"Reloaded queue retry");
            Check(c.LatestState.lower_body==53,"Pending retry does not bypass daily cap");
            Check(report.runtime_errors.Count==0,"No Unity runtime errors");report.passed=true;
        }catch(Exception ex){report.error=ex.ToString();await Capture("failure.png");}
        finally{
            if(game!=null)game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,originalIndex);
            if(customIndex>=0)group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
            Application.logMessageReceived-=Observe;File.WriteAllText(Path.Combine(output,"unity-stats-report.json"),JsonUtility.ToJson(report,true));
            HealthMonAspectVerification.Finish(report.passed?0:1);
        }
    }
    async Task Capture(string name){await Task.Delay(300);ScreenCapture.CaptureScreenshot(Path.Combine(output,name));await Task.Delay(500);report.screenshots.Add(name);}
    void CheckBounds(RectTransform rect,string description)
    {
        var corners=new Vector3[4];rect.GetWorldCorners(corners);
        var canvas=rect.GetComponentInParent<Canvas>();var camera=canvas.renderMode==RenderMode.ScreenSpaceOverlay?null:canvas.worldCamera;
        Check(corners.Select(p=>RectTransformUtility.WorldToScreenPoint(camera,p)).All(p=>p.x>=-2&&p.y>=-2&&p.x<=Screen.width+2&&p.y<=Screen.height+2),description);
    }
    void SetSize(int width,int height)
    {
        var assembly=typeof(EditorWindow).Assembly;
        if(game==null)
        {
            game=EditorWindow.GetWindow(assembly.GetType("UnityEditor.GameView"));game.Show();game.Focus();
            originalIndex=(int)game.GetType().GetProperty("selectedSizeIndex",flags).GetValue(game);
            var type=assembly.GetType("UnityEditor.GameViewSizes");
            var singleton=typeof(ScriptableSingleton<>).MakeGenericType(type);
            var sizes=singleton.GetProperty("instance",BindingFlags.Public|BindingFlags.Static|BindingFlags.FlattenHierarchy).GetValue(null);
            group=type.GetMethod("GetGroup",flags).Invoke(sizes,new[]{Enum.Parse(assembly.GetType("UnityEditor.GameViewSizeGroupType"),"Android")});
        }
        if(customIndex>=0)group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
        var size=Activator.CreateInstance(assembly.GetType("UnityEditor.GameViewSize"),flags,null,new object[]{Enum.Parse(assembly.GetType("UnityEditor.GameViewSizeType"),"FixedResolution"),width,height,"HealthMon multi-food verification"},null);
        customIndex=(int)group.GetType().GetMethod("GetBuiltinCount",flags).Invoke(group,null)+(int)group.GetType().GetMethod("GetCustomCount",flags).Invoke(group,null);
        group.GetType().GetMethod("AddCustomSize",flags).Invoke(group,new[]{size});
        game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,customIndex);game.Repaint();
    }
}
