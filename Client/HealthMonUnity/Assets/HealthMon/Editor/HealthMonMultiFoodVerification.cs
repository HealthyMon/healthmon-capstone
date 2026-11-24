using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

// Opt-in integration check. Uses an isolated test owner/database and a real photo.
[InitializeOnLoad]
public static class HealthMonMultiFoodVerification
{
    static HealthMonMultiFoodVerification()
    {
        EditorApplication.playModeStateChanged += state => {
            if(state != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool("HM.MultiFoodCheck",false))return;
            SessionState.SetBool("HM.MultiFoodCheck",false);
            Debug.Log("MultiFood verification entered Play mode");
            new GameObject("Multi-food verification").AddComponent<HealthMonMultiFoodRunner>();
        };
    }
    public static void Run()
    {
        if(Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP")!="1")throw new InvalidOperationException("Exact preferences backup required");
        PlayerPrefs.SetInt("HealthMon_Offline_Mode_v1",0);PlayerPrefs.Save();
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        var game=EditorWindow.GetWindow(typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView"));
        game.Show();game.Focus();EditorApplication.isPaused=false;
        SessionState.SetBool("HM.MultiFoodCheck",true);EditorApplication.isPlaying=true;
    }
}

public sealed class HealthMonMultiFoodRunner : MonoBehaviour
{
    [Serializable] class Report {
        public bool passed;
        public string error,analysis_id,source_id,provenance;
        public int food_count;
        public float confirmed_grams;
        public List<string> checks=new List<string>(), screenshots=new List<string>(), runtime_errors=new List<string>();
    }
    Report report=new Report();string output;
    EditorWindow game;object group;int originalIndex,customIndex=-1;
    readonly BindingFlags flags=BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic;
    T Field<T>(object target,string name)=>(T)target.GetType().GetField(name,flags).GetValue(target);
    void Check(bool condition,string description){if(!condition)throw new Exception(description);report.checks.Add(description);}
    async Task Until(Func<bool> condition,int seconds,string error){var deadline=DateTime.UtcNow.AddSeconds(seconds);while(!condition()){if(DateTime.UtcNow>deadline)throw new Exception(error);await Task.Delay(100);}}
    void Observe(string message,string trace,LogType type){if(type==LogType.Error||type==LogType.Exception)report.runtime_errors.Add(message+"\n"+trace);}
    async void Start()
    {
        output=Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");Directory.CreateDirectory(output);
        Application.runInBackground=true;Application.targetFrameRate=30;Application.logMessageReceived+=Observe;
        Debug.Log("MultiFood verification started");
        try
        {
            SetSize(720,1280);
            await Until(()=>CommonServerConnection.Instance!=null&&CommonServerConnection.Instance.IsConnected,60,"Isolated backend connection timed out");
            var connection=CommonServerConnection.Instance;
            Check(connection.EnvironmentName=="test"&&connection.OwnerId=="vision-review-owner"&&connection.ServerInstanceId=="vision-review-20261124","Isolated test identity verified");
            await Until(()=>!connection.Api.IsBusy&&!connection.Api.IsStateBusy,30,"Initial state timeout");
            await Task.Delay(1000);
            // This check deliberately supplies a file. Do not open a desktop virtual webcam.
            foreach(var camera in FindObjectsByType<ARFoodCameraCapture>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            { camera.StopPreview();camera.enabled=false; }
            var ui=FindAnyObjectByType<UIManager>(FindObjectsInactive.Include);ui.ShowFoodScan();
            var food=FindAnyObjectByType<FoodScanPrototype>(FindObjectsInactive.Include);
            await Until(()=>Field<TMP_InputField>(food,"gramsInput")!=null,20,"Food controls missing");
            food.EnableSyntheticConsumptionFixture();
            food.UseImage(File.ReadAllBytes(Environment.GetEnvironmentVariable("HEALTHMON_FOOD_TEST_PHOTO")));
            food.AnalyzeFood();
            await Until(()=>food.LastAnalysis!=null||food.HasFoodFailure,300,"Actual food inference timed out");
            await Until(()=>!connection.Api.IsBusy,30,"Analysis busy timeout");
            Check(!food.HasFoodFailure&&food.LastAnalysis.vision!=null,"Actual multi-food response reached Unity");
            var analysis=food.LastAnalysis;report.analysis_id=analysis.analysis_id;report.provenance=analysis.provenance;
            Check(analysis.provenance=="real"&&!analysis.IsSynthetic,"Analysis is real inference; consumed quantities are test inputs");
            var panel=Field<MainFoodResultsPanel>(food,"multiResults");var scroll=Field<ScrollRect>(food,"confirmationScroll");
            report.food_count=analysis.vision.foods.Length;
            Check(panel.HasPortions&&Field<GameObject>(food,"resultView").activeInHierarchy,"Production result view displays all food regions");
            var checkedQuantity=Field<Toggle>(food,"quantityConfirmed");
            Check(!checkedQuantity.isOn,"Photo estimates are not silently confirmed");
            food.SelectMealType("lunch");food.ConfirmFood();
            Check(!food.IsConfirming&&food.LastConfirmation==null,"Unconfirmed quantities cannot be saved");
            // Exercise the actual edit buttons and input fields, not a fabricated response.
            var cards=Field<RectTransform>(panel,"cards");
            cards.GetChild(0).Find("FoodActions").GetComponentsInChildren<Button>()[0].onClick.Invoke();await Task.Delay(100);
            var nameEditor=Field<RectTransform>(panel,"editor");nameEditor.GetComponentInChildren<TMP_InputField>().text="rice";
            nameEditor.GetComponentsInChildren<Button>().First(b=>b.GetComponentInChildren<TMP_Text>().text=="검색").onClick.Invoke();await Task.Delay(100);
            var matches=nameEditor.Find("Matches").GetComponentsInChildren<Button>();Check(matches.Length>0,"Food catalog search returns selectable names");
            matches[0].onClick.Invoke();await Task.Delay(100);
            cards.GetChild(0).Find("FoodActions").GetComponentsInChildren<Button>()[1].onClick.Invoke();await Task.Delay(100);
            var weightEditor=Field<RectTransform>(panel,"editor");weightEditor.GetComponentInChildren<TMP_InputField>().text="125.5";
            weightEditor.GetComponentsInChildren<Button>().First(b=>b.GetComponentInChildren<TMP_Text>().text=="적용").onClick.Invoke();await Task.Delay(100);
            var items=panel.ConfirmedItems();var total=panel.TotalGrams;
            Check(Mathf.Abs(items[0].grams-125.5f)<.001f&&!checkedQuantity.isOn,"Edited quantity is reflected and requires reconfirmation");
            Check(Mathf.Abs(float.Parse(Field<TMP_InputField>(food,"gramsInput").text,System.Globalization.CultureInfo.InvariantCulture)-total)<.01f,"Combined quantity matches all food cards");
            foreach(int height in new[]{1280,1440})
            {
                SetSize(720,height);await Task.Delay(900);Canvas.ForceUpdateCanvases();scroll.verticalNormalizedPosition=1;
                await Capture(height+"-overview.png");
                CheckBounds(Field<Button>(food,"saveButton").GetComponent<RectTransform>(),"Save button fits "+height);
                var photo=Field<RectTransform>(panel,"photoImage");
                var texture=photo.GetComponent<RawImage>().texture;
                Check(Mathf.Abs(photo.rect.width/photo.rect.height-(float)texture.width/texture.height)<.02f,"Photo aspect ratio preserved "+height);
                // Bring the first card into view using the live scroll content's layout.
                var first=(RectTransform)cards.GetChild(0);var corner=new Vector3[4];first.GetWorldCorners(corner);
                float offset=-scroll.content.InverseTransformPoint(corner[1]).y;
                float available=scroll.content.rect.height-scroll.viewport.rect.height;
                scroll.verticalNormalizedPosition=Mathf.Clamp01(1-offset/available);
                await Capture(height+"-food-card.png");
                scroll.verticalNormalizedPosition=0;await Capture(height+"-confirmation-bottom.png");
                CheckBounds(Field<Toggle>(food,"kcalConfirmed").GetComponent<RectTransform>(),"Final confirmation is reachable "+height);
            }
            checkedQuantity.isOn=true;Field<Toggle>(food,"kcalConfirmed").isOn=true;
            food.ConfirmFood();food.ConfirmFood();
            await Until(()=>food.LastConfirmation!=null||food.HasFoodFailure,30,"Food save timeout");
            await Until(()=>!connection.Api.IsBusy&&!connection.Api.IsStateBusy,30,"State refresh timeout");
            var saved=food.LastConfirmation;
            Check(!food.HasFoodFailure&&saved.stored&&!saved.duplicate,"Edited meal saved through the production UI");
            report.source_id=saved.source_id;report.confirmed_grams=total;
            FoodConfirmationResult duplicate=null;
            connection.Api.ConfirmFood(analysis.analysis_id,analysis.candidates[0].candidate_id,total,r=>duplicate=r,
                mealType:"lunch",kcalReconfirmed:true,syntheticFixture:true,items:items);
            await Until(()=>duplicate!=null,30,"Repeated save timeout");
            Check(duplicate.duplicate&&duplicate.source_id==saved.source_id&&duplicate.state_version==saved.state_version,"Repeated submission reuses one meal and one reward");
            using(var request=UnityWebRequest.Get(connection.BaseUrl+"/pets/"+connection.Api.PetId+"/meals"))
            {
                request.SetRequestHeader("Authorization","Bearer "+Environment.GetEnvironmentVariable("HEALTHMON_USER_TOKEN"));
                var op=request.SendWebRequest();await Until(()=>op.isDone,30,"Meal read-back timeout");
                Check(request.result==UnityWebRequest.Result.Success,"Saved meal can be read back");
                File.WriteAllText(Path.Combine(output,"saved-meals.json"),request.downloadHandler.text);
            }
            Check(connection.LatestState.state_version>=saved.state_version,"Food result synchronized to game state");
            ui.ShowHome();await Capture("recorded-home.png");
            Check(report.runtime_errors.Count==0,"No Unity runtime errors during the test");report.passed=true;
        }
        catch(Exception error){report.error=error.ToString();await Capture("failure.png");}
        finally
        {
            if(game!=null)game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,originalIndex);
            if(customIndex>=0)group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
            Application.logMessageReceived-=Observe;
            File.WriteAllText(Path.Combine(output,"unity-multifood-report.json"),JsonUtility.ToJson(report,true));
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
