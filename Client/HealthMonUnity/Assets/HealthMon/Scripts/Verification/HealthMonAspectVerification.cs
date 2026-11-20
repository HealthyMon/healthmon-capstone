#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

[InitializeOnLoad]
public static class HealthMonAspectVerification
{
    static HealthMonAspectVerification()
    {
        EditorApplication.playModeStateChanged += state => {
            if (state != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool("HealthMonAspectChecks", false)) return;
            SessionState.SetBool("HealthMonAspectChecks", false);
            var runner = new GameObject("Aspect verification").AddComponent<HealthMonAspectRunner>();
            runner.onboarding = SessionState.GetBool("HealthMonOnboardingChecks", false);
            SessionState.SetBool("HealthMonOnboardingChecks", false);
            Object.DontDestroyOnLoad(runner.gameObject);
        };
    }
    public static void RunOnboarding()
    {
        if (Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP") != "1") throw new InvalidOperationException("Preferences backup required");
        // The external verifier restores every preference, including existing progress.
        foreach (string key in new[]{"HM_PLAYER_NICKNAME", "HM_PLAYER_CHARACTER_INDEX", "HM_PLAYER_SETUP_DONE"}) PlayerPrefs.DeleteKey(key);
        PlayerPrefs.Save();
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/BootScene.unity");
        SessionState.SetBool("HealthMonOnboardingChecks", true);
        SessionState.SetBool("HealthMonAspectChecks", true);
        EditorApplication.isPlaying = true;
    }
    public static void Run()
    {
        if (Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP") != "1") throw new InvalidOperationException("Preferences backup required");
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        SessionState.SetBool("HealthMonAspectChecks", true);
        EditorApplication.isPlaying = true;
    }
}

public class HealthMonAspectRunner : MonoBehaviour
{
    [Serializable] class Frame { public string name; public int width, height; public List<string> clipped = new List<string>(); }
    [Serializable] class Report { public bool passed; public int runtimeErrors; public string error; public List<string> checks = new List<string>(); public List<Frame> frames = new List<Frame>(); }
    public bool onboarding;
    Report report = new Report(); string output; object group; EditorWindow game; int originalIndex, customIndex = -1;
    BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    void Start()
    {
        output = Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");
        Application.runInBackground = true;
        Application.logMessageReceived += Observe;
        StartCoroutine(Guard(onboarding ? ExerciseOnboarding() : Exercise()));
    }
    void Observe(string message,string trace,LogType type) { if (type == LogType.Error || type == LogType.Exception) report.runtimeErrors++; }
    IEnumerator Guard(IEnumerator routine)
    {
        while(true)
        {
            object next;
            try { if(!routine.MoveNext()) break; next=routine.Current; }
            catch(Exception ex) { report.error=ex.ToString();break; }
            yield return next;
        }
        if(game != null) game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,originalIndex);
        if(customIndex >= 0) group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
        report.passed = string.IsNullOrEmpty(report.error) && report.runtimeErrors == 0 && report.frames.All(f => f.clipped.Count == 0);
        File.WriteAllText(Path.Combine(output,"aspect-report.json"),JsonUtility.ToJson(report,true));
        Application.logMessageReceived -= Observe;
        EditorApplication.Exit(report.passed ? 0 : 1);
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
            var groupType=assembly.GetType("UnityEditor.GameViewSizeGroupType");
            group=type.GetMethod("GetGroup",flags).Invoke(sizes,new object[]{Enum.Parse(groupType,"Android")});
            // Remove only this verifier's leftover resolutions from an interrupted run.
            int count=(int)group.GetType().GetMethod("GetTotalCount",flags).Invoke(group,null);
            for(int i=count-1;i>=0;i--)
            {
                var existing=group.GetType().GetMethod("GetGameViewSize",flags).Invoke(group,new object[]{i});
                string label=(string)existing.GetType().GetProperty("baseText",flags).GetValue(existing);
                if(label=="HealthMon aspect verification")group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{i});
            }
        }
        if(customIndex>=0) group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
        var sizeType=assembly.GetType("UnityEditor.GameViewSizeType");
        var size=Activator.CreateInstance(assembly.GetType("UnityEditor.GameViewSize"),flags,null,new object[]{Enum.Parse(sizeType,"FixedResolution"),width,height,"HealthMon aspect verification"},null);
        int builtin=(int)group.GetType().GetMethod("GetBuiltinCount",flags).Invoke(group,null);
        customIndex=builtin+(int)group.GetType().GetMethod("GetCustomCount",flags).Invoke(group,null);
        group.GetType().GetMethod("AddCustomSize",flags).Invoke(group,new[]{size});
        game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,customIndex);
        game.Repaint();
    }
    T Find<T>() where T:Object => Object.FindAnyObjectByType<T>(FindObjectsInactive.Include);
    void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
        report.checks.Add(message);
    }
    IEnumerator ExerciseOnboarding()
    {
        yield return new WaitForSecondsRealtime(2);
        var flow=Find<HealthMonFirstRunFlow>();
        Check(flow!=null && flow.setupPanel.activeInHierarchy && !flow.startPanel.activeSelf, "First launch opens nickname / starter setup");
        Check(flow.cardButtons.Length==3 && flow.cardButtons.All(b=>b!=null), "All three starter buttons are connected");
        var previews=Find<BootCharacterPreviewRuntime>();
        Check(previews!=null && previews.previewImages.All(i=>i!=null && i.texture!=null), "All three live character previews have textures");
        foreach(int height in new[]{1280,1440,1600})
        {
            SetSize(720,height);yield return new WaitForSecondsRealtime(.6f);
            Check(Screen.width==720 && Screen.height==height, "Resolution 720x"+height);
            string prefix="9x"+(height==1280?16:height==1440?18:20)+"-";
            flow.OpenSetup();yield return Capture(prefix+"first-setup");
            flow.backButton.onClick.Invoke();yield return Capture(prefix+"start");
            flow.continueButton.onClick.Invoke();
            Check(flow.setupPanel.activeInHierarchy, "Continue without a profile returns to setup at "+height);
        }
        SetSize(720,1280);yield return new WaitForSecondsRealtime(.6f);
        foreach(string invalid in new[]{"", " ", "A", "1234567890123"})
        {
            flow.nicknameInput.text=invalid;
            flow.confirmButton.onClick.Invoke();yield return null;
            Check(SceneManager.GetActiveScene().name=="BootScene" && !HealthMonStarterProfile.Instance.IsSetupDone, "Reject invalid nickname length "+invalid.Length);
        }
        for(int i=0;i<3;i++)
        {
            flow.cardButtons[i].onClick.Invoke();yield return null;
            Check(flow.cardFrames[i].color==flow.selectedFrameColor && flow.cardFrames.Where((_,n)=>n!=i).All(f=>f.color==flow.normalFrameColor), "Starter card selection "+i);
            yield return Capture("9x16-starter-"+i);
        }
        flow.nicknameInput.text="  캡처테스터  ";flow.cardButtons[1].onClick.Invoke();
        flow.confirmButton.onClick.Invoke();
        float deadline=Time.realtimeSinceStartup+30;
        while(SceneManager.GetActiveScene().name!="MainARScene" && Time.realtimeSinceStartup<deadline)yield return null;
        yield return new WaitForSecondsRealtime(3);
        Check(SceneManager.GetActiveScene().name=="MainARScene", "Confirm opens the actual home scene");
        var profile=HealthMonStarterProfile.Instance;
        Check(profile!=null && profile.IsSetupDone && profile.Nickname=="캡처테스터" && profile.SelectedCharacterIndex==1, "Trimmed nickname and chosen starter survive the scene change");
        profile.Load();
        Check(profile.Nickname=="캡처테스터" && profile.SelectedCharacterIndex==1, "Profile reload reads persisted values");
        yield return Capture("9x16-after-setup-home");
        SceneManager.LoadScene("BootScene");yield return new WaitForSecondsRealtime(2);
        flow=Find<HealthMonFirstRunFlow>();
        Check(flow.startPanel.activeInHierarchy && !flow.setupPanel.activeSelf, "Returning player sees Continue / New Start");
        yield return Capture("9x16-returning-player");
        flow.continueButton.onClick.Invoke();yield return new WaitForSecondsRealtime(3);
        Check(SceneManager.GetActiveScene().name=="MainARScene", "Continue returns to home");
    }
    IEnumerator Exercise()
    {
        yield return new WaitForSecondsRealtime(3);
        foreach(int height in new[]{1280,1440,1600})
        {
            SetSize(720,height);
            yield return new WaitForSecondsRealtime(.6f);
            if(Screen.width!=720 || Screen.height!=height)throw new Exception("Game view resize failed: "+Screen.width+"x"+Screen.height);
            var ui=Find<UIManager>();
            string prefix="9x"+(height==1280?16:height==1440?18:20)+"-";
            foreach(var page in new (string,Action)[]{("home",ui.ShowHome),("status",ui.ShowStatus),("food",ui.ShowFoodScan),("dialogue",ui.ShowDialogue),("quests",ui.ShowQuest),("collection",ui.ShowCollection),("wearable",ui.ShowWearable),("outfit",ui.ShowCustomization)})
            {page.Item2();yield return new WaitForSecondsRealtime(.2f);yield return Capture(prefix+page.Item1);}
            ui.ShowFoodScan();Find<FoodScanPrototype>().ShowCandidates();yield return Capture(prefix+"food-candidates");Find<FoodScanPrototype>().ShowCapture();
            ui.ShowHome();
            var roster=Find<HealthMonCharacterRosterController>();roster.Open();yield return Capture(prefix+"characters");var firstCard=roster.cardContent.GetComponentsInChildren<HealthMonCharacterSlotCard>().First();
            firstCard.button.onClick.Invoke();yield return Capture(prefix+"character-detail");roster.Close();
            var dashboard=Find<HealthMonRulesDashboard>();dashboard.Open();yield return Capture(prefix+"growth");dashboard.Close();
            var pose=Find<HealthMonPoseScreen>();pose.Open();yield return Capture(prefix+"pose");pose.Close();
            var evolution=Find<HealthMon.Evolution.EvolutionUIController>();evolution.StartEvolution();yield return new WaitForSecondsRealtime(.5f);yield return Capture(prefix+"evolution");evolution.CloseEvolution();
            ui.ShowHome();
            var shopButton=GameObject.Find("UI/Canvas/BottomNavV2/BottomRow/ShopButton");
            if(shopButton!=null){shopButton.GetComponent<Button>().onClick.Invoke();yield return Capture(prefix+"shop");Find<HealthMonShopScreen>().CloseShop();ui.ShowHome();}
        }
    }
    IEnumerator Capture(string name)
    {
        yield return null;Canvas.ForceUpdateCanvases();yield return new WaitForEndOfFrame();
        var frame=new Frame{name=name,width=Screen.width,height=Screen.height};
        foreach(var button in FindObjectsByType<Graphic>(FindObjectsSortMode.None).Where(g => g is TMPro.TMP_Text || g.GetComponent<Button>() != null))
        {
            if(button.GetComponentInParent<ScrollRect>()!=null)continue;
            if(button is TMPro.TMP_Text label && string.IsNullOrWhiteSpace(label.text))continue;
            var rect=button.transform as RectTransform;if(rect==null)continue;
            var canvas=button.GetComponentInParent<Canvas>();if(canvas==null)continue;
            var corners=new Vector3[4];rect.GetWorldCorners(corners);
            var camera=canvas.renderMode==RenderMode.ScreenSpaceOverlay?null:canvas.worldCamera;
            var points=corners.Select(c=>RectTransformUtility.WorldToScreenPoint(camera,c)).ToArray();
            if(points.Any(p=>p.x < -1 || p.y < -1 || p.x > Screen.width+1 || p.y > Screen.height+1))
                frame.clipped.Add(PathOf(rect)+" ["+string.Join(";",points.Select(p=>p.ToString("F0")))+"]");
        }
        report.frames.Add(frame);
        ScreenCapture.CaptureScreenshot(Path.Combine(output,name+".png"));yield return new WaitForSecondsRealtime(.15f);
    }
    static string PathOf(Transform t) => t.parent==null?t.name:PathOf(t.parent)+"/"+t.name;
}
#endif
