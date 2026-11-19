#if UNITY_EDITOR
using System;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

/// <summary>
/// Surgical restoration for the existing HealthMon scene after the Assets cleanup.
/// Does not create, replace or delete any gameplay object, listeners, scripts or PlayerPrefs.
/// </summary>
public static class HealthMonUIRecovery20261119
{
    private const string Root = "Assets/HealthMon/UIRecoveryV1";
    private const string Sprites = Root + "/RecoveredSprites/";
    private const string BackupFolder = Root + "/Backups";

    private static readonly Color DarkInk = Hex("#153A67");
    private static readonly Color PaleBlue = Hex("#D7F2FF");
    private static readonly Color Gold = Hex("#FFE59B");

    private static Color Hex(string value)
    {
        ColorUtility.TryParseHtmlString(value, out var result);
        return result;
    }

    private static Sprite LoadSprite(string path) => AssetDatabase.LoadAssetAtPath<Sprite>(path);

    private static Transform MainCanvas()
    {
        foreach (var canvas in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
        {
            if (canvas.transform.Find("HomePanel") != null && canvas.transform.Find("QuestPanel") != null)
                return canvas.transform;
        }
        return null;
    }

    [MenuItem("Tools/HealthMon/UI Recovery/1. 이미지/화면 진단")]
    public static void Diagnose()
    {
        var main = MainCanvas();
        string[] assets =
        {
            "Admin_ScrollView_Backdrop", "Admin_Close_Button", "Icon_Food_Raw",
            "Icon_Dialogue_Raw", "Icon_Quest_Raw", "Icon_Collection_Raw",
            "Icon_Wearable_Raw", "QuestCard_Refined"
        };
        int found = 0;
        foreach (var name in assets)
        {
            string path = Sprites + name + ".png";
            var sprite = LoadSprite(path);
            if (sprite == null) Debug.LogError("[HM UI Recovery] 스프라이트 임포트 확인 필요: " + path);
            else found++;
        }
        int rawCount = 0;
        Transform nav = main != null ? main.Find("BottomNavV2") : null;
        if (nav != null)
        {
            foreach (RawImage raw in nav.GetComponentsInChildren<RawImage>(true))
                if (raw.name == "RawImage" && raw.GetComponentInParent<Button>() != null)
                    rawCount++;
        }
        string message = "현재 메인 Canvas: " + (main != null ? "확인" : "없음") +
            "\n복구용 스프라이트: " + found + " / " + assets.Length +
            "\n하단 메뉴 RawImage: " + rawCount + "개" +
            "\nAdminPanel: " + (main != null && main.Find("AdminPanel") != null ? "확인" : "없음") +
            "\nQuestPanel: " + (main != null && main.Find("QuestPanel") != null ? "확인" : "없음") +
            "\n\nSprite가 8/8인지 확인한 다음 복구 메뉴를 실행하세요.";
        Debug.Log("[HM UI Recovery]\n" + message);
        EditorUtility.DisplayDialog("HealthMon UI 복구 진단", message, "확인");
    }

    [MenuItem("Tools/HealthMon/UI Recovery/2. 씬 백업 후 UI 복구")]
    public static void Repair()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("HealthMon UI 복구", "Play 모드를 종료하고 실행하세요.", "확인");
            return;
        }
        Scene scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || scene.name != "MainARScene" || string.IsNullOrEmpty(scene.path))
        {
            EditorUtility.DisplayDialog("HealthMon UI 복구", "MainARScene을 열고 저장한 후 실행하세요.", "확인");
            return;
        }
        Transform main = MainCanvas();
        if (main == null)
        {
            EditorUtility.DisplayDialog("HealthMon UI 복구", "UI/Canvas 아래 HomePanel과 QuestPanel을 찾지 못했습니다.", "확인");
            return;
        }
        if (LoadSprite(Sprites + "QuestCard_Refined.png") == null ||
            LoadSprite(Sprites + "Admin_ScrollView_Backdrop.png") == null)
        {
            EditorUtility.DisplayDialog("HealthMon UI 복구", "이미지 임포트가 완료되지 않았어요. UIRecoveryV1의 PNG를 Reimport 해주세요.", "확인");
            return;
        }
        if (!EditorUtility.DisplayDialog("HealthMon UI 복구", "현재 MainARScene을 백업한 뒤 하단 아이콘·관리자 배경·퀘스트 카드만 복구합니다.\n\n서버, 퀘스트 보상, 코인, 캐릭터 전환, PlayerPrefs는 변경하지 않습니다.", "백업 후 복구", "취소"))
            return;
        try
        {
            if (!EditorSceneManager.SaveScene(scene)) throw new Exception("씬 저장에 실패했습니다.");
            if (!AssetDatabase.IsValidFolder(BackupFolder)) AssetDatabase.CreateFolder(Root, "Backups");
            string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string backup = BackupFolder + "/MainARScene_BeforeUIRecovery_" + stamp + ".unity";
            if (!AssetDatabase.CopyAsset(scene.path, backup)) throw new Exception("씬 백업 생성 실패. 복구를 중단합니다.");
            Debug.Log("[HM UI Recovery] 원본 씬 백업: " + backup);

            int nav = RepairNav(main.Find("BottomNavV2"));
            int admin = RepairAdmin(main.Find("AdminPanel"));
            int quest = RepairQuests(main.Find("QuestPanel"));
            int wearable = RepairWearable(main.Find("WearablePanel"));
            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene)) throw new Exception("수정된 씬 저장에 실패했습니다. 백업에서 되돌릴 수 있습니다.");
            EditorUtility.DisplayDialog("HealthMon UI 복구 완료",
                "복구 완료!\n하단 아이콘 " + nav + "개\n관리자 요소 " + admin + "개\n퀘스트 카드 " + quest + "개\n웨어러블 탭 " + wearable + "개\n\n백업 위치: " + backup + "\n\nPlay 실행 후 3개 화면을 확인하세요.", "확인");
        }
        catch (Exception ex)
        {
            Debug.LogException(ex);
            EditorUtility.DisplayDialog("HealthMon UI 복구 실패", ex.Message + "\n\n변경 전 백업 씬을 복원할 수 있습니다.", "확인");
        }
    }

    [MenuItem("Tools/HealthMon/UI Recovery/3. 백업 폴더 열기")]
    public static void RevealBackup()
    {
        if (!AssetDatabase.IsValidFolder(BackupFolder)) AssetDatabase.CreateFolder(Root, "Backups");
        EditorUtility.RevealInFinder(Path.GetFullPath(BackupFolder));
    }

    [MenuItem("Tools/HealthMon/UI Recovery/4. BootScene 시작화면 복구 (선택)")]
    public static void RepairBootScene()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode) { EditorUtility.DisplayDialog("HealthMon UI 복구", "Play를 종료하세요.", "확인"); return; }
        var scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || scene.name != "BootScene" || string.IsNullOrEmpty(scene.path))
        { EditorUtility.DisplayDialog("HealthMon UI 복구", "먼저 BootScene을 열어주세요.", "확인"); return; }
        GameObject root = null;
        foreach (var canvas in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (canvas.name == "HealthMonFirstRunCanvas") { root = canvas.gameObject; break; }
        if (root == null) { EditorUtility.DisplayDialog("HealthMon UI 복구", "HealthMonFirstRunCanvas를 찾지 못했습니다.", "확인"); return; }
        if (!EditorUtility.DisplayDialog("HealthMon UI 복구", "BootScene의 누락된 시작 카드·확인 버튼 이미지도 보정할까요? 백업 후 적용합니다.", "백업 후 복구", "취소")) return;
        try
        {
            if (!EditorSceneManager.SaveScene(scene)) throw new Exception("씬 저장 실패");
            if (!AssetDatabase.IsValidFolder(BackupFolder)) AssetDatabase.CreateFolder(Root, "Backups");
            string backup = BackupFolder + "/BootScene_BeforeUIRecovery_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
            if (!AssetDatabase.CopyAsset(scene.path, backup)) throw new Exception("백업 생성 실패");
            int changes = 0;
            var startPanel = root.transform.Find("Panel");
            var bg = startPanel != null ? startPanel.GetComponent<Image>() : null;
            var bgSprite = LoadSprite("Assets/HealthMon/UIStyleKitV3/Sprites/Cards/Card_Dark.png");
            if (bg != null && bg.sprite == null && bgSprite != null)
            {
                Undo.RecordObject(bg, "Restore BootScene panel"); bg.sprite=bgSprite; bg.type=Image.Type.Sliced;
                bg.color=Color.white; changes++;
            }
            var setupCard = root.transform.Find("FirstSetupPanel/SetupCard");
            var cardImage = setupCard != null ? setupCard.GetComponent<Image>() : null;
            var cardSprite = LoadSprite("Assets/HealthMon/UIStyleKitV3/Sprites/Cards/Card_Blue.png");
            if (cardImage != null && cardImage.sprite == null && cardSprite != null)
            {
                Undo.RecordObject(cardImage, "Restore setup card"); cardImage.sprite=cardSprite; cardImage.type=Image.Type.Sliced;
                cardImage.color=Color.white; changes++;
            }
            var confirm = root.transform.Find("FirstSetupPanel/SetupCard/ConfirmSetupButton");
            var buttonImage = confirm != null ? confirm.GetComponent<Image>() : null;
            var buttonSprite = LoadSprite("Assets/HealthMon/UIStyleKitV3/Sprites/Buttons/BTN_Gold.png");
            if (buttonImage != null && buttonImage.sprite == null && buttonSprite != null)
            {
                Undo.RecordObject(buttonImage, "Restore setup confirmation button"); buttonImage.sprite=buttonSprite;
                buttonImage.type=Image.Type.Sliced; buttonImage.color=Color.white; changes++;
            }
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            EditorUtility.DisplayDialog("BootScene UI 복구", "누락 이미지 " + changes + "곳 수정했습니다.\n백업: " + backup, "확인");
        }
        catch(Exception ex) { Debug.LogException(ex); EditorUtility.DisplayDialog("BootScene UI 복구 실패", ex.Message, "확인"); }
    }

    private static int RepairWearable(Transform wearable)
    {
        if (wearable == null) return 0;
        int count=0;
        foreach (var name in new[] { "LiveButton", "HistoryButton" })
        {
            foreach (var image in wearable.GetComponentsInChildren<Image>(true))
            {
                if (image.name != name) continue;
                string path = "Assets/HealthMon/UIStyleKitV3/Sprites/Buttons/" +
                    (name == "LiveButton" ? "BTN_Blue" : "BTN_Gold") + ".png";
                var sprite=LoadSprite(path);
                if (sprite==null)continue;
                Undo.RecordObject(image,"Restore wearable tab");
                image.sprite=sprite;image.type=Image.Type.Sliced;image.color=Color.white;
                count++;
            }
        }
        return count;
    }

    private static int RepairNav(Transform nav)
    {
        if (nav == null) { Debug.LogWarning("[HM UI Recovery] BottomNavV2 없음. 하단 메뉴는 건너뜁니다."); return 0; }
        string[] rows = { "TopRow/HomeButton", "TopRow/FoodButton", "TopRow/DialogueButton",
            "BottomRow/QuestButton", "BottomRow/CollectionButton", "BottomRow/WearableButton" };
        string[] iconPath = { "Icon_Home_Light", "Icon_Camera_Light", "Icon_Chat_Light",
            "Icon_Quest_Light", "Icon_Book_Light", "Icon_Wearable_Light" };
        int count = 0;
        for (int i = 0; i < rows.Length; i++)
        {
            Transform button = nav.Find(rows[i]);
            Transform iconRoot = button != null ? button.Find("NavIconV2") : null;
            if (iconRoot == null) continue;
            var icon = iconRoot.GetComponent<Image>();
            var sprite = LoadSprite("Assets/HealthMon/UIStyleKit/Sprites/Icons/" + iconPath[i] + ".png");
            if (icon != null && sprite != null)
            {
                Undo.RecordObject(icon, "Restore HealthMon nav icon");
                icon.sprite = sprite; icon.enabled = true; icon.type = Image.Type.Simple;
                icon.color = Color.white; icon.preserveAspect = true; icon.raycastTarget = false;
            }
            // A legacy RawImage child points at textures absent from the uploaded Assets.
            // It renders a solid white rectangle above the valid Image component.
            // Disable only that redundant RawImage; DO NOT remove any button or listener.
            foreach (var raw in iconRoot.GetComponentsInChildren<RawImage>(true))
            {
                if (!raw.enabled) continue;
                Undo.RecordObject(raw, "Hide broken redundant HealthMon nav RawImage");
                raw.enabled = false;
            }
            count++;
        }
        return count;
    }

    private static int RepairAdmin(Transform admin)
    {
        if (admin == null) { Debug.LogWarning("[HM UI Recovery] AdminPanel 없음."); return 0; }
        int count = 0;
        var panel = admin.GetComponent<Image>();
        var backdrop = LoadSprite(Sprites + "Admin_ScrollView_Backdrop.png");
        if (panel != null)
        {
            Undo.RecordObject(panel, "Restore AdminPanel dark background");
            panel.sprite = null; panel.type = Image.Type.Simple;
            panel.color = Hex("#101D37"); panel.enabled = true;
            count++;
        }
        var scroll = admin.Find("AdminScrollView");
        var scrollImage = scroll != null ? scroll.GetComponent<Image>() : null;
        if (scrollImage != null && backdrop != null)
        {
            Undo.RecordObject(scrollImage, "Restore AdminScrollView background");
            scrollImage.sprite = backdrop; scrollImage.type = Image.Type.Sliced;
            scrollImage.color = Color.white; scrollImage.enabled = true;
            count++;
        }
        var close = admin.Find("CloseButton");
        var closeImage = close != null ? close.GetComponent<Image>() : null;
        var closeSprite = LoadSprite(Sprites + "Admin_Close_Button.png");
        if (closeImage != null && closeSprite != null)
        {
            Undo.RecordObject(closeImage, "Restore Admin close button");
            closeImage.sprite = closeSprite; closeImage.type = Image.Type.Sliced;
            closeImage.color = Color.white; closeImage.enabled = true;
            count++;
        }
        foreach (var text in admin.GetComponentsInChildren<TextMeshProUGUI>(true))
        {
            if (text == null || text.text == null) continue;
            // Keep input text dark on its white background. All other label text is readable on navy.
            if (text.GetComponentInParent<TMP_InputField>() != null) continue;
            if (text.name == "Text (TMP)" && text.transform.parent != null && text.transform.parent.GetComponent<Button>() != null)
                continue; // Existing button label palette is maintained.
            Undo.RecordObject(text, "Restore admin text contrast");
            text.color = PaleBlue;
        }
        return count;
    }

    private static int RepairQuests(Transform questPanel)
    {
        if (questPanel == null) { Debug.LogWarning("[HM UI Recovery] QuestPanel 없음."); return 0; }
        var questSprite = LoadSprite(Sprites + "QuestCard_Refined.png");
        if (questSprite == null) return 0;
        Transform list = questPanel.Find("QuestList");
        if (list == null) { Debug.LogWarning("[HM UI Recovery] QuestList 없음."); return 0; }
        string[] names = { "WalkQuest", "FoodQuest", "DialogueQuest", "ARquest" };
        int count = 0;
        foreach (var name in names)
        {
            Transform card = list.Find(name);
            if (card == null) continue;
            var image = card.GetComponent<Image>();
            if (image == null) continue;
            Undo.RecordObject(image, "Restyle HealthMon quest card");
            image.sprite = questSprite; image.type = Image.Type.Sliced; image.color = Color.white;
            image.enabled = true; count++;
            foreach (var text in card.GetComponentsInChildren<TextMeshProUGUI>(true))
            {
                if (text == null) continue;
                if (text.name == "Text (TMP)" && text.GetComponentInParent<Button>() != null)
                    continue; // Button state can keep its own text styling.
                Undo.RecordObject(text, "Make quest labels readable on blue");
                text.color = text.name == "RewardText" ? Gold : text.name == "ProgessText" || text.name == "ProgressText" ? PaleBlue : Color.white;
            }
        }
        return count;
    }
}
#endif
