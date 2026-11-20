using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Healthmon.Beta;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using Object = UnityEngine.Object;

public static class HealthMonTeamIntegration
{
    private const string Main = "Assets/HealthMon/Scenes/MainARScene.unity";
    private const string Adventure = "Assets/HealthMon/Scenes/AdventureScene.unity";
    private static int checks;

    public static void StartAspectChecks()
    {
        Run();
        HealthMonAspectVerification.Run();
    }

    public static void StartPlayChecks()
    {
        Run();
        HealthMonTeamPlayChecks.Run();
    }

    [MenuItem("HealthMon/Verification/Install team scene navigation")]
    public static void InstallNavigation()
    {
        var scene = EditorSceneManager.OpenScene(Main);
        var canvas = GameObject.Find("UI/Canvas");
        Require(canvas != null, "Main canvas");
        var row = canvas.transform.Find("BottomNavV2/BottomRow");
        Require(row != null, "Navigation row");
        var template = row.GetComponentsInChildren<Button>(true).First();
        var navigation = canvas.GetComponent<HealthMonAdventureNavigation>() ?? canvas.AddComponent<HealthMonAdventureNavigation>();
        var entry = row.Find("AdventureButton");
        var button = entry != null ? entry.GetComponent<Button>() : Object.Instantiate(template, row);
        button.name = "AdventureButton";
        button.onClick = new Button.ButtonClickedEvent();
        UnityEventTools.AddPersistentListener(button.onClick, navigation.OpenAdventure);
        foreach (var text in button.GetComponentsInChildren<TMP_Text>(true)) text.text = "탐험";
        foreach (var icon in button.GetComponentsInChildren<Image>(true))
        {
            if (icon.gameObject == button.gameObject) continue;
            icon.sprite = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/HealthMon/UIStyleKit/Sprites/Icons/Icon_Activity_Light.png");
        }
        EditorSceneManager.MarkSceneDirty(scene);
        EditorSceneManager.SaveScene(scene);

        scene = EditorSceneManager.OpenScene(Adventure);
        // BattleCanvas is hidden at the entrance. Navigation must remain available
        // above both the entrance and battle canvases, including transition panels.
        var navObject = GameObject.Find("AdventureNavigation");
        if (navObject == null)
            navObject = new GameObject("AdventureNavigation", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var adventureCanvas = navObject.GetComponent<Canvas>();
        adventureCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
        adventureCanvas.sortingOrder = 100;
        var scaler = navObject.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1080, 1920);
        scaler.matchWidthOrHeight = 0f;
        navigation = adventureCanvas.GetComponent<HealthMonAdventureNavigation>() ?? adventureCanvas.gameObject.AddComponent<HealthMonAdventureNavigation>();
        var previousHome = Object.FindObjectsByType<Button>(FindObjectsInactive.Include).FirstOrDefault(b => b.name == "HomeButton");
        if (previousHome != null) previousHome.transform.SetParent(adventureCanvas.transform, false);
        var existing = adventureCanvas.transform.Find("HomeButton");
        Button home;
        if (existing != null) home = existing.GetComponent<Button>();
        else
        {
            var go = new GameObject("HomeButton", typeof(RectTransform), typeof(Image), typeof(Button));
            go.transform.SetParent(adventureCanvas.transform, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = new Vector2(24, -24);
            rect.sizeDelta = new Vector2(150, 68);
            var image = go.GetComponent<Image>();
            image.sprite = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/HealthMon/UIStyleKit/UIStyleKitV3/Sprites/Buttons/BTN_Blue.png");
            image.type = Image.Type.Sliced;
            home = go.GetComponent<Button>();
            var label = new GameObject("Label", typeof(RectTransform), typeof(TextMeshProUGUI));
            label.transform.SetParent(go.transform, false);
            var labelRect = (RectTransform)label.transform;
            labelRect.anchorMin = Vector2.zero; labelRect.anchorMax = Vector2.one;
            labelRect.offsetMin = labelRect.offsetMax = Vector2.zero;
            var text = label.GetComponent<TextMeshProUGUI>();
            text.font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>("Assets/HealthMon/Shop/Fonts/HealthMonShop_KoreanDynamic.asset");
            text.text = "홈"; text.fontSize = 30; text.alignment = TextAlignmentOptions.Center; text.raycastTarget = false;
        }
        home.onClick = new Button.ButtonClickedEvent();
        UnityEventTools.AddPersistentListener(home.onClick, navigation.ReturnHome);
        home.transform.SetAsLastSibling();
        var battleUI = Object.FindAnyObjectByType<BattleUI>(FindObjectsInactive.Include);
        battleUI.enemyNameText = Object.FindObjectsByType<TMP_Text>(FindObjectsInactive.Include)
            .First(t => t.name == "EnemyNameText");
        EditorUtility.SetDirty(battleUI);
        EditorSceneManager.MarkSceneDirty(scene);
        EditorSceneManager.SaveScene(scene);

        var scenes = EditorBuildSettings.scenes.ToList();
        var target = scenes.FirstOrDefault(s => s.path == Adventure);
        if (target == null) scenes.Add(new EditorBuildSettingsScene(Adventure, true));
        else target.enabled = true;
        EditorBuildSettings.scenes = scenes.ToArray();
        AssetDatabase.SaveAssets();
        EditorSceneManager.OpenScene(Main);
        Run();
    }

    [MenuItem("HealthMon/Verification/Check team integration")]
    public static void Run()
    {
        checks = 0;
        var setup = EditorSceneManager.GetSceneManagerSetup();
        try
        {
            var main = EditorSceneManager.OpenScene(Main);
            CheckScripts(main);
            var roster = Object.FindAnyObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
            Require(roster != null && roster.catalog != null, "Character roster installed");
            Require(roster.state != null && roster.originalHomePet != null && roster.homePetAnchor != null, "Character home bindings");
            Require(roster.overlay != null && roster.cardTemplate != null && roster.cardContent != null, "Character UI bindings");
            Require(roster.confirmSwitchButton != null && roster.quickOpenButton != null, "Character entry and switching controls");
            foreach (var entry in roster.catalog.entries)
                Require(entry != null && entry.portrait != null && entry.visualPrefab != null, "Roster prefab and portrait: " + entry?.id);
            var pose = Object.FindAnyObjectByType<HealthMonPoseScreen>(FindObjectsInactive.Include);
            Require(pose != null && pose.view != null, "Pose training preserved");
            Require(Object.FindAnyObjectByType<WorkoutHistoryController>(FindObjectsInactive.Include) != null, "Wearable history preserved");
            var adventureEntry = GameObject.Find("UI/Canvas").transform.Find("BottomNavV2/BottomRow/AdventureButton").GetComponent<Button>();
            Require(adventureEntry.onClick.GetPersistentMethodName(0) == "OpenAdventure", "Adventure entry connected");
            Require(EditorBuildSettings.scenes.Any(s => s.enabled && s.path == Adventure), "Adventure in Android build");
            VerifyEditorProfile();
            VerifyGrowthRules();
            VerifyWorkoutDisplay();
            VerifyAdventure();
            CommonServerVerification.Run();
            Debug.Log("HEALTHMON_TEAM_INTEGRATION_PASS checks=" + checks);
            var path = Environment.GetEnvironmentVariable("HEALTHMON_TEAM_REPORT");
            if (!string.IsNullOrEmpty(path)) File.WriteAllText(path, "{\"passed\":true,\"checks\":" + checks + "}");
        }
        finally
        {
            if (Application.isBatchMode || setup.Length == 0 || setup.Any(s => string.IsNullOrEmpty(s.path)))
                EditorSceneManager.OpenScene(Main);
            else EditorSceneManager.RestoreSceneManagerSetup(setup);
        }
    }

    private static void VerifyEditorProfile()
    {
        string root = Path.Combine(Path.GetTempPath(), "HealthMon-profile-check-" + Guid.NewGuid().ToString("N"));
        string runtime = Path.Combine(root, ".runtime");
        Directory.CreateDirectory(runtime);
        string profile = Path.Combine(runtime, "native-server.json"), session = Path.Combine(runtime, "session.json");
        bool ReadProfile(out string url, out string token, out string pet)
        {
            // The profile reader belongs to Assembly-CSharp, not the Editor assembly.
            var type = typeof(Healthmon.Common.CommonServerConnection).Assembly.GetType("Healthmon.Common.EditorConnectionSession");
            var method = type.GetMethod("TryReadProfile", BindingFlags.Static | BindingFlags.NonPublic);
            object[] args = { root, null, null, null };
            bool read = (bool)method.Invoke(null, args);
            url = (string)args[1]; token = (string)args[2]; pet = (string)args[3];
            return read;
        }
        try
        {
            File.WriteAllText(profile, "{\"base_url\":\"http://127.0.0.1:18092\",\"session\":\".runtime/session.json\"}");
            File.WriteAllText(session, "{\"bearer_token\":\"profile-check-token\",\"owner_id\":\"test-owner\"}");
            Require(ReadProfile(out var url, out var token, out var pet)
                && url == "http://127.0.0.1:18092" && token == "profile-check-token" && string.IsNullOrEmpty(pet), "Launcher format supports account pet selection");
            File.WriteAllText(session, "{\"api_base_url\":\"http://127.0.0.1:18092\",\"bearer_token\":\"profile-check-token\"}");
            Require(ReadProfile(out _, out _, out _), "Matching explicit session origin accepted");
            File.WriteAllText(session, "{\"api_base_url\":\"http://127.0.0.1:18093\",\"bearer_token\":\"profile-check-token\"}");
            Require(!ReadProfile(out _, out _, out _), "Mismatched session origin rejected");
            File.WriteAllText(session, "{\"bearer_token\":\"\"}");
            Require(!ReadProfile(out _, out _, out _), "Empty credentials rejected");
            File.WriteAllText(profile, "{\"base_url\":\"https://example.invalid\",\"session\":\".runtime/session.json\"}");
            Require(!ReadProfile(out _, out _, out _), "Non-loopback profile rejected");
            File.WriteAllText(profile, "{\"base_url\":\"http://127.0.0.1:18092\",\"session\":\"outside.json\"}");
            File.WriteAllText(Path.Combine(root, "outside.json"), "{\"bearer_token\":\"profile-check-token\"}");
            Require(!ReadProfile(out _, out _, out _), "Session outside runtime directory rejected");
        }
        finally { if (!Path.GetFullPath(root).StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Unexpected verification directory"); Directory.Delete(root, true); }
    }

    private static void VerifyGrowthRules()
    {
        var rules = Object.FindAnyObjectByType<HealthMonGameRules>(FindObjectsInactive.Include);
        var dashboard = Object.FindAnyObjectByType<HealthMonRulesDashboard>(FindObjectsInactive.Include);
        Require(rules != null && rules.pet != null && rules.roster != null, "Daily rules bind to existing pet and roster");
        Require(dashboard != null && dashboard.rules == rules && dashboard.rulesOverlay != null, "Growth dashboard connected");
        Require(dashboard.openButton != null && dashboard.closeButton != null && dashboard.summary != null, "Growth dashboard navigation");
        Require(dashboard.upperInput != null && dashboard.cardioInput != null && dashboard.upperButton != null && dashboard.cardioButton != null, "Manual record controls");
        int[] values = { -1, 0, 1, 39, 40, 69, 70, 99, 100, 119, 120, 200 };
        int[] expected = { 0, 0, -2, -2, -1, -1, 1, 1, 2, 2, 3, 3 };
        for (int i = 0; i < values.Length; i++)
            Require(HealthMonGameRules.CalculateDailyDelta(values[i], 100) == expected[i], "Daily settlement boundary " + values[i]);
        Require(HealthMonGameRules.CalculateDailyDelta(100, 0) == 0, "Invalid daily target is ignored");
        var main = SceneManager.GetActiveScene();
        var boot = EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/BootScene.unity", OpenSceneMode.Additive);
        try
        {
            CheckScripts(boot);
            foreach (var name in new[] { "Panel", "SetupCard", "ConfirmSetupButton" })
            {
                var image = boot.GetRootGameObjects().SelectMany(r => r.GetComponentsInChildren<Image>(true)).First(i => i.name == name);
                Require(image.sprite != null, "Boot image restored: " + name);
            }
        }
        finally { EditorSceneManager.CloseScene(boot, true); SceneManager.SetActiveScene(main); }
    }

    private static void VerifyWorkoutDisplay()
    {
        var root = new GameObject("Workout DTO verification");
        try
        {
            var item = root.AddComponent<WorkoutRecordItemUI>();
            foreach (var field in typeof(WorkoutRecordItemUI).GetFields(BindingFlags.Instance | BindingFlags.NonPublic))
            {
                if (field.FieldType != typeof(TMP_Text)) continue;
                var label = new GameObject(field.Name, typeof(RectTransform), typeof(TextMeshProUGUI));
                label.transform.SetParent(root.transform);
                field.SetValue(item, label.GetComponent<TMP_Text>());
            }
            var entry = JsonUtility.FromJson<ServerWorkoutEntry>("{\"occurred_at\":\"2026-11-19T00:00:00Z\",\"record\":{\"workout_type\":\"walking\",\"duration_seconds\":60,\"steps\":100}}");
            item.SetServerData(entry, 1);
            Require(root.GetComponentsInChildren<TMP_Text>().Any(t => t.text == "운동 종목: 걷기"), "Server workout_type displayed");
            Require(root.GetComponentsInChildren<TMP_Text>().Any(t => t.text == "걸음 수: 100"), "Watch steps displayed");
            entry.record.duration_seconds = entry.record.steps = 0;
            item.SetServerData(entry, 1);
            Require(root.GetComponentsInChildren<TMP_Text>().Any(t => t.text == "운동 시간: 측정 정보 없음"), "Legacy missing metrics retained");
        }
        finally { Object.DestroyImmediate(root); }
    }

    private static void VerifyAdventure()
    {
        var scene = EditorSceneManager.OpenScene(Adventure);
        CheckScripts(scene);
        var manager = Object.FindAnyObjectByType<AdventureManager>(FindObjectsInactive.Include);
        var battle = Object.FindAnyObjectByType<BattleController>(FindObjectsInactive.Include);
        Require(manager != null && battle != null, "Adventure and battle controllers installed");
        RequireReferences(manager, "eventManager", "battleController", "entrancePanel", "floorPanel", "descendButton");
        RequireReferences(battle, "battleManager", "battleRoot", "enemySpawner", "adventurePlayerStats");
        var stats = Object.FindAnyObjectByType<AdventurePlayerStats>(FindObjectsInactive.Include);
        Require(stats != null, "Adventure stats installed");
        stats.InitializeExploration();
        Require(stats.IsInitialized && stats.MaxHP > 0, "Adventure stats initialize");
        var temporary = new GameObject("Battle transfer verification");
        try
        {
            var unit = temporary.AddComponent<BattleUnit>();
            stats.ApplyToBattleUnit(unit);
            Require(unit.maxHP == stats.MaxHP && unit.currentHP == stats.CurrentHP, "Exploration stats enter battle");
            unit.currentHP = Math.Max(0, unit.currentHP - 1);
            stats.CaptureFromBattleUnit(unit);
            Require(stats.CurrentHP == unit.currentHP, "Battle health returns to exploration");
            var events = manager.GetComponent<AdventureEventManager>() ?? Object.FindAnyObjectByType<AdventureEventManager>();
            Require(events.GenerateEvent(10) == AdventureEventType.EliteBattle, "Tenth floor elite battle");
        }
        finally { Object.DestroyImmediate(temporary); }
        var home = Object.FindObjectsByType<Button>(FindObjectsInactive.Include).FirstOrDefault(b => b.name == "HomeButton");
        Require(home != null && home.onClick.GetPersistentMethodName(0) == "ReturnHome", "Return home connected");
    }

    private static void RequireReferences(object target, params string[] fields)
    {
        foreach (var name in fields)
            Require(typeof(Object).IsAssignableFrom(target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).FieldType) &&
                (Object)target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(target) != null, target.GetType().Name + "." + name);
    }

    private static void CheckScripts(Scene scene)
    {
        foreach (var root in scene.GetRootGameObjects())
            foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                Require(GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(transform.gameObject) == 0, "No missing script: " + transform.name);
    }

    private static void Require(bool condition, string message)
    {
        checks++;
        if (!condition) throw new InvalidOperationException("Team integration: " + message);
    }
}
