#if UNITY_EDITOR
using System;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class HealthMonUIV4PolishEditor
{
    private const string Base = "Assets/HealthMon/UIStyleKitV3/Sprites/";

    [MenuItem("Tools/HealthMon/UI v4/1. 현재 MainARScene 백업 후 새 디자인 적용")]
    public static void Apply()
    {
        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || scene.name != "MainARScene" || string.IsNullOrEmpty(scene.path))
        {
            EditorUtility.DisplayDialog("HealthMon UI v4", "MainARScene을 먼저 열고, Play 모드를 종료해 주세요.", "확인");
            return;
        }
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("HealthMon UI v4", "Play 모드에서는 적용할 수 없습니다.", "확인");
            return;
        }
        if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
        if (!EditorUtility.DisplayDialog("HealthMon UI v4", "현재 씬의 백업을 만든 뒤 UI의 배경·헤더·버튼·카드만 정리합니다.\n기존 이벤트·서버·3D 캐릭터·진화 로직은 수정하지 않습니다.", "백업 후 적용", "취소")) return;
        var src = scene.path;
        const string folder = "Assets/HealthMon/UIStyleKitV4/SceneBackups";
        Directory.CreateDirectory(folder);
        AssetDatabase.Refresh();
        string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string backup = AssetDatabase.GenerateUniqueAssetPath(folder + "/MainARScene_BeforeUIv4_" + stamp + ".unity");
        if (!AssetDatabase.CopyAsset(src, backup))
        {
            EditorUtility.DisplayDialog("HealthMon UI v4", "씬 백업을 만들지 못했습니다. 적용을 중지합니다.", "확인");
            return;
        }

        var canvas = FindMainCanvas(scene);
        if (canvas == null)
        {
            EditorUtility.DisplayDialog("HealthMon UI v4", "UI/Canvas를 찾지 못했습니다. 씬 백업만 생성했습니다.", "확인");
            return;
        }
        int changes = 0;
        // All placements are existing RectTransforms. No button listeners or 3D objects are touched.
        changes += Style(canvas, "HomePanel/TopInfoPanel", "Cards/Card_HUD");
        changes += Style(canvas, "HomePanel/LeftStatusPanel", "Cards/Card_Status");
        changes += Style(canvas, "HomePanel/SpeechBubble", "Cards/Card_Chat");
        changes += Style(canvas, "HomePanel/StatusButton", "Buttons/BTN_Gold");
        changes += Style(canvas, "FoodScanPanel", "Backgrounds/BG_Food");
        changes += Style(canvas, "FoodScanPanel/Header", "Bars/Bar_Header");
        changes += Style(canvas, "FoodScanPanel/CaptureView", "Cards/Card_Glass");
        changes += Style(canvas, "FoodScanPanel/CaptureView/CameraFrame", "Cards/Card_LightOutline");
        changes += Style(canvas, "FoodScanPanel/CaptureView/CaptureButton", "Buttons/BTN_Gold");
        changes += Style(canvas, "FoodScanPanel/CaptureView/AnalyzeButton", "Buttons/BTN_Mint");
        changes += Style(canvas, "DialoguePanel", "Backgrounds/BG_Dialogue");
        changes += Style(canvas, "DialoguePanel/Header", "Bars/Bar_Header");
        changes += Style(canvas, "DialoguePanel/CharacterArea", "Cards/Card_Preview", .30f);
        changes += Style(canvas, "DialoguePanel/FloatingSpeechBubble", "Cards/Card_Chat");
        changes += Style(canvas, "DialoguePanel/InputArea", "Cards/Card_Blue");
        changes += Style(canvas, "DialoguePanel/InputArea/MessageInput", "Buttons/BTN_White");
        changes += Style(canvas, "DialoguePanel/InputArea/SendButton", "Buttons/BTN_Violet");
        changes += Style(canvas, "QuestPanel", "Backgrounds/BG_Quest");
        changes += Style(canvas, "QuestPanel/Header", "Bars/Bar_Header");
        changes += Style(canvas, "QuestPanel/SummaryPanel", "Cards/Card_Blue");
        changes += Style(canvas, "QuestPanel/QuestList", "Cards/Card_EmptyPanel", .90f);
        changes += Style(canvas, "CollectionPanel", "Backgrounds/BG_Collection");
        changes += Style(canvas, "CollectionPanel/Header", "Bars/Bar_Header");
        changes += Style(canvas, "CollectionPanel/ItemGrid", "Cards/Card_Glass", .58f);
        changes += Style(canvas, "CollectionPanel/SelectedItemPanel", "Cards/Card_Blue");
        changes += Style(canvas, "CustomizationPanel", "Backgrounds/BG_Customization");
        changes += Style(canvas, "CustomizationPanel/Header", "Bars/Bar_Header");
        changes += Style(canvas, "CustomizationPanel/CharacterPreview", "Cards/Card_Preview", .30f);
        changes += Style(canvas, "CustomizationPanel/JewelryAdjustPanel", "Cards/Card_Blue", .95f);
        changes += Style(canvas, "BottomNavV2", "Cards/Card_NavBar");
        changes += Style(canvas, "StatusPanel", "Backgrounds/BG_Status");
        changes += Style(canvas, "RewardPanel", "Backgrounds/BG_Reward");
        // Keep important instructions above the persistent two-row bottom navigation.
        Move(canvas, "QuestPanel/InfoText", new Vector2(0, 320), new Vector2(900, 120));
        TextSize(canvas, "QuestPanel/InfoText", 25);
        // The jewelry edit controls used to sit partly behind BottomNavV2.
        Move(canvas, "CustomizationPanel/JewelryAdjustPanel", new Vector2(0, 545), new Vector2(900, 510));
        // The dialogue was black in the user's screenshots despite a background sprite.
        // A backdrop child, drawn before the foreground children, protects against a missing panel fill.
        var dialogue = canvas.Find("DialoguePanel") as RectTransform;
        if (dialogue != null)
        {
            var backdrop = dialogue.Find("HMV4_DialogueBackdrop") as RectTransform;
            if (backdrop == null)
            {
                var go = new GameObject("HMV4_DialogueBackdrop", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
                Undo.RegisterCreatedObjectUndo(go, "HealthMon v4 Dialogue backdrop");
                go.transform.SetParent(dialogue, false);
                backdrop = (RectTransform)go.transform;
                backdrop.anchorMin = Vector2.zero; backdrop.anchorMax = Vector2.one;
                backdrop.offsetMin = Vector2.zero; backdrop.offsetMax = Vector2.zero;
                backdrop.SetAsFirstSibling();
                changes++;
            }
            var img = backdrop.GetComponent<Image>();
            var sprite = Load("Backgrounds/BG_Dialogue");
            if (img != null && sprite != null)
            {
                Undo.RecordObject(img, "HealthMon v4 dialogue backdrop");
                img.sprite = sprite; img.type = Image.Type.Simple;
                img.color = Color.white; img.raycastTarget = false;
                EditorUtility.SetDirty(img);
            }
        }
        // Color the temporary test button as a compact pill; keep its original onClick intact.
        var testButton = canvas.Find("DEV_EvolutionStartButton (출시 전 숨김)");
        if (testButton != null)
        {
            var tx = testButton.GetComponentInChildren<TMP_Text>(true);
            if (tx != null) { Undo.RecordObject(tx, "HealthMon v4 test caption"); tx.fontSize = 19f; }
        }
        var skin = canvas.GetComponent<HealthMonUIV4RuntimeSkin>();
        if (skin == null) skin = Undo.AddComponent<HealthMonUIV4RuntimeSkin>(canvas.gameObject);
        Undo.RecordObject(skin, "HealthMon v4 settings style");
        var ev = canvas.Find("EvolutionOverlay");
        skin.Configure(Load("Buttons/BTN_Dark"), ev == null ? null : ev.gameObject);
        EditorUtility.SetDirty(skin);
        EditorSceneManager.MarkSceneDirty(scene);
        EditorSceneManager.SaveScene(scene);
        AssetDatabase.SaveAssets();
        EditorUtility.DisplayDialog("HealthMon UI v4 적용 완료", "원본 씬을 백업하고 스타일을 적용했습니다.\n수정된 이미지: " + changes + "곳\n백업: " + backup + "\n\nPlay로 화면을 확인해 주세요.", "확인");
    }

    private static RectTransform FindMainCanvas(Scene scene)
    {
        foreach (var root in scene.GetRootGameObjects())
        {
            if (root.name != "UI") continue;
            var candidate = root.transform.Find("Canvas") as RectTransform;
            if (candidate != null && candidate.Find("HomePanel") != null) return candidate;
        }
        return null;
    }

    private static Sprite Load(string relative) => AssetDatabase.LoadAssetAtPath<Sprite>(Base + relative + ".png");
    private static void Move(Transform canvas, string path, Vector2 pos, Vector2 size)
    {
        var rect = canvas.Find(path) as RectTransform;
        if (rect == null) return;
        Undo.RecordObject(rect, "HealthMon UI v4 spacing " + path);
        rect.anchoredPosition = pos;
        rect.sizeDelta = size;
        EditorUtility.SetDirty(rect);
    }
    private static void TextSize(Transform canvas, string path, float size)
    {
        var t = canvas.Find(path);
        if (t == null) return;
        var text = t.GetComponent<TMP_Text>();
        if (text == null) return;
        Undo.RecordObject(text, "HealthMon UI v4 text size " + path);
        text.fontSize = size;
        EditorUtility.SetDirty(text);
    }
    private static int Style(Transform canvas, string path, string asset, float opacity = 1f)
    {
        var t = canvas.Find(path);
        if (t == null) return 0;
        var image = t.GetComponent<Image>();
        var sprite = Load(asset);
        if (image == null || sprite == null) return 0;
        Undo.RecordObject(image, "HealthMon UI v4 image " + path);
        image.sprite = sprite;
        image.type = asset.StartsWith("Backgrounds/") ? Image.Type.Simple : Image.Type.Sliced;
        image.color = new Color(1f, 1f, 1f, opacity);
        // An input or button requires raycast events. Never disable them on interactive graphics.
        if (asset.StartsWith("Backgrounds/") && t.GetComponent<Selectable>() == null)
            image.raycastTarget = false;
        EditorUtility.SetDirty(image);
        return 1;
    }
}
#endif
