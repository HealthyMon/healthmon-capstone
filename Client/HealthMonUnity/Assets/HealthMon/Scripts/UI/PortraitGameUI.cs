using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Visuals and geometry only. Existing controls keep their listeners, fields and server authority.
[DefaultExecutionOrder(10000)]
[DisallowMultipleComponent]
public sealed class PortraitGameUI : MonoBehaviour
{
    public static PortraitGameUI Active { get; private set; }
    public static readonly Color Ink = new Color32(32, 63, 82, 255);
    public static readonly Color Cream = new Color32(255, 244, 215, 255);
    private readonly Dictionary<string, Sprite> sprites = new Dictionary<string, Sprite>();
    private Canvas canvas;
    private RectTransform root;
    private Rect safe;
    private bool dirty = true, applying;
    private int lastWidth, lastHeight, lastVisible;
    private Rect lastSafe;
    private GameObject backdrop;
    private Material backdropMaterial;
    private Camera sceneCamera;
    private readonly Dictionary<Button, Transform> fixedActions = new Dictionary<Button, Transform>();
    [Serializable] private sealed class FixedActionBinding { public Button action; public Transform page; }
    [SerializeField, HideInInspector] private List<FixedActionBinding> actionBindings = new List<FixedActionBinding>();
    private readonly string[] panels = { "HomePanel", "StatusPanel", "FoodScanPanel", "DialoguePanel", "QuestPanel", "RewardPanel", "CollectionPanel", "CustomizationPanel", "WearablePanel", "AdminPanel", "PetARPanel" };
    private readonly string[] navNames = { "HomeButton", "FoodButton", "PetARButton", "DialogueButton", "QuestButton", "CollectionButton", "WearableButton" };
    private readonly string[] navIcons = { "home", "camera", "ar", "chat", "quest", "book", "watch" };

    public static void Refresh() { if (Active != null) Active.dirty = true; }
    public bool SettingsLauncherVisible => !VisiblePanel("AdminPanel") && !VisiblePanel("WearablePanel") && !(GetComponent<PortraitCharacterMenu>()?.IsOpen ?? false);
    private void OnEnable()
    {
        Active = this; dirty = true; fixedActions.Clear();
        actionBindings.RemoveAll(binding => binding.action == null || binding.page == null);
        foreach (var binding in actionBindings) fixedActions[binding.action] = binding.page;
    }
    private void Start()
    {
        ApplyNow();
        var owner = FindAnyObjectByType<UIManager>();
        if (owner != null) (GetComponent<PortraitCharacterMenu>() ?? gameObject.AddComponent<PortraitCharacterMenu>()).Configure(this, owner);
        ApplyNow();
    }
    private void OnRectTransformDimensionsChange() { dirty = true; }
    private void OnTransformChildrenChanged() { dirty = true; }
    private void LateUpdate()
    {
        int visible = VisibleSignature();
        if (dirty || visible != lastVisible || Screen.width != lastWidth || Screen.height != lastHeight || Screen.safeArea != lastSafe)
        { lastVisible = visible; ApplyNow(); }
        UpdateBackdrop();
    }
    private int VisibleSignature()
    {
        int value = 0;
        for (int i = 0; i < panels.Length; i++)
        { var p = transform.Find(panels[i]); if (p != null && p.gameObject.activeSelf) value |= 1 << i; }
        var entry = GetComponent<PortraitCharacterMenu>(); if (entry != null && entry.IsOpen) value |= 1 << 14;
        return value;
    }
    public Sprite Sprite(string name)
    {
        if (!sprites.TryGetValue(name, out var sprite))
        { sprite = Resources.Load<Sprite>("HealthMon/PortraitUI/" + name); sprites[name] = sprite; }
        return sprite;
    }
    public void ApplyNow()
    {
        if (applying) return;
        applying = true;
        try
        {
            Active = this; canvas = GetComponent<Canvas>(); root = transform as RectTransform;
            if (canvas == null || root == null) return;
            var scaler = GetComponent<CanvasScaler>();
            if (scaler != null)
            { scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize; scaler.referenceResolution = new Vector2(1080, 2400); scaler.matchWidthOrHeight = 0; }
            Canvas.ForceUpdateCanvases();
            float width = root.rect.width, height = root.rect.height;
            if (width < 1 || height < 1) return;
            var device = Screen.safeArea;
            float sw = Mathf.Max(1, Screen.width), sh = Mathf.Max(1, Screen.height);
            float left = Mathf.Max(35, device.xMin / sw * width);
            float bottom = Mathf.Max(45, device.yMin / sh * height);
            float right = Mathf.Max(35, (sw - device.xMax) / sw * width);
            float top = Mathf.Max(70, (sh - device.yMax) / sh * height);
            safe = new Rect(left, bottom, width - left - right, height - top - bottom);
            foreach (string name in panels)
            {
                var panel = transform.Find(name) as RectTransform;
                if (panel == null) continue;
                Stretch(panel);
                var image = panel.GetComponent<Image>();
                if (image != null) { image.sprite = null; image.color = Color.clear; image.raycastTarget = false; }
            }
            foreach (var text in GetComponentsInChildren<TMP_Text>(true))
            {
                text.color = Ink; text.raycastTarget = false;
                text.fontSizeMin = Mathf.Max(26, text.fontSizeMin);
                text.fontSizeMax = Mathf.Max(34, text.fontSizeMax);
                text.fontSize = Mathf.Max(32, text.fontSize);
            }
            foreach (var button in GetComponentsInChildren<Button>(true)) StyleButton(button, false);
            foreach (var field in GetComponentsInChildren<TMP_InputField>(true))
            { Surface(field.GetComponent<Image>(), "input-default"); if (field.textComponent != null) field.textComponent.color = Ink; if (field.placeholder != null) field.placeholder.color = new Color(.40f, .49f, .48f); }
            foreach (var slider in GetComponentsInChildren<Slider>(true))
            {
                var track = slider.transform.Find("Track"); if (track != null) Surface(track.GetComponent<Image>(), "progress-track");
                if (slider.fillRect != null) Surface(slider.fillRect.GetComponent<Image>(), "progress-fill");
                if (slider.handleRect != null) slider.handleRect.GetComponent<Image>().color = new Color(.27f, .62f, .58f);
            }
            LayoutNavigation(); LayoutHome(); LayoutHeaders(); LayoutFood(); LayoutDialogue();
            LayoutStatus(); LayoutQuests(); LayoutCollection(); LayoutReward(); LayoutWearable(); LayoutAdmin(); LayoutAR();
            GetComponent<PortraitCharacterMenu>()?.Arrange(safe);
            lastWidth = Screen.width; lastHeight = Screen.height; lastSafe = Screen.safeArea;
            dirty = false;
        }
        finally { applying = false; }
    }
    private Rect ContentRect => new Rect(safe.x + 10, safe.y + 400, safe.width - 20, safe.height - 610);
    private Rect Top(float x, float y, float width, float height) => new Rect(safe.x + x, safe.yMax - y - height, width, height);
    public void Place(RectTransform target, Rect bounds)
    {
        if (target == null || target.parent == null) return;
        var parent = target.parent as RectTransform; if (parent == null) return;
        Vector2 min = parent.InverseTransformPoint(root.TransformPoint(root.rect.min + bounds.min));
        Vector2 max = parent.InverseTransformPoint(root.TransformPoint(root.rect.min + bounds.max));
        target.anchorMin = target.anchorMax = target.pivot = Vector2.zero;
        target.localScale = Vector3.one; target.localRotation = Quaternion.identity;
        target.anchoredPosition = min - parent.rect.min; target.sizeDelta = max - min;
    }
    private static void Stretch(RectTransform target)
    { target.anchorMin = Vector2.zero; target.anchorMax = Vector2.one; target.offsetMin = target.offsetMax = Vector2.zero; target.localScale = Vector3.one; }
    private static RectTransform Child(Transform parent, string path) => parent == null ? null : parent.Find(path) as RectTransform;
    private static void Off(Transform parent, string path)
    { var t = parent == null ? null : parent.Find(path); if (t != null) t.gameObject.SetActive(false); }
    private void Surface(Image image, string name)
    {
        if (image == null) return; var sprite = Sprite("Components/" + name);
        if (sprite == null) return;
        image.enabled = true; image.sprite = sprite; image.overrideSprite = null; image.type = Image.Type.Sliced; image.color = Color.white; image.preserveAspect = false;
    }
    public void StyleButton(Button button, bool primary)
    {
        if (button == null) return;
        string kind = primary ? "button-primary" : "button-secondary";
        var image = button.targetGraphic as Image ?? button.GetComponent<Image>();
        Surface(image, kind);
        button.targetGraphic = image; button.transition = Selectable.Transition.SpriteSwap;
        var state = button.spriteState;
        state.highlightedSprite = Sprite("Components/" + kind);
        state.pressedSprite = Sprite("Components/" + kind + "-pressed");
        state.selectedSprite = Sprite("Components/" + kind); state.disabledSprite = Sprite("Components/" + kind + "-disabled");
        button.spriteState = state;
        var label = button.GetComponentInChildren<TMP_Text>(true);
        if (label != null) { label.color = primary ? Ink : Cream; label.fontSizeMin = 28; label.fontSizeMax = 38; label.enableAutoSizing = true; label.fontStyle = FontStyles.Bold; }
    }
    private void Label(Transform parent, string path, Rect bounds, float size, Color color)
    {
        var rect = Child(parent, path); if (rect == null) return;
        Place(rect, bounds); var text = rect.GetComponent<TMP_Text>();
        if (text != null) { text.color = color; text.fontSize = text.fontSizeMax = size; text.fontSizeMin = 26; text.enableAutoSizing = true; }
    }
    private void Icon(Button button, string name, bool navigation = false)
    {
        var icon = button.transform.Find("PortraitIcon") as RectTransform;
        if (icon == null)
        { icon = new GameObject("PortraitIcon", typeof(RectTransform), typeof(Image)).GetComponent<RectTransform>(); icon.SetParent(button.transform, false); }
        var image = icon.GetComponent<Image>(); image.sprite = Sprite("Icons/" + name + "-default"); image.color = Color.white; image.raycastTarget = false; image.preserveAspect = true;
        icon.anchorMin = icon.anchorMax = new Vector2(.5f, navigation ? .67f : .5f); icon.pivot = new Vector2(.5f, .5f);
        icon.sizeDelta = navigation ? new Vector2(73, 73) : new Vector2(44, 44); icon.anchoredPosition = Vector2.zero;
        if (!navigation) { icon.anchorMin = icon.anchorMax = new Vector2(.12f, .5f); }
        var label = button.GetComponentInChildren<TMP_Text>(true);
        if (label != null && navigation)
        { label.rectTransform.anchorMin = new Vector2(0, .03f); label.rectTransform.anchorMax = new Vector2(1, .42f); label.rectTransform.offsetMin = new Vector2(5, 0); label.rectTransform.offsetMax = new Vector2(-5, 0); label.alignment = TextAlignmentOptions.Center; label.fontSizeMax = 34; }
    }
    private void LayoutNavigation()
    {
        var nav = Child(transform, "BottomNav"); if (nav == null) return;
        var entry = GetComponent<PortraitCharacterMenu>(); nav.gameObject.SetActive(entry == null || !entry.IsOpen);
        foreach (var group in nav.GetComponents<LayoutGroup>()) group.enabled = false;
        Rect area = new Rect(safe.x, safe.y, safe.width, 340); Place(nav, area); Surface(nav.GetComponent<Image>(), "navigation-panel-portrait");
        int selected = VisiblePanel("FoodScanPanel") ? 1 : VisiblePanel("PetARPanel") ? 2 : VisiblePanel("DialoguePanel") ? 3 : VisiblePanel("QuestPanel") || VisiblePanel("RewardPanel") ? 4 : VisiblePanel("CollectionPanel") || VisiblePanel("CustomizationPanel") ? 5 : VisiblePanel("WearablePanel") ? 6 : 0;
        for (int i = 0; i < navNames.Length; i++)
        {
            var rect = Child(nav, navNames[i]); if (rect == null) continue;
            int cols = i < 4 ? 4 : 3, column = i < 4 ? i : i - 4;
            float width = (area.width - 36 - (cols - 1) * 12) / cols;
            Place(rect, new Rect(area.x + 18 + column * (width + 12), area.y + (i < 4 ? 178 : 18), width, 144));
            var button = rect.GetComponent<Button>(); StyleButton(button, i == selected);
            Surface(rect.GetComponent<Image>(), i == selected ? "navigation-item-selected" : "navigation-item-default");
            var state = button.spriteState; state.highlightedSprite = state.selectedSprite = rect.GetComponent<Image>().sprite; state.pressedSprite = Sprite("Components/navigation-item-pressed"); state.disabledSprite = rect.GetComponent<Image>().sprite; button.spriteState = state;
            Icon(button, navIcons[i], true);
            if (navNames[i] == "FoodButton") button.GetComponentInChildren<TMP_Text>().text = "촬영";
        }
    }
    private bool VisiblePanel(string name) { var panel = transform.Find(name); return panel != null && panel.gameObject.activeSelf; }
    private void LayoutHome()
    {
        var home = transform.Find("HomePanel"); if (home == null) return;
        var hud = Child(home, "TopInfoPanel"); Place(hud, Top(0, 0, safe.width * .63f, 188)); Surface(hud.GetComponent<Image>(), "header-panel");
        if (hud.GetComponent<Button>() != null) hud.GetComponent<Button>().transition = Selectable.Transition.None;
        Label(hud, "LevelText", Top(20, 24, 130, 115), 36, Cream);
        Label(hud, "NameText", Top(165, 20, safe.width * .63f - 190, 70), 44, Cream);
        Label(hud, "ExpText", Top(165, 100, safe.width * .63f - 190, 60), 30, Cream);
        Label(hud, "CoinText", Top(safe.width - 285, 205, 285, 120), 33, Cream);
        var coin = Child(hud, "CoinText");
        if (coin != null)
        {
            var background = Child(home, "PortraitCoinCard");
            if (background == null) { background = new GameObject("PortraitCoinCard", typeof(RectTransform), typeof(Image)).GetComponent<RectTransform>(); background.SetParent(home, false); background.SetAsFirstSibling(); }
            Place(background, Top(safe.width - 285, 205, 285, 120)); Surface(background.GetComponent<Image>(), "card-dark"); background.GetComponent<Image>().raycastTarget = false;
            coin.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Center;
        }
        var stats = Child(home, "LeftStatusPanel"); Place(stats, Top(0, 223, safe.width * .64f, 127)); Surface(stats.GetComponent<Image>(), "status-strip-portrait");
        float column = safe.width * .64f / 3;
        foreach (var item in new[] { ("IntimacyText", 0), ("ActivityText", 1), ("MoodText", 2) })
            Label(stats, item.Item1, Top(column * item.Item2 + 10, 240, column - 20, 90), 32, Ink);
        var status = Child(home, "StatusButton"); Place(status, new Rect(safe.x, safe.y + 590, 310, 144)); StyleButton(status.GetComponent<Button>(), true);
        var evolve = Child(home, "HomeEvolutionButton"); Place(evolve, new Rect(safe.xMax - 350, safe.y + 590, 350, 144)); if (evolve != null) StyleButton(evolve.GetComponent<Button>(), false);
        var speech = Child(home, "SpeechBubble"); Place(speech, new Rect(safe.x + 35, safe.y + 405, safe.width - 70, 145)); Surface(speech.GetComponent<Image>(), "speech-bubble");
        var speechText = Child(speech, "SpeechText"); if (speechText != null) { Stretch(speechText); speechText.offsetMin = new Vector2(30, 20); speechText.offsetMax = new Vector2(-30, -25); speechText.GetComponent<TMP_Text>().fontSizeMax = 38; }
        Off(home, "AdminOpenButton");
    }
    private void LayoutHeaders()
    {
        foreach (string name in panels)
        {
            var panel = transform.Find(name); var header = Child(panel, "Header"); if (header == null) continue;
            Place(header, Top(0, 0, safe.width, 160)); Surface(header.GetComponent<Image>(), "header-panel");
            foreach (var title in header.GetComponentsInChildren<TMP_Text>(true)) title.color = Cream;
            var back = Child(header, "BackButton"); if (back != null) { Place(back, Top(12, 12, 136, 136)); StyleButton(back.GetComponent<Button>(), false); }
            var titleRect = Child(header, "TitleText"); if (titleRect != null) Place(titleRect, Top(160, 20, safe.width - 440, 120));
        }
        var settings = Child(transform, "UnifiedSettingsButton");
        if (settings != null) { settings.gameObject.SetActive(SettingsLauncherVisible); Place(settings, Top(safe.width - 310, 0, 310, 144)); StyleButton(settings.GetComponent<Button>(), false); settings.SetAsLastSibling(); }
    }
    private void LayoutFood()
    {
        var food = transform.Find("FoodScanPanel"); if (food == null) return;
        Rect area = ContentRect;
        foreach (string name in new[] { "CaptureView", "CandidateView", "ResultView" })
        { var view = Child(food, name); Place(view, area); if (view != null) Surface(view.GetComponent<Image>(), "card-default"); }
        var capture = food.Find("CaptureView");
        float photoHeight = Mathf.Max(300, area.height - 600);
        Place(Child(capture, "CameraFrame"), new Rect(area.x + 30, area.yMax - photoHeight - 30, area.width - 60, photoHeight));
        Place(Child(capture, "CapturePreview"), new Rect(area.x + 30, area.yMax - photoHeight - 30, area.width - 60, photoHeight));
        Label(capture, "GuideText", new Rect(area.x + 35, area.y + 435, area.width - 70, 105), 34, Ink);
        Label(capture, "ScanStatusText", new Rect(area.x + 35, area.y + 335, area.width - 70, 90), 30, Ink);
        var analyze = Child(capture, "AnalyzeButton"); Place(analyze, new Rect(area.x + 35, area.y + 185, area.width - 70, 144)); if (analyze != null) StyleButton(analyze.GetComponent<Button>(), true);
        Place(Child(capture, "CaptureButton"), new Rect(area.x + 35, area.y + 30, area.width - 70, 144));
        Place(Child(capture, "ChooseDesktopFoodPhoto"), new Rect(area.x + 35, area.y + 30, area.width - 70, 144));
        var captureButton = capture.Find("CaptureButton");
        if (captureButton != null) captureButton.gameObject.SetActive(Application.isMobilePlatform || !Application.isEditor);
        var candidate = food.Find("CandidateView");
        Label(candidate, "CandidateTitle", new Rect(area.x + 35, area.yMax - 130, area.width - 70, 90), 38, Ink);
        Label(candidate, "CandidateAnalysisOrigin", new Rect(area.x + 35, area.yMax - 230, area.width - 70, 90), 29, Ink);
        int rank = 0;
        foreach (var button in candidate.GetComponentsInChildren<Button>(true))
        {
            if (button.name == "RetakeButton") { Place((RectTransform)button.transform, new Rect(area.x + 75, area.y + 35, area.width - 150, 144)); continue; }
            Place((RectTransform)button.transform, new Rect(area.x + 35, area.yMax - 470 - rank * 235, area.width - 70, 205)); rank++;
        }
        var result = food.Find("ResultView");
        Label(result, "ResultTitle", new Rect(area.x + 30, area.yMax - 115, area.width - 60, 85), 40, Ink);
        Place(Child(result, "FoodConfirmationScroll"), new Rect(area.x + 28, area.y + 310, area.width - 56, Mathf.Max(200, area.height - 455)));
        var confirm = Child(result, "ConfirmButton"); Place(confirm, new Rect(area.x + 35, area.y + 25, area.width - 70, 150)); if (confirm != null) StyleButton(confirm.GetComponent<Button>(), true);
        Label(result, "FoodSaveFeedback", new Rect(area.x + 30, area.y + 185, area.width - 60, 105), 30, Ink);
        var scroll = result.Find("FoodConfirmationScroll");
        if (scroll != null)
        {
            var content = scroll.Find("Viewport/Content");
            if (content != null) foreach (Transform row in content)
            {
                var layout = row.GetComponent<LayoutElement>(); if (layout == null) continue;
                float height = row.GetComponent<Toggle>() != null ? 145 : row.name == "ConfirmationNotice" ? 190 : row.name == "FoodNameText" ? 130 : 144;
                layout.minHeight = layout.preferredHeight = height;
                if (row.name == "QuantityRow")
                { var group = row.GetComponent<HorizontalLayoutGroup>(); if (group != null) group.spacing = 16; }
                if (row.name == "MealTypeChoices" || row.name == "QuantityRow")
                {
                    var horizontal = row.GetComponent<HorizontalLayoutGroup>();
                    if (horizontal != null) { horizontal.childControlWidth = horizontal.childControlHeight = true; horizontal.childForceExpandWidth = true; }
                    foreach (RectTransform child in row)
                    {
                        child.localScale = Vector3.one;
                        var size = child.GetComponent<LayoutElement>() ?? child.gameObject.AddComponent<LayoutElement>();
                        size.minWidth = 0; size.preferredWidth = 0; size.flexibleWidth = 1;
                    }
                }
            }
            foreach (var toggle in scroll.GetComponentsInChildren<Toggle>(true))
            {
                var box = Child(toggle.transform, "Box"); if (box != null) { box.sizeDelta = new Vector2(72, 72); Surface(box.GetComponent<Image>(), "checkbox-off"); }
                var mark = Child(box, "Checked"); if (mark != null) { Stretch(mark); Surface(mark.GetComponent<Image>(), "checkbox-on"); }
                var label = Child(toggle.transform, "Label"); if (label != null) { label.offsetMin = new Vector2(95, 0); label.GetComponent<TMP_Text>().fontSize = 32; }
            }
            var scanner = FindAnyObjectByType<FoodScanPrototype>(FindObjectsInactive.Include);
            foreach (var button in scroll.GetComponentsInChildren<Button>(true))
                if (button.name.StartsWith("Meal_")) StyleButton(button, scanner != null && button.name == "Meal_" + scanner.SelectedMealType);
        }
    }
    private void LayoutDialogue()
    {
        var panel = transform.Find("DialoguePanel"); if (panel == null) return;
        var area = Child(panel, "CharacterArea"); if (area != null) Stretch(area);
        if (area != null) { var background = area.GetComponent<Image>(); if (background != null) { background.color = Color.clear; background.raycastTarget = false; } }
        var placeholder = Child(area, "CharacterPlaceholder");
        if (placeholder != null)
        { Place(placeholder, new Rect(safe.x + 70, safe.y + 1000, safe.width - 140, Mathf.Max(350, safe.height - 1240))); var image = placeholder.GetComponent<Image>(); if (image != null) image.enabled = false; Off(placeholder, "Text (TMP)"); Off(placeholder, "PetPreviewImage"); }
        Off(panel, "MemoryHintText");
        Surface(Child(area, "CharacterSpeechBubble")?.GetComponent<Image>(), "card-default");
        Surface(Child(panel, "UserMessagePanel")?.GetComponent<Image>(), "card-soft");
        Surface(Child(panel, "InputArea")?.GetComponent<Image>(), "card-default");
        var layout = FindAnyObjectByType<DialogueRuntimeLayout>(FindObjectsInactive.Include);
        if (layout != null && panel.gameObject.activeInHierarchy) layout.ApplyNow();
    }
    private void LayoutStatus()
    {
        var status = transform.Find("StatusPanel"); var card = Child(status, "CommonPetStatus");
        Place(card, ContentRect); if (card != null) Surface(card.GetComponent<Image>(), "card-default");
        var text = Child(card, "ServerStats"); if (text != null) { Stretch(text); text.offsetMin = new Vector2(40, 35); text.offsetMax = new Vector2(-40, -35); text.GetComponent<TMP_Text>().fontSizeMax = 38; }
    }
    private void LayoutQuests()
    {
        var quests = transform.Find("QuestPanel"); var card = Child(quests, "ServerQuestPanel"); if (card == null) return;
        Rect area = ContentRect; Place(card, area); Surface(card.GetComponent<Image>(), "card-default");
        Label(card, "Summary", new Rect(area.x + 30, area.yMax - 165, area.width - 330, 130), 32, Ink);
        Place(Child(card, "RefreshQuests"), new Rect(area.xMax - 280, area.yMax - 165, 250, 136));
        Place(Child(card, "Viewport"), new Rect(area.x + 25, area.y + 190, area.width - 50, area.height - 385));
        Label(card, "Notice", new Rect(area.x + 30, area.y + 25, area.width - 60, 145), 29, Ink);
        var content = card.Find("Viewport/Content"); if (content == null) return;
        foreach (Transform row in content)
        {
            Surface(row.GetComponent<Image>(), "card-soft"); var layout = row.GetComponent<LayoutElement>(); if (layout != null) layout.preferredHeight = 340;
            var details = Child(row, "QuestDetails"); if (details != null) { details.anchorMin = new Vector2(.04f, .45f); details.anchorMax = new Vector2(.96f, .95f); details.offsetMin = details.offsetMax = Vector2.zero; details.GetComponent<TMP_Text>().fontSizeMax = 34; }
            foreach (string name in new[] { "Accept", "Reject" })
            { var rect = Child(row, name); if (rect == null) continue; rect.anchorMin = new Vector2(name == "Accept" ? .48f : .73f, .05f); rect.anchorMax = new Vector2(name == "Accept" ? .71f : .96f, .45f); rect.offsetMin = rect.offsetMax = Vector2.zero; }
        }
    }
    private void LayoutCollection()
    {
        var panel = transform.Find("CollectionPanel"); var grid = Child(panel, "ItemGrid"); if (grid == null) return;
        Rect area = ContentRect; Place(grid, new Rect(area.x, area.y + 380, area.width, area.height - 510));
        foreach (var group in grid.GetComponents<LayoutGroup>()) group.enabled = false;
        int index = 0;
        foreach (Transform item in grid)
        {
            if (item.GetComponent<Button>() == null) continue;
            float w = (area.width - 24) / 2, h = (area.height - 534) / 2;
            Rect card = new Rect(area.x + (index % 2) * (w + 24), area.y + 380 + (1 - index / 2) * (h + 24), w, h);
            Place(item as RectTransform, card);
            Surface(item.GetComponent<Image>(), "card-default");
            foreach (string legacy in new[] { "RawImage", "JewelryItemIcon", "Icon" }) Off(item, legacy);
            var image = Child(item, "PortraitItemIcon");
            if (image == null) { image = new GameObject("PortraitItemIcon", typeof(RectTransform), typeof(Image)).GetComponent<RectTransform>(); image.SetParent(item, false); }
            string glyph = item.name.StartsWith("Necklace") ? "link" : item.name.StartsWith("Earring") ? "star" : item.name.StartsWith("Ring") ? "ring" : "leaf";
            image.GetComponent<Image>().sprite = Sprite("Icons/" + glyph + "-default"); image.GetComponent<Image>().preserveAspect = true; image.GetComponent<Image>().raycastTarget = false;
            float iconHeight = Mathf.Min(210, h * .5f); Place(image, new Rect(card.center.x - iconHeight / 2, card.yMax - iconHeight - 25, iconHeight, iconHeight));
            Label(item, "ItemNameText", new Rect(card.x + 15, card.y + 100, w - 30, 75), 36, Ink);
            Label(item, "LockText", new Rect(card.x + 15, card.y + 25, w - 30, 65), 30, Ink);
            var itemButton = item.GetComponent<Button>(); var state = itemButton.spriteState;
            state.highlightedSprite = state.selectedSprite = state.disabledSprite = Sprite("Components/card-default"); state.pressedSprite = Sprite("Components/card-soft"); itemButton.spriteState = state;
            index++;
        }
        Place(Child(panel, "CollectionSummary"), new Rect(area.x, area.yMax - 115, area.width, 100));
        Surface(Child(panel, "CollectionSummary")?.GetComponent<Image>(), "card-default");
        Label(panel, "CollectionSummary/CollectionTitle", new Rect(area.x + 25, area.yMax - 100, area.width * .6f, 70), 34, Ink);
        Label(panel, "CollectionSummary/CollectionCountText", new Rect(area.xMax - 300, area.yMax - 100, 270, 70), 31, Ink);
        Place(Child(panel, "SelectedItemPanel"), new Rect(area.x, area.y, area.width, 350)); Surface(Child(panel, "SelectedItemPanel")?.GetComponent<Image>(), "card-default");
        Label(panel, "SelectedItemPanel/SelectedItemNameText", new Rect(area.x + 30, area.y + 255, area.width - 60, 70), 38, Ink);
        Label(panel, "SelectedItemPanel/SelectedItemDescriptionText", new Rect(area.x + 30, area.y + 160, area.width - 60, 85), 30, Ink);
        var customize = Child(panel, "SelectedItemPanel/CustomizeButton"); Place(customize, new Rect(area.x + 50, area.y + 15, area.width - 100, 136)); if (customize != null) StyleButton(customize.GetComponent<Button>(), true);
        var selectedPanel = panel.Find("SelectedItemPanel");
        if (selectedPanel != null) foreach (var image in selectedPanel.GetComponentsInChildren<Image>(true))
            if (image.transform != selectedPanel && image.GetComponentInParent<Button>() == null) image.gameObject.SetActive(false);
        Off(panel, "GuideText");
        var custom = transform.Find("CustomizationPanel");
        Place(Child(custom, "CharacterPreview"), new Rect(area.x, area.y + area.height * .45f, area.width, area.height * .55f));
        Place(Child(custom, "ItemInfoPanel"), new Rect(area.x, area.y, area.width, area.height * .4f)); Surface(Child(custom, "ItemInfoPanel")?.GetComponent<Image>(), "card-default");
    }
    private void LayoutReward()
    {
        var popup = Child(transform, "RewardPanel/RewardPopup"); if (popup == null) return;
        Rect area = ContentRect; Place(popup, area); Surface(popup.GetComponent<Image>(), "reward-panel");
        var labels = popup.GetComponentsInChildren<TMP_Text>(true); int i = 0;
        foreach (var text in labels)
        { if (text.GetComponentInParent<Button>() != null) continue; Place(text.rectTransform, new Rect(area.x + 45, area.yMax - 180 - i * 155, area.width - 90, 130)); text.alignment = TextAlignmentOptions.Center; i++; }
        var confirm = Child(popup, "ConfirmButton"); Place(confirm, new Rect(area.x + 70, area.y + 40, area.width - 140, 150)); if (confirm != null) StyleButton(confirm.GetComponent<Button>(), true);
    }
    private void LayoutWearable()
    {
        var panel = transform.Find("WearablePanel"); if (panel == null) return;
        foreach (Transform child in panel)
        {
            var rect = child as RectTransform; if (rect == null) continue;
            if (child.name.Contains("Tab")) { Place(rect, Top(0, 0, safe.width, 160)); Surface(child.GetComponent<Image>(), "header-panel"); }
            else if (child.name.Contains("Page")) { Place(rect, ContentRect); Surface(child.GetComponent<Image>(), "card-default"); }
        }
        var live = panel.GetComponentInChildren<LiveWorkoutPageUI>(true); if (live != null) live.ApplyPortraitLayout(this, ContentRect);
        var history = panel.GetComponentInChildren<WorkoutHistoryController>(true); if (history != null) history.ApplyPortraitLayout(this, ContentRect);
    }
    private void LayoutAdmin()
    {
        var panel = transform.Find("AdminPanel"); var safeRoot = Child(panel, "MobileSettingsSafeArea"); if (safeRoot == null) return;
        var image = panel.GetComponent<Image>(); if (image != null) { image.color = new Color(.08f, .18f, .25f, .97f); image.raycastTarget = true; }
        Place(Child(safeRoot, "Header"), Top(0, 0, safe.width, 144));
        Label(Child(safeRoot, "Header"), "Title", Top(10, 10, safe.width - 270, 120), 40, Cream);
        Place(Child(safeRoot, "Header/Close"), Top(safe.width - 230, 0, 230, 144));
        Place(Child(safeRoot, "Tabs"), Top(0, 180, safe.width, 144));
        var tabs = safeRoot.Find("Tabs"); if (tabs != null) foreach (var button in tabs.GetComponentsInChildren<Button>(true)) button.GetComponent<LayoutElement>().preferredHeight = 144;
        var viewport = Child(safeRoot, "Viewport"); Place(viewport, new Rect(safe.x, safe.y + 330, safe.width, safe.height - 690)); Surface(viewport.GetComponent<Image>(), "card-default");
        var content = safeRoot.Find("Viewport/Content");
        if (content != null) foreach (var layout in content.GetComponentsInChildren<LayoutElement>(true))
        { if (layout.GetComponent<Button>() != null || layout.GetComponent<TMP_InputField>() != null) layout.preferredHeight = Mathf.Max(144, layout.preferredHeight); }
        if (content != null)
        {
            int activeIndex = 0, pageIndex = 0;
            foreach (Transform page in content) { if (page.gameObject.activeSelf) activeIndex = pageIndex; pageIndex++; }
            if (tabs != null) { int i = 0; foreach (var button in tabs.GetComponentsInChildren<Button>(true)) StyleButton(button, i++ == activeIndex); }
            var footer = Child(safeRoot, "PortraitFixedActions");
            if (footer == null) { footer = new GameObject("PortraitFixedActions", typeof(RectTransform), typeof(Image)).GetComponent<RectTransform>(); footer.SetParent(safeRoot, false); }
            Place(footer, new Rect(safe.x, safe.y + 145, safe.width, 160)); Surface(footer.GetComponent<Image>(), "card-default");
            foreach (Transform page in content)
            {
                bool registered = false;
                foreach (var existing in fixedActions) if (existing.Key != null && existing.Value == page) { registered = true; break; }
                if (registered) continue;
                Button action = null;
                foreach (var button in page.GetComponentsInChildren<Button>(true))
                {
                    bool match = page.name == "퀘스트" ? button.name == "QuestList" : page.name == "연결·설정" ? button.name == "Connect" : button.name == "TestControl";
                    if (match) { action = button; break; }
                }
                if (action != null) { fixedActions[action] = page; actionBindings.Add(new FixedActionBinding { action = action, page = page }); action.transform.SetParent(footer, false); }
            }
            foreach (var item in fixedActions)
            {
                if (item.Key == null || item.Value == null) continue;
                item.Key.gameObject.SetActive(item.Value.gameObject.activeSelf);
                Place((RectTransform)item.Key.transform, new Rect(safe.x + 15, safe.y + 153, safe.width - 30, 144)); StyleButton(item.Key, true);
            }
            foreach (var slider in content.GetComponentsInChildren<Slider>(true))
            {
                var row = slider.transform.parent as RectTransform;
                var size = row.GetComponent<LayoutElement>(); if (size != null) size.preferredHeight = 192;
                var title = Child(row, "Value"); if (title != null) { title.anchorMin = new Vector2(0, .74f); title.anchorMax = Vector2.one; title.offsetMin = title.offsetMax = Vector2.zero; }
                var area = (RectTransform)slider.transform; area.anchorMin = Vector2.zero; area.anchorMax = new Vector2(1, .72f); area.offsetMin = area.offsetMax = Vector2.zero;
                var handleArea = Child(area, "HandleArea");
                if (handleArea != null) { handleArea.anchorMin = new Vector2(0, .5f); handleArea.anchorMax = new Vector2(1, .5f); handleArea.sizeDelta = new Vector2(-52, 52); handleArea.anchoredPosition = Vector2.zero; }
                if (slider.handleRect != null) Surface(slider.handleRect.GetComponent<Image>(), "portrait-frame");
            }
        }
        Label(safeRoot, "Notice", new Rect(safe.x + 20, safe.y + 10, safe.width - 40, 135), 30, Cream);
    }
    private void LayoutAR()
    {
        var panel = transform.Find("PetARPanel"); if (panel == null) return;
        var header = Child(panel, "ARHeader"); Place(header, Top(0, 0, safe.width, 160)); Surface(header?.GetComponent<Image>(), "header-panel");
        if (header != null) foreach (var text in header.GetComponentsInChildren<TMP_Text>()) text.color = Cream;
        var hint = Child(panel, "ARInstructions"); Place(hint, new Rect(safe.x + 25, safe.y + 400, safe.width - 50, 210)); Surface(hint?.GetComponent<Image>(), "card-default");
    }
    public static bool TryPresentationPose(Camera camera, out Pose pose)
    {
        pose = default;
        if (Active == null || camera == null) return false;
        bool dialogue = Active.VisiblePanel("DialoguePanel");
        float fraction = dialogue ? .30f : .42f, bottom = dialogue ? .54f : .35f;
        var entry = Active.GetComponent<PortraitCharacterMenu>();
        if (entry != null && entry.IsOpen)
        {
            if (entry.IsSelecting && entry.PreviewBounds.height > 0)
            { bottom = (entry.PreviewBounds.yMin + 50) / Active.root.rect.height; fraction = (entry.PreviewBounds.height - 100) / Active.root.rect.height; }
            else { bottom = .27f; fraction = .42f; }
        }
        float height = Healthmon.Evolution.EvolutionClient.Instance?.Settings?.display_height_m ?? .6f;
        float distance = height / (2 * Mathf.Tan(camera.fieldOfView * Mathf.Deg2Rad * .5f) * fraction);
        var point = camera.ViewportToWorldPoint(new Vector3(.5f, bottom, Mathf.Max(.8f, distance)));
        pose = new Pose(point, Quaternion.LookRotation(camera.transform.forward, camera.transform.up));
        return true;
    }
    public void PreviewEnvironment(Camera camera)
    { sceneCamera = camera; UpdateBackdrop(true); }
    private void UpdateBackdrop(bool editorPreview = false)
    {
        if (!Application.isPlaying && !editorPreview) return;
        if (sceneCamera == null) sceneCamera = Camera.main;
        if (sceneCamera == null) return;
        if (backdrop == null)
        {
            var sprite = Sprite("Backgrounds/home-stage-portrait"); if (sprite == null) return;
            var shared = Resources.Load<Material>("HealthMon/PortraitUI/Backgrounds/PortraitEnvironment");
            var shader = shared != null ? shared.shader : Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Texture"); if (shader == null) return;
            backdrop = GameObject.CreatePrimitive(PrimitiveType.Quad); backdrop.name = "Portrait game environment";
            if (Application.isPlaying) Destroy(backdrop.GetComponent<Collider>()); else DestroyImmediate(backdrop.GetComponent<Collider>());
            backdrop.hideFlags = HideFlags.DontSave;
            backdropMaterial = shared != null ? new Material(shared) : new Material(shader); backdropMaterial.SetTexture("_BaseMap", sprite.texture); backdropMaterial.mainTexture = sprite.texture;
            backdropMaterial.SetFloat("_Cull", 0); backdrop.GetComponent<MeshRenderer>().sharedMaterial = backdropMaterial;
        }
        bool cameraView = VisiblePanel("PetARPanel") || Application.isMobilePlatform && VisiblePanel("FoodScanPanel") && transform.Find("FoodScanPanel/CaptureView").gameObject.activeSelf;
        backdrop.SetActive(!cameraView);
        float distance = Mathf.Min(8, sceneCamera.farClipPlane * .5f);
        float height = sceneCamera.orthographic ? 2 * sceneCamera.orthographicSize : 2 * distance * Mathf.Tan(sceneCamera.fieldOfView * Mathf.Deg2Rad * .5f);
        backdrop.transform.SetPositionAndRotation(sceneCamera.transform.position + sceneCamera.transform.forward * distance, sceneCamera.transform.rotation);
        backdrop.transform.localScale = new Vector3(height * sceneCamera.aspect, height, 1);
        var texture = backdropMaterial.mainTexture;
        if (texture != null)
        {
            float aspect = (float)texture.width / texture.height;
            var scale = aspect > sceneCamera.aspect ? new Vector2(sceneCamera.aspect / aspect, 1) : new Vector2(1, aspect / sceneCamera.aspect);
            backdropMaterial.mainTextureScale = scale; backdropMaterial.mainTextureOffset = (Vector2.one - scale) / 2;
        }
    }
    private void OnDestroy()
    {
        if (Active == this) Active = null;
        if (Application.isPlaying) { if (backdrop != null) Destroy(backdrop); if (backdropMaterial != null) Destroy(backdropMaterial); }
        else { if (backdrop != null) DestroyImmediate(backdrop); if (backdropMaterial != null) DestroyImmediate(backdropMaterial); }
    }
}
