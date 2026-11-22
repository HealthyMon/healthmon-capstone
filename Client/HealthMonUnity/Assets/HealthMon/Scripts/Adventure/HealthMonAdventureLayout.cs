using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>Reserve separate portrait regions for navigation, HUD, arena and actions.</summary>
public sealed class HealthMonAdventureLayout : MonoBehaviour
{
    private static readonly Color PanelColor = new Color(.16f, .085f, .055f, .94f);
    private Sprite fittedFrame;
    private GameObject explorationBackdrop;
    private Transform actionPanel, movePanel;
    private BattleController controller;
    private Transform hud;
    private AdventureManager adventure;
    private void Start()
    {
        controller = FindAnyObjectByType<BattleController>();
        adventure = GetComponent<AdventureManager>();
        var frame = GameObject.Find("AdventureFrameCanvas").transform;
        var frameImage = frame.Find("CanvasFrame")?.GetComponent<Image>();
        if (frameImage != null && frameImage.sprite != null)
        {
            var source = frameImage.sprite;
            // Keep the painted corners and lower stone panel intact on taller phones.
            fittedFrame = Sprite.Create(source.texture, source.rect, new Vector2(.5f, .5f),
                source.pixelsPerUnit, 0, SpriteMeshType.FullRect, new Vector4(145, 340, 145, 280));
            frameImage.sprite = fittedFrame;
            frameImage.type = Image.Type.Sliced;
            frameImage.pixelsPerUnitMultiplier = .87f;
            frameImage.raycastTarget = false;
        }
        hud = frame.Find("AdventureHUD");
        Place(hud.Find("FloorText"), .74f, .945f, .94f, .985f);
        Label(hud.Find("FloorText"), 38, TextAlignmentOptions.Right);
        Place(hud.Find("PlayerStatusPanel"), .06f, .865f, .94f, .935f);
        var stats = hud.Find("PlayerStatusPanel"); ColorPanel(stats);
        Place(stats.Find("PlayerNameTetxt"), .04f, .54f, .55f, .94f); Label(stats.Find("PlayerNameTetxt"), 30, TextAlignmentOptions.Left);
        Place(stats.Find("PlayerHPText"), .60f, .54f, .96f, .94f); Label(stats.Find("PlayerHPText"), 28, TextAlignmentOptions.Right);
        Place(stats.Find("PlayerHPBar"), .04f, .42f, .96f, .52f);
        Place(stats.Find("PlayerSTText"), .04f, .11f, .46f, .35f); Label(stats.Find("PlayerSTText"), 24, TextAlignmentOptions.Left);
        Place(stats.Find("PlayerSTBar"), .50f, .17f, .96f, .25f);
        Place(hud.Find("EventDescription"), .10f, .48f, .90f, .57f);
        Label(hud.Find("EventDescription"), 30);
        Place(hud.Find("EventLogText"), .12f, .31f, .88f, .44f);
        Label(hud.Find("EventLogText"), 28);
        Place(frame.Find("ContentViewport"), .08f, .43f, .92f, .85f);
        var nav = GameObject.Find("AdventureNavigation").transform;
        Button(nav.Find("HomeButton")?.GetComponent<Button>(), .04f, .946f, .23f, .986f, "홈");
        var entrance = GameObject.Find("AdventureCanvas").transform.Find("EntrancePanel");
        entrance.GetComponent<Image>().color = new Color(.04f, .08f, .06f, 1f);
        Place(entrance.Find("EntreanceBackground"), 0, 0, 1, 1);
        var entranceImage = entrance.Find("EntreanceBackground")?.GetComponent<Image>();
        if (entranceImage != null)
        {
            entranceImage.preserveAspect = false;
            entranceImage.raycastTarget = false;
            var fit = entranceImage.gameObject.AddComponent<AspectRatioFitter>();
            fit.aspectMode = AspectRatioFitter.AspectMode.EnvelopeParent;
            fit.aspectRatio = entranceImage.sprite.rect.width / entranceImage.sprite.rect.height;
        }
        if (entrance.GetComponent<RectMask2D>() == null) entrance.gameObject.AddComponent<RectMask2D>();
        Place(entrance.Find("discription"), .07f, .755f, .93f, .905f);
        entrance.Find("discription").GetComponent<Image>().color = new Color(.035f, .07f, .045f, .78f);
        Place(entrance.Find("discription/EntranceTitle"), .06f, .62f, .94f, .94f);
        Place(entrance.Find("discription/EntranceDescription"), .06f, .16f, .94f, .51f);
        Label(entrance.Find("discription/EntranceTitle"), 46);
        Label(entrance.Find("discription/EntranceDescription"), 28);
        var description = entrance.Find("discription/EntranceDescription").GetComponent<TMP_Text>();
        if (description != null) description.text = "미지의 던전, 새로운 도전!";
        var enter = entrance.Find("EnterButton")?.GetComponent<Button>();
        Button(enter, .18f, .075f, .82f, .145f, "탐험 시작");
        var floor = entrance.parent.Find("FloorPanel");
        // The transition already owns the team's cave artwork. Reuse its still
        // frame for exploration instead of exposing the default Unity skybox.
        var descent = GameObject.Find("DescendContent")?.GetComponent<Image>();
        if (descent == null)
            foreach (var candidate in FindObjectsByType<Image>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                if (candidate.name == "DescendContent") { descent = candidate; break; }
        if (descent != null && descent.sprite != null)
        {
            explorationBackdrop = new GameObject("ExplorationBackdrop", typeof(RectTransform), typeof(Image), typeof(AspectRatioFitter));
            explorationBackdrop.transform.SetParent(frame, false);
            explorationBackdrop.transform.SetAsFirstSibling();
            var image = explorationBackdrop.GetComponent<Image>();
            image.sprite = descent.sprite; image.color = new Color(.48f, .38f, .32f, 1); image.raycastTarget = false;
            var fit = explorationBackdrop.GetComponent<AspectRatioFitter>();
            fit.aspectRatio = image.sprite.rect.width / image.sprite.rect.height;
            fit.aspectMode = AspectRatioFitter.AspectMode.EnvelopeParent;
        }
        Place(floor.Find("EvnetText"), .10f, .48f, .90f, .57f);
        Label(floor.Find("EvnetText"), 30);
        Button(floor.Find("DescendButton")?.GetComponent<Button>(), .24f, .13f, .76f, .21f, "다음 층으로");
        BottomBand(floor.Find("DescendButton"), 100, 240);

        var ui = FindAnyObjectByType<BattleUI>(FindObjectsInactive.Include);
        var panel = ui.battlePanel.transform;
        // This extra bitmap was layered over the enemy and the frame canvas.
        var duplicate = panel.Find("Image")?.GetComponent<Image>();
        if (duplicate != null) duplicate.enabled = false;
        var player = panel.Find("PlayerStatusPanel");
        Place(player, .06f, .87f, .94f, .94f); ColorPanel(player);
        Place(player.Find("PlayerNameTetxt"), .04f, .58f, .55f, .94f); Label(player.Find("PlayerNameTetxt"), 30, TextAlignmentOptions.Left);
        Set(ui.playerHPText, .58f, .58f, .96f, .94f, 30, TextAlignmentOptions.Right);
        Place(ui.playerHPBar.transform, .04f, .47f, .96f, .57f);
        Set(ui.playerSTText, .04f, .14f, .46f, .41f, 24, TextAlignmentOptions.Left);
        Set(ui.playerATBText, .53f, .14f, .96f, .41f, 24, TextAlignmentOptions.Right);
        Place(ui.playerSTBar.transform, .04f, .05f, .46f, .13f);
        Place(ui.playerGaugeBar.transform, .53f, .05f, .96f, .13f);
        var enemy = panel.Find("EnemyStatusPanel");
        Place(enemy, .09f, .77f, .91f, .86f); ColorPanel(enemy);
        Set(ui.enemyNameText, .04f, .62f, .58f, .92f, 32, TextAlignmentOptions.Left);
        Set(ui.enemyHPText, .60f, .62f, .96f, .92f, 28, TextAlignmentOptions.Right);
        Place(ui.enemyHPBar.transform, .04f, .47f, .96f, .57f);
        Set(ui.enemyNextActionText, .04f, .13f, .68f, .39f, 25, TextAlignmentOptions.Left);
        Place(ui.enemyGaugeBar.transform, .72f, .20f, .96f, .28f);
        var log = panel.Find("BattleLogPanel");
        Place(log, .10f, .235f, .90f, .285f); ColorPanel(log);
        Set(ui.battleLogText, .05f, .12f, .95f, .88f, 30);
        var actions = panel.Find("ActionPanel");
        actionPanel = actions;
        var layout = actions.GetComponent<LayoutGroup>();
        if (layout != null) layout.enabled = false;
        Place(actions, .09f, .045f, .91f, .205f);
        BottomBand(actions, 56, 300);
        var actionImage = actions.GetComponent<Image>(); if (actionImage != null) actionImage.enabled = false;
        Button(ui.attackButton, .02f, .54f, .48f, .96f, "공격 · " + ui.battleManager.attackCost);
        Button(ui.skillButton, .52f, .54f, .98f, .96f, "스킬 · " + ui.battleManager.skillCost);
        Button(ui.itemButton, .02f, .04f, .48f, .46f, "회복");
        Button(ui.moveButton, .02f, .04f, .48f, .46f, "이동");
        Button(ui.waitButton, .52f, .04f, .98f, .46f, "대기");
        Place(panel.Find("MovePanel"), .09f, .045f, .91f, .205f);
        BottomBand(panel.Find("MovePanel"), 56, 300);
        movePanel = panel.Find("MovePanel");
        ColorPanel(movePanel);
        var moveText = movePanel.Find("MoveInfoText")?.GetComponent<TMP_Text>();
        if (moveText != null) moveText.font = ui.battleLogText.font;
        Set(moveText, .04f, .48f, .96f, .96f, 28);
        Button(movePanel.Find("ConfirmButton")?.GetComponent<Button>(), .04f, .07f, .48f, .41f, "이동 확정");
        Button(movePanel.Find("CancelButton (1)")?.GetComponent<Button>(), .52f, .07f, .96f, .41f, "취소");
    }
    private void OnDestroy() { if (fittedFrame != null) Destroy(fittedFrame); }
    private static void BottomBand(Transform target, float bottom, float top)
    {
        var rect = target as RectTransform;
        if (rect == null) return;
        rect.anchorMin = new Vector2(rect.anchorMin.x, 0);
        rect.anchorMax = new Vector2(rect.anchorMax.x, 0);
        rect.offsetMin = new Vector2(0, bottom);
        rect.offsetMax = new Vector2(0, top);
    }
    private void LateUpdate()
    {
        if (hud == null || controller == null) return;
        if (explorationBackdrop != null) explorationBackdrop.SetActive(!controller.IsBattling);
        if (actionPanel != null && movePanel != null)
            actionPanel.gameObject.SetActive(!movePanel.gameObject.activeSelf);
        // The exploration stats and battle stats previously rendered on top of each other.
        foreach (string name in new[] { "PlayerStatusPanel", "EventDescription", "EventLogText" })
        {
            var child = hud.Find(name);
            bool visible = !controller.IsBattling && (name != "PlayerStatusPanel" || adventure.State != ExplorationState.Entrance);
            if (child != null && child.gameObject.activeSelf != visible) child.gameObject.SetActive(visible);
        }
    }
    private static void Place(Transform t, float x, float y, float r, float top) => HealthMonUILayout.Place(t as RectTransform, x, y, r, top);
    private static void ColorPanel(Transform t)
    {
        var image = t.GetComponent<Image>(); if (image != null) image.color = PanelColor;
    }
    private static void Set(TMP_Text text, float x, float y, float r, float top, float size, TextAlignmentOptions alignment = TextAlignmentOptions.Center)
    {
        HealthMonUILayout.Text(text, x, y, r, top, size);
        if (text != null) { text.color = Color.white; text.alignment = alignment; }
    }
    private static void Label(Transform t, float size, TextAlignmentOptions alignment = TextAlignmentOptions.Center)
    {
        var text = t?.GetComponent<TMP_Text>();
        var legacy = t?.GetComponent<Text>();
        if (legacy != null)
        {
            legacy.color = Color.white; legacy.resizeTextForBestFit = true;
            legacy.resizeTextMinSize = 20; legacy.resizeTextMaxSize = (int)size;
            legacy.alignment = alignment == TextAlignmentOptions.Left ? TextAnchor.MiddleLeft : alignment == TextAlignmentOptions.Right ? TextAnchor.MiddleRight : TextAnchor.MiddleCenter;
        }
        if (text == null) return;
        text.enableAutoSizing = true; text.fontSizeMin = 20; text.fontSizeMax = size;
        text.alignment = alignment; text.color = Color.white;
    }
    private static void Button(Button button, float x, float y, float r, float top, string caption)
    {
        if (button == null) return;
        Place(button.transform, x, y, r, top);
        var image = button.GetComponent<Image>();
        if (image != null) image.color = new Color(.46f, .23f, .085f, 1f);
        var colors = button.colors;
        colors.normalColor = Color.white;
        colors.highlightedColor = new Color(1f, .91f, .72f);
        colors.pressedColor = new Color(.72f, .61f, .43f);
        colors.disabledColor = new Color(.48f, .42f, .36f, .8f);
        button.colors = colors;
        var tmp = button.GetComponentInChildren<TMP_Text>(true);
        if (tmp != null) { Set(tmp, .06f, .12f, .94f, .88f, 36); tmp.text = caption; }
        var legacy = button.GetComponentInChildren<Text>(true);
        if (legacy != null)
        {
            Place(legacy.transform, .06f, .12f, .94f, .88f); legacy.text = caption;
            legacy.color = Color.white; legacy.resizeTextForBestFit = true;
            legacy.resizeTextMinSize = 20; legacy.resizeTextMaxSize = 36;
        }
    }
}
