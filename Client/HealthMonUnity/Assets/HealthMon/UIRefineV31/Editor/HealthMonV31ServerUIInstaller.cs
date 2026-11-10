#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

// Safe, additive makeover for an existing HealthMon MainARScene (v3/v3+).
// It does NOT replace the scene or modify the API, quest award, dialogue, pet or evolution scripts.
public static class HealthMonV31ServerUIInstaller
{
    private const string Root = "Assets/HealthMon/UIRefineV31";
    private const string Sprites = Root + "/Resources/HMUI/";
    private static int changes;
    private static readonly Color White = Color.white;
    private static readonly Color Ink = Hex("#153A67");
    private static readonly Color SoftInk = Hex("#37597B");

    [MenuItem("Tools/HealthMon/UI v3.1 Server Ready/1. 대상 UI 확인")]
    public static void Diagnose()
    {
        var canvas = MainCanvas();
        if (canvas == null) { EditorUtility.DisplayDialog("HealthMon", "현재 씬에서 UI/Canvas/HomePanel 을 찾지 못했습니다. MainARScene을 여세요.", "확인"); return; }
        string[] names = { "HomePanel", "FoodScanPanel", "DialoguePanel", "QuestPanel", "CollectionPanel", "CustomizationPanel", "StatusPanel", "BottomNavV2", "EvolutionOverlay" };
        var found = new List<string>();
        foreach (var n in names) found.Add(n + ": " + (canvas.Find(n) != null ? "OK" : "없음"));
        found.Add("로컬 데모: " + (canvas.Find("HealthMon_LocalPreviewSystem") != null ? "설치됨 (적용 시 제거)" : "없음"));
        EditorUtility.DisplayDialog("HealthMon v3.1 / 점검", string.Join("\n", found), "확인");
    }

    [MenuItem("Tools/HealthMon/UI v3.1 Server Ready/2. 씬 백업 후 서버 UI 디자인 적용")]
    public static void Apply()
    {
        if (Application.isPlaying) { EditorUtility.DisplayDialog("HealthMon", "Play 모드를 종료한 뒤 실행하세요.", "확인"); return; }
        var scene = SceneManager.GetActiveScene();
        var canvas = MainCanvas();
        if (!scene.IsValid() || !scene.isLoaded || canvas == null || string.IsNullOrEmpty(scene.path))
        { EditorUtility.DisplayDialog("HealthMon", "저장된 MainARScene을 열어야 합니다. (UI/Canvas 확인)", "확인"); return; }
        if (!EditorUtility.DisplayDialog("HealthMon v3.1", "현재 씬을 먼저 백업하고, 기존 서버/버튼/펫 기능을 유지한 채 UI만 바꿉니다.\n\n로컬 미리보기 오브젝트는 제거합니다. 계속할까요?", "백업 후 적용", "취소")) return;
        ImportSprites();
        EnsureFolder(Root + "/Backups");
        string backupPath = Root + "/Backups/" + Path.GetFileNameWithoutExtension(scene.path) + "_PreV31_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
        if (!EditorSceneManager.SaveScene(scene, backupPath, true))
        { EditorUtility.DisplayDialog("HealthMon", "씬 백업에 실패했습니다. UI 수정은 중단합니다.", "확인"); return; }
        changes = 0;
        try
        {
            RemoveLocalPreview(canvas);
            ApplyHome(canvas.Find("HomePanel"));
            ApplyFood(canvas.Find("FoodScanPanel"));
            ApplyDialogue(canvas.Find("DialoguePanel"));
            ApplyQuest(canvas.Find("QuestPanel"));
            ApplyCollection(canvas.Find("CollectionPanel"));
            ApplyCustomization(canvas.Find("CustomizationPanel"));
            ApplyStatus(canvas.Find("StatusPanel"));
            ApplyNav(canvas);
            // Dynamic settings launcher exists only during play; style it at runtime.
            if (canvas.GetComponent<HealthMonHeaderRuntimeV31>() == null)
                Undo.AddComponent<HealthMonHeaderRuntimeV31>(canvas.gameObject);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            AssetDatabase.SaveAssets();
            Debug.Log("[HealthMon v3.1] Applied. Changed graphics/rects: " + changes + ". Backup: " + backupPath);
            EditorUtility.DisplayDialog("HealthMon v3.1", "UI 적용 완료 (수정 " + changes + "개)\n백업: " + backupPath + "\n\n기존 서버, AR 펫, 진화 및 버튼 이벤트는 수정하지 않았습니다. Play에서 화면별로 확인하세요.", "확인");
        }
        catch (Exception ex)
        {
            Debug.LogException(ex);
            EditorUtility.DisplayDialog("HealthMon v3.1", "적용 중 예외가 발생했습니다. Console을 확인해 주세요.\n백업은 " + backupPath + " 에 있습니다.", "확인");
        }
    }

    [MenuItem("Tools/HealthMon/UI v3.1 Server Ready/3. 로컬 미리보기만 제거")]
    public static void RemoveLocalOnly()
    {
        if (Application.isPlaying) { EditorUtility.DisplayDialog("HealthMon", "Play 모드를 먼저 종료하세요.", "확인"); return; }
        var canvas = MainCanvas();
        if (canvas == null) return;
        changes = 0; RemoveLocalPreview(canvas);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorUtility.DisplayDialog("HealthMon", "로컬 미리보기 오브젝트를 제거했습니다. Ctrl+S로 저장하세요. (씬/서버 기능 유지)", "확인");
    }

    [MenuItem("Tools/HealthMon/UI v3.1 Server Ready/4. 웨어러블 프리팹 디자인 (선택)")]
    public static void Wearable()
    {
        if (Application.isPlaying) return;
        string path = "Assets/HealthMon/Prefabs/Wearable/WearablePanel.prefab";
        if (AssetDatabase.LoadAssetAtPath<GameObject>(path) == null)
        { EditorUtility.DisplayDialog("HealthMon", "WearablePanel.prefab이 해당 경로에 없습니다. 건너뜁니다.", "확인"); return; }
        ImportSprites();
        var root = PrefabUtility.LoadPrefabContents(path);
        try
        {
            var images = root.GetComponentsInChildren<Image>(true);
            foreach (var im in images)
            {
                string n = im.name.ToLowerInvariant();
                if (n.Contains("icon") || n.Contains("graph") || n.Contains("chart") || n.Contains("raw") || n.Contains("preview")) continue;
                if (n.Contains("button") || n.Contains("refresh")) Paint(im, "Btn_Blue", White);
                else if (n.Contains("tab")) Paint(im, "Btn_White", White);
                else if (n.Contains("panel") || n.Contains("page") || n.Contains("card")) Paint(im, "Card_Dark", White);
            }
            PrefabUtility.SaveAsPrefabAsset(root, path);
            EditorUtility.DisplayDialog("HealthMon", "웨어러블 프리팹 UI 스타일을 적용했습니다. 데이터/버튼 코드는 유지됩니다.", "확인");
        }
        finally { PrefabUtility.UnloadPrefabContents(root); }
    }

    [MenuItem("Tools/HealthMon/UI v3.1 Server Ready/5. 백업 폴더 보기")]
    public static void ShowBackup()
    {
        string path = Root + "/Backups";
        if (AssetDatabase.IsValidFolder(path)) { Selection.activeObject = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(path); EditorGUIUtility.PingObject(Selection.activeObject); }
        else EditorUtility.DisplayDialog("HealthMon", "아직 적용 전이라 백업이 없습니다.", "확인");
    }

    private static Transform MainCanvas()
    {
        var scene = SceneManager.GetActiveScene();
        foreach (var c in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (c.gameObject.scene == scene && c.transform.Find("HomePanel") != null && c.transform.Find("DialoguePanel") != null)
                return c.transform;
        return null;
    }

    private static void RemoveLocalPreview(Transform canvas)
    {
        var go = canvas.Find("HealthMon_LocalPreviewSystem");
        if (go != null) { Undo.DestroyObjectImmediate(go.gameObject); changes++; }
        // Any demo runtime layers accidentally persisted by hand are removed too.
        foreach (var name in new [] { "HM_Demo_Quest", "HM_Demo_Dialogue", "HM_Demo_Food", "HM_Demo_Workout" })
        {
            foreach (var rt in canvas.GetComponentsInChildren<RectTransform>(true))
                if (rt != null && rt.name == name) { Undo.DestroyObjectImmediate(rt.gameObject); changes++; }
        }
    }

    private static void ApplyHome(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"TopInfoPanel", "HUD_Blue");
        ImageAt(panel,"LeftStatusPanel", "Card_Glass");
        ImageAt(panel,"SpeechBubble", "Speech_White");
        ImageAt(panel,"StatusButton", "Btn_Gold");
        RectAnchors(panel,"SpeechBubble",.09f,.118f,.91f,.19f);
        TextAt(panel,"SpeechBubble/SpeechText",Ink,32);
        foreach (string path in new [] { "TopInfoPanel/LevelText","TopInfoPanel/NameText","TopInfoPanel/ExpText","TopInfoPanel/CoinText", "LeftStatusPanel/IntimacyText","LeftStatusPanel/ActivityText","LeftStatusPanel/MoodText" }) TextAt(panel,path,White,27);
        TextAt(panel,"StatusButton/Text (TMP)",Ink,24);
    }

    private static void ApplyFood(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"", "BG_Food", White, false);
        Header(panel);
        ImageAt(panel,"CaptureView/CameraFrame", "Camera_Corners",White,false,Image.Type.Simple);
        ImageAt(panel,"CaptureView/CaptureButton", "Btn_Gold");
        ImageAt(panel,"CaptureView/AnalyzeButton", "Btn_Mint");
        // Keep camera RenderTexture/RawImage and existing callbacks untouched.
        RectAnchors(panel,"CaptureView/CameraFrame",.13f,.36f,.87f,.82f);
        RectAnchors(panel,"CaptureView/GuideText",.10f,.27f,.90f,.34f);
        RectAnchors(panel,"CaptureView/CaptureButton",.24f,.14f,.76f,.205f);
        RectAnchors(panel,"CaptureView/AnalyzeButton",.24f,.212f,.76f,.268f);
        TextAt(panel,"CaptureView/GuideText",White,28);
        ImageAt(panel,"ResultView", "Card_Dark");
        ImageAt(panel,"ResultView/ConfirmButton", "Btn_Mint");
        ImageAt(panel,"CandidateView", "Card_Dark");
    }

    private static void ApplyDialogue(Transform panel)
    {
        if (panel == null) return;
        // Only semi-transparent tint; never cover the AR camera/pet with opaque artwork.
        ImageAt(panel,"", "BG_ChatTint",new Color(1,1,1,.42f),false);
        Header(panel);
        ImageAt(panel,"FloatingSpeechBubble", "Speech_White");
        ImageAt(panel,"UserMessagePanel", "Speech_Purple");
        ImageAt(panel,"InputArea", "Card_Dark");
        ImageAt(panel,"InputArea/SendButton", "Btn_Purple");
        ImageAt(panel,"InputArea/MessageInput", "Speech_White");
        TextAt(panel,"FloatingSpeechBubble/FloatingBubbleText",Ink,30);
        TextAt(panel,"UserMessagePanel/UserMessageText",Ink,28);
        RectAnchors(panel,"InputArea",.055f,.10f,.945f,.175f);
        RectAnchors(panel,"MemoryHintText",.11f,.24f,.89f,.285f);
        // Keep CharacterArea and the 3D AR camera unmodified.
    }

    private static void ApplyQuest(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"", "BG_Quest",White,false);
        Header(panel);
        ImageAt(panel,"SummaryPanel", "HUD_Blue");
        ImageAt(panel,"QuestList", "Card_Dark");
        TextAt(panel,"InfoText",White,27);
        if (panel.GetComponent<HealthMonQuestSkinV31>() == null)
            Undo.AddComponent<HealthMonQuestSkinV31>(panel.gameObject);
        // Server-created cards are styled live after CommonServerQuestUI.Configure().
        // Never spawn fake quests or modify CommonServerQuestUI's event callbacks.
    }

    private static void ApplyCollection(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"", "BG_Collection",White,false);
        Header(panel,"Header_Lavender");
        ImageAt(panel,"CollectionSummary", "HUD_Blue");
        ImageAt(panel,"ItemGrid", "Card_Glass");
        foreach (string n in new [] { "EarringButton", "RingButton", "PendantButton", "NecklaceButton" })
            ImageAt(panel,"ItemGrid/"+n,"Tile_Lavender");
        ImageAt(panel,"SelectedItemPanel", "Card_Dark");
        ImageAt(panel,"SelectedItemPanel/CustomizeButton", "Btn_Gold");
        RectAnchors(panel,"CollectionSummary",.09f,.81f,.91f,.90f);
        RectAnchors(panel,"ItemGrid",.075f,.40f,.925f,.80f);
        RectAnchors(panel,"SelectedItemPanel",.09f,.15f,.91f,.30f);
        TextAt(panel,"SelectedItemPanel/SelectedItemNameText",White,30);
        TextAt(panel,"SelectedItemPanel/SelectedItemDescriptionText",White,25);
    }

    private static void ApplyCustomization(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"", "BG_Customization",White,false);
        Header(panel,"Header_Lavender");
        ImageAt(panel,"CharacterPreview", "Card_Lavender");
        ImageAt(panel,"ItemInfoPanel", "Card_Dark");
        ImageAt(panel,"ItemInfoPanel/EquipButton", "Btn_Gold");
        ImageAt(panel,"Jewelry3DPalette", "Card_Glass");
        ImageAt(panel,"JewelryAdjustPanel", "Card_Dark");
        ImageAt(panel,"JewelryAdjustPanel/SaveButton", "Btn_Mint");
        ImageAt(panel,"JewelryAdjustPanel/ResetButton", "Btn_White");
        ImageAt(panel,"JewelryAdjustPanel/CloseButton", "Btn_Purple");
        // Do NOT change CharacterPreview/PetPreviewImage, its RenderTexture or jewelry rig.
    }

    private static void ApplyStatus(Transform panel)
    {
        if (panel == null) return;
        ImageAt(panel,"", "BG_Status",White,false);
        Header(panel);
        ImageAt(panel,"ProfilePanel","HUD_Blue");
        ImageAt(panel,"StatPanel","Card_Glass");
        ImageAt(panel,"GrowthPanel","Card_Lavender");
    }

    private static void ApplyNav(Transform canvas)
    {
        Transform nav = canvas.Find("BottomNavV2") ?? canvas.Find("BottomNav");
        if (nav == null) return;
        ImageAt(nav,"", "Card_Nav");
        foreach (string name in new [] { "HomeButton", "FoodButton", "DialogueButton", "QuestButton", "CollectionButton", "WearableButton" })
        {
            foreach (var img in nav.GetComponentsInChildren<Image>(true))
            {
                if (img.name != name || img.GetComponent<Button>() == null) continue;
                Paint(img, "Nav_Idle", White);
            }
        }
        // Nav Highlighter writes the selected/normal sprites every frame.
        // Update its serialized sprite references, not its callbacks.
        foreach (var highlighter in canvas.GetComponentsInChildren<HealthMonSixNavHighlighter>(true))
        {
            var so = new SerializedObject(highlighter);
            var normal = so.FindProperty("normalSprite");
            var selected = so.FindProperty("selectedSprite");
            if (normal != null) normal.objectReferenceValue = SpriteAt("Nav_Idle");
            if (selected != null) selected.objectReferenceValue = SpriteAt("Nav_Selected");
            so.ApplyModifiedProperties();
        }
    }

    private static void Header(Transform panel, string name = "Header_Ocean")
    {
        ImageAt(panel,"Header",name);
        ImageAt(panel,"Header/BackButton","Btn_Blue");
        TextAt(panel,"Header/TitleText",White,34);
        // Reserve right space for the settings launcher injected at runtime.
        var rt = panel.Find("Header/TitleText") as RectTransform;
        if (rt != null && rt.anchorMin.x < .5f && rt.anchorMax.x > .5f)
        {
            Undo.RecordObject(rt,"HealthMon title layout");
            rt.offsetMin = new Vector2(95,rt.offsetMin.y);
            rt.offsetMax = new Vector2(-165,rt.offsetMax.y);
        }
    }

    private static void ImageAt(Transform root, string path, string sprite, Color? color = null, bool raycast = true, Image.Type type = Image.Type.Sliced)
    {
        var t = string.IsNullOrEmpty(path) ? root : root.Find(path);
        if (t == null) return;
        var image = t.GetComponent<Image>();
        if (image != null) { Paint(image,sprite,color ?? White,type); if (!raycast) image.raycastTarget=false; }
    }

    private static void Paint(Image image, string sprite, Color color, Image.Type type = Image.Type.Sliced)
    {
        if (image == null) return;
        var asset = SpriteAt(sprite);
        if (asset == null) return;
        Undo.RecordObject(image,"HealthMon sprite redesign");
        image.sprite=asset; image.type=type; image.color=color;
        image.preserveAspect=false;
        EditorUtility.SetDirty(image); changes++;
    }

    private static void TextAt(Transform root, string path, Color col, float max)
    {
        var t = root.Find(path);
        if (t == null) return;
        var txt = t.GetComponent<TMP_Text>();
        if (txt == null) return;
        Undo.RecordObject(txt,"HealthMon legible text");
        txt.color=col; txt.enableAutoSizing=true; txt.fontSizeMin=max*.66f;txt.fontSizeMax=max;
        EditorUtility.SetDirty(txt); changes++;
    }

    private static void RectAnchors(Transform root,string path,float x0,float y0,float x1,float y1)
    {
        var rect = root.Find(path) as RectTransform;
        if (rect == null) return;
        Undo.RecordObject(rect,"HealthMon layout spacing");
        rect.anchorMin=new Vector2(x0,y0);rect.anchorMax=new Vector2(x1,y1);
        rect.offsetMin=rect.offsetMax=Vector2.zero;
        EditorUtility.SetDirty(rect);changes++;
    }

    private static Sprite SpriteAt(string name)
    { return AssetDatabase.LoadAssetAtPath<Sprite>(Sprites + name + ".png"); }
    private static Color Hex(string hex) { ColorUtility.TryParseHtmlString(hex,out var c);return c; }

    private static void ImportSprites()
    {
        foreach (string path in Directory.GetFiles(Sprites,"*.png"))
        {
            var assetPath = path.Replace('\\','/');
            var imp = AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if (imp == null) continue;
            bool changed = imp.textureType!=TextureImporterType.Sprite || imp.spriteImportMode!=SpriteImportMode.Single || imp.spriteBorder!=new Vector4(30,30,30,30);
            if (!changed) continue;
            imp.textureType=TextureImporterType.Sprite;
            imp.spriteImportMode=SpriteImportMode.Single;
            imp.mipmapEnabled=false;
            imp.alphaIsTransparency=true;
            imp.spritePixelsPerUnit=100;
            // 9-slice border is contained within every panel/CTA texture.
            imp.spriteBorder=new Vector4(30,30,30,30);
            imp.SaveAndReimport();
        }
        AssetDatabase.Refresh();
    }

    private static void EnsureFolder(string folder)
    {
        if (AssetDatabase.IsValidFolder(folder)) return;
        var parent=Path.GetDirectoryName(folder).Replace('\\','/');
        EnsureFolder(parent);
        AssetDatabase.CreateFolder(parent,Path.GetFileName(folder));
    }
}
#endif
