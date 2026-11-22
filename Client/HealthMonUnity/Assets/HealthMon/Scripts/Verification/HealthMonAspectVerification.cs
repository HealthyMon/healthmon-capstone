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

    public static void Finish(int code)
    {
        // Exit play mode first so native AR/GLTF resources can dispose normally.
        void AfterPlay(PlayModeStateChange state)
        {
            if (state != PlayModeStateChange.EnteredEditMode) return;
            EditorApplication.playModeStateChanged -= AfterPlay;
            EditorApplication.delayCall += () => EditorApplication.Exit(code);
        }
        EditorApplication.playModeStateChanged += AfterPlay;
        EditorApplication.isPlaying = false;
    }
}

public class HealthMonAspectRunner : MonoBehaviour
{
    [Serializable] class Frame { public string name; public int width, height; public List<string> clipped = new List<string>(); }
    [Serializable] class Report { public bool passed; public int runtimeErrors; public string error; public List<string> errorMessages = new List<string>(); public List<string> checks = new List<string>(); public List<Frame> frames = new List<Frame>(); }
    public bool onboarding;
    Report report = new Report(); string output; object group; EditorWindow game; int originalIndex, customIndex = -1;
    BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    void Start()
    {
        output = Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");
        Application.runInBackground = true;
        Application.targetFrameRate = 30;
        Application.logMessageReceived += Observe;
        StartCoroutine(Guard(onboarding ? ExerciseOnboarding() : Exercise()));
    }
    void Observe(string message,string trace,LogType type)
    {
        if (type != LogType.Error && type != LogType.Exception) return;
        report.runtimeErrors++;
        report.errorMessages.Add(message + "\n" + trace);
    }
    IEnumerator Guard(IEnumerator routine)
    {
        var routines = new Stack<IEnumerator>();
        routines.Push(routine);
        while(routines.Count > 0)
        {
            object next;
            try
            {
                var active = routines.Peek();
                if(!active.MoveNext()) { routines.Pop(); continue; }
                next=active.Current;
                if(next is IEnumerator nested) { routines.Push(nested); continue; }
            }
            catch(Exception ex) { report.error=ex.ToString();break; }
            yield return next;
        }
        Time.timeScale = 1;
        if(game != null) game.GetType().GetProperty("selectedSizeIndex",flags).SetValue(game,originalIndex);
        if(customIndex >= 0) group.GetType().GetMethod("RemoveCustomSize",flags).Invoke(group,new object[]{customIndex});
        report.passed = string.IsNullOrEmpty(report.error) && report.runtimeErrors == 0 && report.frames.All(f => f.clipped.Count == 0);
        File.WriteAllText(Path.Combine(output,"aspect-report.json"),JsonUtility.ToJson(report,true));
        Application.logMessageReceived -= Observe;
        if (Environment.GetEnvironmentVariable("HEALTHMON_VISUAL_REVIEW") == "1")
        {
            Find<UIManager>()?.ShowHome();
            Debug.Log("VISUAL_REVIEW_READY: bounds checks are not visual approval; editor remains open for inspection.");
            yield break;
        }
        HealthMonAspectVerification.Finish(report.passed ? 0 : 1);
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
        if (Environment.GetEnvironmentVariable("HEALTHMON_LIVE_EVOLUTION_REVIEW") == "1")
        {
            yield return ExerciseLiveEvolution();
            yield break;
        }
        if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("HEALTHMON_GENERATED_REVIEW")))
        {
            yield return ExerciseGeneratedModel();
            yield break;
        }
        if (Environment.GetEnvironmentVariable("HEALTHMON_ADVENTURE_REVIEW") == "1")
        {
            yield return ExerciseAdventure();
            yield break;
        }
        foreach(int height in new[]{1280,1440,1600})
        {
            SetSize(720,height);
            yield return new WaitForSecondsRealtime(.6f);
            if(Screen.width!=720 || Screen.height!=height)throw new Exception("Game view resize failed: "+Screen.width+"x"+Screen.height);
            var ui=Find<UIManager>();
            string prefix="9x"+(height==1280?16:height==1440?18:20)+"-";
            foreach(var page in new (string,Action)[]{("home",ui.ShowHome),("status",ui.ShowStatus),("food",ui.ShowFoodScan),("dialogue",ui.ShowDialogue),("quests",ui.ShowQuest),("collection",ui.ShowCollection),("wearable",ui.ShowWearable),("outfit",ui.ShowCustomization)})
            {page.Item2();yield return new WaitForSecondsRealtime(.2f);yield return Capture(prefix+page.Item1);}
            ui.ShowHome();
            var arButton = GameObject.Find("PetARButton")?.GetComponent<Button>();
            Check(arButton != null && arButton.gameObject.activeInHierarchy, "Home AR entry visible at " + height);
            arButton.onClick.Invoke();
            yield return new WaitForSecondsRealtime(.6f);
            Check(GameObject.Find("PetARPanel") != null, "Home AR entry opens AR presentation at " + height);
            yield return Capture(prefix + "pet-ar");
            ui.ShowHome();
            ui.ShowFoodScan();Find<FoodScanPrototype>().ShowCandidates();yield return Capture(prefix+"food-candidates");Find<FoodScanPrototype>().ShowCapture();
            ui.ShowHome();
            var roster=Find<HealthMonCharacterRosterController>();roster.Open();yield return Capture(prefix+"characters");var firstCard=roster.cardContent.GetComponentsInChildren<HealthMonCharacterSlotCard>().First();
            firstCard.button.onClick.Invoke();yield return Capture(prefix+"character-detail");roster.Close();
            var dashboard=Find<HealthMonRulesDashboard>();dashboard.Open();yield return Capture(prefix+"growth");dashboard.Close();
            var pose=Find<HealthMonPoseScreen>();pose.Open();yield return Capture(prefix+"pose");pose.Close();
            var evolution=Find<HealthMon.Evolution.EvolutionUIController>();evolution.StartEvolution();yield return new WaitForSecondsRealtime(.5f);yield return Capture(prefix+"evolution");
            // Visual-state fixtures only: actual model application is checked separately.
            evolution.CompleteEvolution();yield return new WaitForSecondsRealtime(1);MarkVisualFixture(evolution);yield return Capture(prefix+"evolution-complete");
            evolution.ShowEvolutionError("진화 중단 · 홈에서 다시 도전");yield return Capture(prefix+"evolution-error");evolution.CloseEvolution();
            ui.ShowHome();
            var shopButton=GameObject.Find("UI/Canvas/BottomNavV2/BottomRow/ShopButton");
            if(shopButton!=null){shopButton.GetComponent<Button>().onClick.Invoke();yield return Capture(prefix+"shop");Find<HealthMonShopScreen>().CloseShop();ui.ShowHome();}
        }
        if (Environment.GetEnvironmentVariable("HEALTHMON_VISUAL_REVIEW") == "1")
        {
            yield return ExerciseAdventure();
        }
    }
    IEnumerator ExerciseLiveEvolution()
    {
        var connection = Healthmon.Common.CommonServerConnection.Instance;
        var client = Healthmon.Evolution.EvolutionClient.Instance;
        float deadline = Time.realtimeSinceStartup + 120;
        while ((connection == null || !connection.IsConnected || connection.LatestState == null || client.Current == null)
            && Time.realtimeSinceStartup < deadline) yield return new WaitForSecondsRealtime(.2f);
        Check(connection != null && connection.IsConnected && connection.EnvironmentName == "test",
            "Connected to isolated real backend");
        Check(connection.Api.PetId == Environment.GetEnvironmentVariable("HEALTHMON_LIVE_PET_ID"), "Correct isolated pet identity");
        var ui = Find<UIManager>();
        var flow = ui.GetComponent<EvolutionFlowController>();
        var screen = Find<HealthMon.Evolution.EvolutionUIController>();
        Check(flow != null && flow.HomeModel != null && flow.PreviewModel != null, "Production visual consumers attached");
        bool restart = Environment.GetEnvironmentVariable("HEALTHMON_LIVE_RESTART") == "1";
        bool publishedReview = Environment.GetEnvironmentVariable("HEALTHMON_LIVE_PUBLISHED_REVIEW") == "1";
        ui.ShowHome(); SetSize(720,1280); yield return new WaitForSecondsRealtime(.8f);
        string previousHash = client.Current?.model_sha256;
        if (!restart)
        {
            Check(connection.LatestState.published_model_stage == (publishedReview ? 1 : 0),
                publishedReview ? "Reviewing the already generated published model" : "Before evolution: authoritative starter stage zero");
            yield return Capture(publishedReview ? "9x16-published-home" : "9x16-real-before");
            var button = GameObject.Find("HomeEvolutionButton")?.GetComponent<Button>();
            Check(button != null && button.interactable, "Actual home evolution button is available");
            button.onClick.Invoke();
            yield return new WaitForSecondsRealtime(2);
            Check(publishedReview ? string.IsNullOrEmpty(client.ActiveRequestId) && screen.completedContent.activeInHierarchy :
                !string.IsNullOrEmpty(client.ActiveRequestId) && screen.evolvingContent.activeInHierarchy,
                publishedReview ? "Published result re-opens without requesting another generation" : "Real request opens production evolving screen");
            if (!publishedReview) foreach (int height in new[] {1280,1440,1600})
            {
                SetSize(720,height); yield return new WaitForSecondsRealtime(.6f);
                yield return Capture("9x"+(height==1280?16:height==1440?18:20)+"-real-progress");
            }
        }
        deadline = Time.realtimeSinceStartup + (restart ? 120 : 7200);
        while (Time.realtimeSinceStartup < deadline)
        {
            if (client.HasTerminalError) throw new InvalidOperationException("Real generation failed: " + client.LastError);
            if (!restart && screen.completedContent.activeInHierarchy)
                Check(flow.IsApplied && client.Current.stage == 1, "Success cannot precede both model applications");
            bool applied = client.Current != null && client.Current.stage == 1 && flow.IsApplied &&
                connection.LatestState.published_model_stage == 1;
            if (applied && (restart || screen.completedContent.activeInHierarchy)) break;
            yield return new WaitForSecondsRealtime(.1f);
        }
        Check(client.Current != null && client.Current.stage == 1 && flow.IsApplied, "Generated stage one applied to home and preview");
        Check(client.Current.revision == Environment.GetEnvironmentVariable("HEALTHMON_LIVE_JOB_ID"), "Applied revision is the actual GPU job");
        if (!restart && !publishedReview) Check(client.Current.model_sha256 != previousHash, "Evolution replaces the starter with a different model asset");
        else Check(client.Current.model_sha256 == Environment.GetEnvironmentVariable("HEALTHMON_LIVE_MODEL_SHA256"),
            "Fresh Unity process restores the exact published model hash");
        string cache = Path.Combine(Application.persistentDataPath,"HealthMonModels",client.Current.model_sha256+".glb");
        Check(File.Exists(cache), "Published model downloaded through the production client");
        using (var hash = System.Security.Cryptography.SHA256.Create())
        using (var file = File.OpenRead(cache))
            Check(BitConverter.ToString(hash.ComputeHash(file)).Replace("-", "").ToLowerInvariant() == client.Current.model_sha256,
                "Downloaded GLB hash matches server publication");
        File.WriteAllText(Path.Combine(output,"real-evolution.json"),JsonUtility.ToJson(client.Current,true));
        foreach (var model in new[] {flow.HomeModel,flow.PreviewModel})
            Check(model.GetComponentsInChildren<Renderer>().Any(r => r.enabled), "Applied model has visible renderers: "+model.name);
        if (!restart)
        {
            Check(screen.completedContent.activeInHierarchy, "Production flow shows real evolution completion");
            foreach (int height in new[] {1280,1440,1600})
            {
                SetSize(720,height); yield return new WaitForSecondsRealtime(.6f);
                yield return Capture("9x"+(height==1280?16:height==1440?18:20)+"-real-complete");
            }
            screen.CloseEvolution();
        }
        foreach (int height in new[] {1280,1440,1600})
        {
            SetSize(720,height); ui.ShowHome(); yield return new WaitForSecondsRealtime(.8f);
            Check(flow.HomeModel.DisplayedRevision == client.Current.revision && !screen.evolutionOverlay.activeInHierarchy,
                "Home retains generated appearance without a success overlay");
            yield return Capture("9x"+(height==1280?16:height==1440?18:20)+(restart?"-real-restarted-home":"-real-after-home"));
        }
        if (!restart && Environment.GetEnvironmentVariable("HEALTHMON_LIVE_PRESENTATION") == "1")
        {
            SetSize(720,1280); yield return new WaitForSecondsRealtime(.6f);
            var ar = GameObject.Find("PetARButton")?.GetComponent<Button>();
            Check(ar != null && ar.interactable, "Evolved pet AR entry remains available");
            ar.onClick.Invoke();
            var placement = Find<ARPlacementManager>();
            deadline = Time.realtimeSinceStartup + 90;
            Healthmon.Evolution.ArEvolutionModel arModel = null;
            while (Time.realtimeSinceStartup < deadline)
            {
                arModel = placement.SpawnedHealthMon?.GetComponent<Healthmon.Evolution.ArEvolutionModel>();
                if (arModel != null && arModel.DisplayedRevision == client.Current.revision) break;
                yield return null;
            }
            Check(arModel != null && arModel.DisplayedRevision == client.Current.revision,
                "AR uses the same published generated model");
            Check(Mathf.Abs(client.Settings.model_yaw_degrees) < .01f,
                "Slime forward axis is not reversed after placement faces the camera");
            foreach (int height in new[] {1280,1440,1600})
            {
                SetSize(720,height); yield return new WaitForSecondsRealtime(.6f);
                yield return Capture("9x"+(height==1280?16:height==1440?18:20)+"-real-pet-ar");
            }
            ui.ShowHome(); yield return new WaitForSecondsRealtime(.6f);
            yield return ExerciseAdventure();
        }
    }
    IEnumerator ExerciseGeneratedModel()
    {
        var ui = Find<UIManager>();
        var flow = ui.GetComponent<EvolutionFlowController>() ?? ui.gameObject.AddComponent<EvolutionFlowController>();
        flow.Configure(ui);
        yield return null;
        var file = Environment.GetEnvironmentVariable("HEALTHMON_GENERATED_REVIEW");
        var bytes = File.ReadAllBytes(file);
        string digest;
        using (var hash = System.Security.Cryptography.SHA256.Create())
            digest = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        string cache = Path.Combine(Application.persistentDataPath, "HealthMonModels", digest + ".glb");
        Directory.CreateDirectory(Path.GetDirectoryName(cache));
        File.WriteAllBytes(cache, bytes);
        var manifest = new Healthmon.Evolution.ModelManifest { pet_id = "isolated-render-verification", stage = 1,
            revision = "generated-2511-" + digest.Substring(0, 12), model_sha256 = digest, model_url = "/verification/" + digest + ".glb" };
        var screen = Find<HealthMon.Evolution.EvolutionUIController>();
        SetSize(720,1280); yield return new WaitForSecondsRealtime(.6f);
        screen.StartEvolution(); yield return new WaitForSecondsRealtime(.5f);
        yield return Capture("9x16-generated-loading");
        flow.HomeModel.Changed(manifest); flow.PreviewModel.Changed(manifest);
        float deadline = Time.realtimeSinceStartup + 90;
        while ((flow.HomeModel.DisplayedRevision != manifest.revision || flow.PreviewModel.DisplayedRevision != manifest.revision)
            && Time.realtimeSinceStartup < deadline) yield return null;
        Check(flow.HomeModel.DisplayedRevision == manifest.revision && flow.PreviewModel.DisplayedRevision == manifest.revision,
            "Supplied GLB loaded into both production views: " + flow.HomeModel.LastError + "; " + flow.PreviewModel.LastError);
        var geometry = new List<string>();
        foreach (var model in new[] {flow.HomeModel, flow.PreviewModel})
        {
            for (Transform ancestor=model.transform; ancestor!=null; ancestor=ancestor.parent)
                geometry.Add(ancestor.name+" worldEuler="+ancestor.eulerAngles+" local="+ancestor.localEulerAngles+" scale="+ancestor.lossyScale);
            foreach (var skin in model.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                if (!skin.enabled) continue;
                var mesh=new Mesh(); skin.BakeMesh(mesh,false);
                geometry.Add(skin.name+" renderer="+skin.bounds+" bakeFalse="+mesh.bounds+" scale="+skin.transform.lossyScale);
                skin.BakeMesh(mesh,true); geometry.Add("bakeTrue="+mesh.bounds); Destroy(mesh);
            }
        }
        File.WriteAllLines(Path.Combine(output,"geometry.txt"),geometry);
        File.WriteAllText(Path.Combine(output, "artifact-sha256.txt"), digest);
        foreach (int height in new[] {1280,1440,1600})
        {
            SetSize(720,height); yield return new WaitForSecondsRealtime(.6f);
            string prefix="9x"+(height==1280?16:height==1440?18:20)+"-";
            screen.StartEvolution(); yield return new WaitForSecondsRealtime(.4f);
            screen.CompleteEvolution(); yield return new WaitForSecondsRealtime(1);
            MarkVisualFixture(screen);
            yield return Capture(prefix+"generated-complete");
            screen.CloseEvolution(); ui.ShowHome(); yield return new WaitForSecondsRealtime(.6f);
            yield return Capture(prefix+"generated-home");
        }
    }
    void MarkVisualFixture(HealthMon.Evolution.EvolutionUIController screen)
    {
        // A layout/import fixture must never resemble proof of live generation.
        foreach (var label in screen.completedContent.GetComponentsInChildren<TMPro.TMP_Text>(true))
        {
            if (label.text.Contains("진화 성공")) label.text = "연출 검증";
            else if (label.name == "SuccessSubtitle") label.text = "실제 진화 요청 아님";
            else if (label.name == "SuccessMessage") label.text = "화면 배치·모델 표시만 검사";
        }
    }
    IEnumerator ExerciseAdventure()
    {
            HealthMonAdventureAppearance.CaptureHome();
            foreach (int height in new[] { 1280, 1440, 1600 })
            {
                SetSize(720, height);
                UnityEngine.Random.InitState(2511);
                SceneManager.LoadScene("AdventureScene");
                yield return new WaitForSecondsRealtime(2);
                string prefix = "9x" + (height == 1280 ? 16 : height == 1440 ? 18 : 20) + "-";
                yield return Capture(prefix + "adventure-entrance");
                Time.timeScale = .25f;
                Find<AdventureManager>().EnterExploration();
                yield return CaptureFloorTransitions(prefix);
                Time.timeScale = 1;
                float deadline = Time.realtimeSinceStartup + 20;
                while (Find<BattleManager>().currentState != BattleState.PlayerSelecting && Time.realtimeSinceStartup < deadline) yield return null;
                yield return new WaitForSecondsRealtime(.5f);
                Check(Find<BattleManager>().currentState == BattleState.PlayerSelecting, "Normal battle reaches player turn at " + height);
                yield return Capture(prefix + "battle");
                var battle = Find<BattleManager>();
                int hp = battle.enemy.currentHP;
                battle.battleUI.attackButton.onClick.Invoke();
                yield return new WaitForSecondsRealtime(1);
                Check(battle.enemy.currentHP < hp, "Visible attack button damages enemy at " + height);
                // Isolated unsaved battle fixture: finish this encounter to exercise the result path.
                battle.enemy.currentHP = 1;
                deadline = Time.realtimeSinceStartup + 20;
                while (battle.currentState != BattleState.PlayerSelecting && Time.realtimeSinceStartup < deadline) yield return null;
                battle.battleUI.attackButton.onClick.Invoke();
                yield return new WaitForSecondsRealtime(1);
                Check(battle.LastBattleVictory == true, "Normal victory at " + height);
                yield return Capture(prefix + "battle-victory");
                Find<BattleController>().ConfirmBattleResult();
                yield return new WaitForSecondsRealtime(.5f);
                yield return Capture(prefix + "exploration-result");
                Find<BattleController>().StartBattle(true);
                deadline = Time.realtimeSinceStartup + 20;
                while ((!battle.IsEliteBattle || battle.currentState != BattleState.PlayerSelecting) && Time.realtimeSinceStartup < deadline) yield return null;
                Check(battle.IsEliteBattle && battle.currentState == BattleState.PlayerSelecting, "Elite battle reaches player turn at " + height);
                yield return new WaitForSecondsRealtime(.5f);
                yield return Capture(prefix + "elite-battle");
                battle.battleUI.moveButton.onClick.Invoke();
                yield return new WaitForSecondsRealtime(.3f);
                yield return Capture(prefix + "elite-move");
            }
            SceneManager.LoadScene("MainARScene");
            yield return new WaitForSecondsRealtime(3);
    }
    IEnumerator CaptureFloorTransitions(string prefix)
    {
        var transition = Find<AdventureTransitionUI>();
        var observed = new Dictionary<string, HashSet<int>>();
        float deadline = Time.realtimeSinceStartup + 30;
        while (Time.realtimeSinceStartup < deadline)
        {
            var sequence = transition.ActiveSequence;
            if (sequence != null)
            {
                string name = sequence.name == "DescendContent" ? "descending" : "monster-intro";
                if (!observed.ContainsKey(name)) observed[name] = new HashSet<int>();
                if (observed[name].Add(sequence.CurrentFrame))
                {
                    var canvas = sequence.GetComponentInParent<Canvas>();
                    var corners = new Vector3[4];
                    sequence.GetComponent<RectTransform>().GetWorldCorners(corners);
                    var points = corners.Select(c => RectTransformUtility.WorldToScreenPoint(canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera, c)).ToArray();
                    Check(points.Min(p=>p.x) <= 1 && points.Max(p=>p.x) >= Screen.width-1 && points.Min(p=>p.y) <= 1 && points.Max(p=>p.y) >= Screen.height-1,
                        name + " frame " + sequence.CurrentFrame + " fills " + Screen.width + "x" + Screen.height);
                    yield return Capture(prefix + name + "-frame-" + sequence.CurrentFrame);
                }
            }
            if (observed.ContainsKey("monster-intro") && !transition.IsPlaying) break;
            yield return null;
        }
        Check(observed.ContainsKey("descending") && observed["descending"].Count == 8, "All eight descending frames rendered at " + Screen.height);
        Check(observed.ContainsKey("monster-intro") && observed["monster-intro"].Count == 8, "All eight monster intro frames rendered at " + Screen.height);
    }
    IEnumerator Capture(string name)
    {
        yield return null;Canvas.ForceUpdateCanvases();yield return new WaitForEndOfFrame();
        var frame=new Frame{name=name,width=Screen.width,height=Screen.height};
        if (name.EndsWith("wearable"))
            File.WriteAllLines(Path.Combine(output, name + "-images.txt"), FindObjectsByType<Image>(FindObjectsSortMode.None).Select(g => {
                var corners = new Vector3[4]; g.rectTransform.GetWorldCorners(corners);
                return PathOf(g.transform) + " | " + g.sprite?.name + " | " + g.color + " | " + string.Join(";",corners.Select(c=>c.ToString("F0")));
            }));
        foreach(var button in FindObjectsByType<Graphic>(FindObjectsSortMode.None).Where(g => g is TMPro.TMP_Text || g.GetComponent<Button>() != null))
        {
            if(button.GetComponentInParent<ScrollRect>()!=null)continue;
            if(button is TMPro.TMP_Text label && string.IsNullOrWhiteSpace(label.text))continue;
            var rect=button.transform as RectTransform;if(rect==null)continue;
            var canvas=button.GetComponentInParent<Canvas>();if(canvas==null)continue;
            if(button is TMPro.TMP_Text text && text.isTextOverflowing && text.GetComponentInParent<TMPro.TMP_InputField>() == null)
                frame.clipped.Add(PathOf(rect)+" [text overflows its layout]");
            var corners=new Vector3[4];rect.GetWorldCorners(corners);
            var camera=canvas.renderMode==RenderMode.ScreenSpaceOverlay?null:canvas.worldCamera;
            var points=corners.Select(c=>RectTransformUtility.WorldToScreenPoint(camera,c)).ToArray();
            if(points.Any(p=>p.x < -1 || p.y < -1 || p.x > Screen.width+1 || p.y > Screen.height+1))
                frame.clipped.Add(PathOf(rect)+" ["+string.Join(";",points.Select(p=>p.ToString("F0")))+"]");
        }
        report.frames.Add(frame);
        // Capture this rendered frame now; deferred CaptureScreenshot can record
        // the next UI state instead when the coroutine changes panels/resolution.
        var screenshot = ScreenCapture.CaptureScreenshotAsTexture();
        File.WriteAllBytes(Path.Combine(output,name+".png"), screenshot.EncodeToPNG());
        Destroy(screenshot);
        yield return null;
    }
    static string PathOf(Transform t) => t.parent==null?t.name:PathOf(t.parent)+"/"+t.name;
}
#endif
