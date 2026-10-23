#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class PortraitGameUIEditor
{
    public const string MainScene = "Assets/HealthMon/Scenes/MainARScene.unity";
    [InitializeOnLoadMethod]
    private static void ConfigureEditorView()
    {
        if (Application.isBatchMode) return;
        EditorApplication.delayCall += () => {
            if (UnityEngine.Object.FindAnyObjectByType<PortraitGameUI>() != null) SelectPortraitGameView();
        };
    }
    [MenuItem("HealthMon/UI/Apply portrait game UI")]
    public static void ApplyProject()
    {
        const string materialPath = "Assets/HealthMon/Resources/HealthMon/PortraitUI/Backgrounds/PortraitEnvironment.mat";
        var environment = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
        if (environment == null)
        {
            environment = new Material(Shader.Find("Universal Render Pipeline/Unlit"));
            environment.mainTexture = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/HealthMon/Resources/HealthMon/PortraitUI/Backgrounds/home-stage-portrait.png");
            environment.SetFloat("_Cull", 0); AssetDatabase.CreateAsset(environment, materialPath);
        }
        var scene = EditorSceneManager.OpenScene(MainScene);
        var owner = UnityEngine.Object.FindAnyObjectByType<UIManager>(FindObjectsInactive.Include);
        if (owner == null) throw new InvalidOperationException("MainARScene must retain its UIManager.");
        var canvas = owner.GetComponentInParent<Canvas>();
        if (canvas == null) foreach (var candidate in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include))
            if (candidate.transform.Find("HomePanel") != null) { canvas = candidate; break; }
        if (canvas == null) throw new InvalidOperationException("The existing Canvas was not found.");
        var theme = canvas.GetComponent<PortraitGameUI>() ?? canvas.gameObject.AddComponent<PortraitGameUI>();
        var mode = canvas.renderMode;
        canvas.renderMode = RenderMode.WorldSpace;
        ((RectTransform)canvas.transform).sizeDelta = new Vector2(1080, 2400);
        theme.ApplyNow();
        canvas.renderMode = mode;
        PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
        PlayerSettings.allowedAutorotateToPortrait = true;
        PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
        PlayerSettings.allowedAutorotateToLandscapeLeft = false;
        PlayerSettings.allowedAutorotateToLandscapeRight = false;
        EditorSceneManager.MarkSceneDirty(scene); EditorSceneManager.SaveScene(scene); AssetDatabase.SaveAssets();
        if (!Application.isBatchMode) SelectPortraitGameView();
        Debug.Log("HEALTHMON_PORTRAIT_APPLIED scene=" + MainScene);
    }

    [MenuItem("HealthMon/UI/Select portrait Game view")]
    public static void SelectPortraitGameView()
    {
        // Editor-only convenience; the runtime has no dependency on these editor internals.
        try
        {
            var assembly = typeof(Editor).Assembly;
            var sizesType = assembly.GetType("UnityEditor.GameViewSizes");
            var singleton = typeof(ScriptableSingleton<>).MakeGenericType(sizesType);
            var sizes = singleton.GetProperty("instance", BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy).GetValue(null);
            var groupType = assembly.GetType("UnityEditor.GameViewSizeGroupType");
            var group = sizesType.GetMethod("GetGroup").Invoke(sizes, new[] { Enum.Parse(groupType, "Standalone") });
            var type = group.GetType();
            int builtins = (int)type.GetMethod("GetBuiltinCount").Invoke(group, null);
            int custom = (int)type.GetMethod("GetCustomCount").Invoke(group, null);
            int index = -1;
            for (int i = 0; i < builtins + custom; i++)
            {
                var size = type.GetMethod("GetGameViewSize").Invoke(group, new object[] { i });
                if ((int)size.GetType().GetProperty("width").GetValue(size) == 1080 && (int)size.GetType().GetProperty("height").GetValue(size) == 2400) { index = i; break; }
            }
            if (index < 0)
            {
                var sizeType = assembly.GetType("UnityEditor.GameViewSize");
                var modeType = assembly.GetType("UnityEditor.GameViewSizeType");
                var size = Activator.CreateInstance(sizeType, new object[] { Enum.Parse(modeType, "FixedResolution"), 1080, 2400, "HealthMon portrait" });
                type.GetMethod("AddCustomSize").Invoke(group, new[] { size }); index = builtins + custom;
            }
            var gameView = assembly.GetType("UnityEditor.GameView");
            var window = EditorWindow.GetWindow(gameView);
            gameView.GetProperty("selectedSizeIndex", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).SetValue(window, index);
            window.Repaint();
        }
        catch (Exception error) { Debug.LogWarning("Choose 1080 x 2400 in the Game view: " + error.GetBaseException().Message); }
    }

    public static void VerifyGeometry()
    {
        ApplyProject();
        var theme = UnityEngine.Object.FindAnyObjectByType<PortraitGameUI>();
        var canvas = theme.GetComponent<Canvas>(); var manager = UnityEngine.Object.FindAnyObjectByType<UIManager>();
        var food = UnityEngine.Object.FindAnyObjectByType<FoodScanPrototype>(FindObjectsInactive.Include);
        var connection = UnityEngine.Object.FindAnyObjectByType<Healthmon.Common.CommonServerConnection>(FindObjectsInactive.Include);
        var home = canvas.transform.Find("HomePanel").gameObject;
        var status = canvas.transform.Find("StatusPanel").gameObject;
        var admin = canvas.transform.Find("AdminPanel").gameObject;
        var petUI = manager.GetComponent<PetExperienceUI>() ?? manager.gameObject.AddComponent<PetExperienceUI>();
        petUI.Configure(manager, home, status, admin);
        var quests = canvas.transform.Find("QuestPanel");
        var serverQuests = quests.GetComponent<CommonServerQuestUI>() ?? quests.gameObject.AddComponent<CommonServerQuestUI>(); serverQuests.Configure();
        typeof(FoodScanPrototype).GetMethod("Start", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(food, null);
        theme.ApplyNow(); Canvas.ForceUpdateCanvases();
        int count = 0;
        Action<bool,string> check = (ok, text) => { count++; if (!ok) throw new InvalidOperationException("Portrait UI verification: " + text); };
        check(PlayerSettings.defaultInterfaceOrientation == UIOrientation.Portrait, "mobile orientation");
        check(canvas.GetComponent<CanvasScaler>().referenceResolution == new Vector2(1080, 2400), "canvas reference");
        foreach (string button in new[] { "HomeButton", "FoodButton", "PetARButton", "DialogueButton", "QuestButton", "CollectionButton", "WearableButton" })
        {
            var target = canvas.transform.Find("BottomNav/" + button).GetComponent<Button>();
            check(target != null && target.targetGraphic != null, button + " retained");
            check(target.onClick.GetPersistentEventCount() > 0 || button == "PetARButton", button + " existing scene event retained");
            check(target.GetComponent<Image>().sprite != null, button + " sprite");
        }
        check(canvas.transform.Find("UnifiedSettingsButton").GetComponent<Button>() != null, "settings launcher");
        check(canvas.transform.Find("FoodScanPanel/ResultView/ConfirmButton").GetComponent<Button>().onClick.GetPersistentEventCount() > 0, "record event retained");
        check(canvas.transform.Find("DialoguePanel/InputArea/SendButton").GetComponent<Button>().onClick.GetPersistentEventCount() > 0, "send event retained");
        check(theme.Sprite("Backgrounds/home-stage-portrait") != null, "portrait background imported");
        check(theme.Sprite("Components/button-primary-disabled") != null, "disabled state imported");
        theme.ApplyNow(); theme.ApplyNow();
        var fixedButton = canvas.transform.Find("AdminPanel/MobileSettingsSafeArea/PortraitFixedActions").GetComponentInChildren<Button>();
        check(fixedButton != null && fixedButton.GetComponentInChildren<TMPro.TMP_Text>().text.Contains("캐릭터·성격 적용"), "repeated refresh retains apply action, not fresh-pet creation");
        check(AssetDatabase.LoadAssetAtPath<Material>("Assets/HealthMon/Resources/HealthMon/PortraitUI/Backgrounds/PortraitEnvironment.mat") != null, "environment shader retained in build");
        var adminRoot = canvas.transform.Find("AdminPanel/MobileSettingsSafeArea");
        string[] actions = { "캐릭터·성격 적용", "운동 테스트 기록 추가", "현재 퀘스트·진행 상황 보기", "서버 연결 / 연결 변경" };
        for (int i = 0; i < actions.Length; i++)
        {
            adminRoot.Find("Tabs/Tab" + i).GetComponent<Button>().onClick.Invoke(); theme.ApplyNow(); theme.ApplyNow();
            int visibleActions = 0;
            foreach (var button in adminRoot.Find("PortraitFixedActions").GetComponentsInChildren<Button>(true))
                if (button.gameObject.activeSelf) { visibleActions++; check(button.GetComponentInChildren<TMPro.TMP_Text>().text == actions[i], "tab callback keeps its correct primary action " + i); }
            check(visibleActions == 1, "exactly one fixed action for tab " + i);
        }
        adminRoot.Find("Tabs/Tab0").GetComponent<Button>().onClick.Invoke();
        typeof(PortraitGameUI).GetMethod("OnEnable", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(theme, null);
        theme.ApplyNow();
        check(adminRoot.Find("PortraitFixedActions").GetComponentInChildren<Button>().GetComponentInChildren<TMPro.TMP_Text>().text == actions[0], "action mapping survives theme re-enable");
        foreach (string meal in new[] { "breakfast", "lunch", "dinner", "snack" })
        {
            canvas.transform.Find("FoodScanPanel/ResultView/FoodConfirmationScroll/Viewport/Content/MealTypeChoices/Meal_" + meal).GetComponent<Button>().onClick.Invoke();
            check(food.SelectedMealType == meal, "meal callback " + meal);
        }
        food.SelectMealType(null);
        var foodEvent = canvas.transform.Find("BottomNav/FoodButton").GetComponent<Button>().onClick;
        check(foodEvent.GetPersistentTarget(0) == manager && foodEvent.GetPersistentMethodName(0) == "ShowFoodScan", "food navigation target");
        // Scene events are RuntimeOnly; invoke their verified targets while this editor test is outside Play mode.
        manager.ShowFoodScan();
        check(canvas.transform.Find("FoodScanPanel").gameObject.activeSelf && !home.activeSelf, "existing food navigation callback");
        var homeEvent = canvas.transform.Find("BottomNav/HomeButton").GetComponent<Button>().onClick;
        check(homeEvent.GetPersistentTarget(0) == manager && homeEvent.GetPersistentMethodName(0) == "ShowHome", "home navigation target");
        manager.ShowHome(); theme.ApplyNow();
        var launcher = (RectTransform)canvas.transform.Find("UnifiedSettingsButton"); var position = launcher.anchoredPosition;
        typeof(MobileAdminMenu).GetMethod("Update", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(UnityEngine.Object.FindAnyObjectByType<MobileAdminMenu>(), null);
        check(launcher.anchoredPosition == position && launcher.gameObject.activeSelf, "legacy Update keeps portrait settings reachable");
        Debug.Log("HEALTHMON_PORTRAIT_GEOMETRY_PASS assertions=" + count);
        // Runtime-generated controls are intentionally not saved into the scene.
    }
}
#endif
