using System;
using System.Collections.Generic;
using System.Globalization;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public sealed class MobileAdminMenu : MonoBehaviour
{
    public static MobileAdminMenu Instance { get; private set; }
    private UIManager manager;
    private GameObject panel;
    private RectTransform safeRoot, launcher, content;
    private TMP_FontAsset font;
    private TMP_Text connectionStatus, notice, stateSummary;
    private TMP_InputField level, coin, address, token, pet, amount;
    private readonly Dictionary<string, Slider> axes = new Dictionary<string, Slider>();
    private readonly List<GameObject> pages = new List<GameObject>();
    private readonly List<Button> testButtons = new List<Button>();
    private readonly List<Button> tabs = new List<Button>();
    private int pageIndex, exerciseIndex;
    private string currentScope;
    private bool wasOpen;
    private TMP_Text exerciseLabel;
    private readonly string[] exercises = { "walking", "running", "pushup", "squat", "lunge", "dumbbell" };
    private readonly string[] exerciseNames = { "걷기 · 걸음", "달리기 · 분", "푸시업 · 회", "스쿼트 · 회", "런지 · 회", "덤벨 · 회" };
    private static readonly Color Background = new Color(.035f, .07f, .13f, 1);
    private static readonly Color Card = new Color(.08f, .14f, .23f, 1);
    private static readonly Color Accent = new Color(.08f, .59f, .78f, 1);
    private CommonServerConnection Connection => CommonServerConnection.Instance;

    private void OnEnable()
    {
        Instance = this;
        if (manager != null && panel != null)
            Configure(manager, panel, panel.GetComponentInParent<Canvas>(), font);
    }

    public void Configure(UIManager owner, GameObject admin, Canvas canvas, TMP_FontAsset textFont)
    {
        Instance = this; manager = owner; panel = admin; font = textFont;
        if (canvas == null) return;
        // Runtime UnityEvent listeners do not survive script reloads.
        // Rebuild only this generated menu, preserving the existing scene.
        var rootCanvas = canvas.rootCanvas;
        canvas = rootCanvas != null ? rootCanvas : canvas;
        var previous = panel.transform.Find("MobileSettingsSafeArea");
        if (previous != null) { previous.gameObject.SetActive(false); Destroy(previous.gameObject); }
        var previousLauncher = canvas.transform.Find("UnifiedSettingsButton");
        if (previousLauncher != null) { previousLauncher.gameObject.SetActive(false); Destroy(previousLauncher.gameObject); }
        axes.Clear(); pages.Clear(); testButtons.Clear(); tabs.Clear();
        foreach (var button in canvas.GetComponentsInChildren<Button>(true))
            if (button.name == "AdminOpenButton") button.gameObject.SetActive(false);
        foreach (Transform old in panel.transform) old.gameObject.SetActive(false);
        var legacy = panel.GetComponent<HealthMonAdminPanel>();
        if (legacy != null) legacy.enabled = false;
        var overlay = panel.GetComponent<Canvas>();
        if (overlay == null) overlay = panel.AddComponent<Canvas>();
        overlay.overrideSorting = true; overlay.sortingOrder = 100;
        if (panel.GetComponent<GraphicRaycaster>() == null) panel.AddComponent<GraphicRaycaster>();
        var background = panel.GetComponent<Image>() ?? panel.AddComponent<Image>();
        background.enabled = true; background.sprite = null; background.type = Image.Type.Simple;
        background.color = Background; background.raycastTarget = true;
        safeRoot = Rect("MobileSettingsSafeArea", panel.transform);
        var header = Rect("Header", safeRoot); Top(header, 0, 120);
        var title = Text("Title", header, "설정 · 테스트 관리", 42);
        title.rectTransform.offsetMax = new Vector2(-260, 0);
        var close = FixedButton("Close", header, "닫기", () => manager.CloseAdmin());
        close.anchorMin = close.anchorMax = new Vector2(1, .5f); close.pivot = new Vector2(1, .5f);
        close.sizeDelta = new Vector2(240, 104); close.anchoredPosition = new Vector2(-20, 0);
        var navigation = Rect("Tabs", safeRoot); Top(navigation, 128, 104);
        var horizontal = navigation.gameObject.AddComponent<HorizontalLayoutGroup>();
        horizontal.spacing = 10; horizontal.padding = new RectOffset(20, 20, 0, 0);
        horizontal.childControlWidth = horizontal.childControlHeight = true;
        horizontal.childForceExpandWidth = true;
        string[] labels = { "캐릭터", "운동", "퀘스트", "연결·설정" };
        for (int i = 0; i < labels.Length; i++)
        {
            int index = i;
            var button = Button("Tab" + i, navigation, labels[i], () => SelectPage(index), 104);
            button.GetComponent<LayoutElement>().flexibleWidth = 1; tabs.Add(button);
        }
        var viewport = Rect("Viewport", safeRoot);
        viewport.offsetMin = new Vector2(24, 110); viewport.offsetMax = new Vector2(-24, -252);
        viewport.gameObject.AddComponent<Image>().color = new Color(0, 0, 0, .01f);
        viewport.gameObject.AddComponent<RectMask2D>();
        var scroll = viewport.gameObject.AddComponent<ScrollRect>();
        scroll.horizontal = false; scroll.scrollSensitivity = 50; scroll.movementType = ScrollRect.MovementType.Clamped;
        content = Vertical("Content", viewport); scroll.content = content; scroll.viewport = viewport;
        notice = Text("Notice", safeRoot, "", 28); Bottom(notice.rectTransform, 12, 86);
        foreach (string label in labels) pages.Add(Vertical(label, content).gameObject);
        BuildCharacter(pages[0].transform); BuildExercise(pages[1].transform);
        BuildQuests(pages[2].transform); BuildConnection(pages[3].transform);
        launcher = FixedButton("UnifiedSettingsButton", canvas.transform, "설정 · 관리", () => manager.ShowAdmin());
        launcher.anchorMin = launcher.anchorMax = launcher.pivot = Vector2.one;
        launcher.sizeDelta = new Vector2(260, 112);
        SelectPage(0);
    }

    private void BuildCharacter(Transform page)
    {
        stateSummary = Label(page, "서버에 연결하면 현재 상태를 불러옵니다.", 120);
        Label(page, "테스트 계정에서만 아래 값을 변경할 수 있어요. 실제 운동·식사 기록은 유지됩니다.", 90);
        var basic = Row(page, 184);
        level = Input(basic, "레벨", "1", TMP_InputField.ContentType.IntegerNumber);
        coin = Input(basic, "코인", "0", TMP_InputField.ContentType.IntegerNumber);
        string[] keys = { "affinity", "activity", "initiative", "upper_body", "lower_body", "nutrition", "energy_balance" };
        string[] names = { "친밀도", "활동성", "주도성", "상체", "하체", "영양", "에너지 균형" };
        for (int i = 0; i < keys.Length; i++) axes[keys[i]] = SliderRow(page, names[i], keys[i] == "energy_balance" ? -100 : 0, 100);
        TestButton(page, "캐릭터·성격 적용", ApplyState);
        Button("ReloadState", page, "현재 값 다시 불러오기", LoadState);
        TestButton(page, "테스트 조정 해제 · 기록 기준으로 복원", () => Connection.Api.ClearTestState(Applied, Failed));
        TestButton(page, "새 테스트 펫으로 시작", () => { Connection.CreateFreshTestPet(); notice.text = "새 펫을 준비하고 있어요. 기존 펫과 기록은 유지됩니다."; });
    }

    private void BuildExercise(Transform page)
    {
        Label(page, "운동 테스트", 86, 36);
        Label(page, "종류와 수행량을 골라 서버에 테스트 기록을 보냅니다. 연결된 펫의 상태와 퀘스트가 함께 갱신돼요.", 110);
        var cycle = Button("Exercise", page, exerciseNames[0], () => {
            exerciseIndex = (exerciseIndex + 1) % exercises.Length; exerciseLabel.text = exerciseNames[exerciseIndex];
            amount.text = exerciseIndex == 0 ? "3000" : exerciseIndex == 1 ? "30" : "30";
        });
        exerciseLabel = cycle.GetComponentInChildren<TMP_Text>();
        amount = Input(page, "수행량", "3000", TMP_InputField.ContentType.DecimalNumber);
        TestButton(page, "운동 테스트 기록 추가", () => {
            float actual;
            if (!float.TryParse(amount.text, NumberStyles.Float, CultureInfo.InvariantCulture, out actual) || actual < 0)
            { notice.text = "수행량을 0 이상의 숫자로 입력해 주세요."; return; }
            Connection.Api.RecordTestWorkout(exercises[exerciseIndex], actual, Applied, Failed);
        });
        Button("Wearable", page, "실제 운동·웨어러블 화면 열기", () => manager.ShowWearable());
    }

    private void BuildQuests(Transform page)
    {
        Label(page, "퀘스트 테스트", 86, 36);
        Label(page, "오늘·이번 주 퀘스트 종류를 바꿉니다. 기록과 이미 지급된 보상은 유지되며 중복 지급되지 않아요.", 110);
        QuestSelector(page, "쉬움", "easy", new[] { "식사 1회", "운동 1회", "대화 1회" }, new[] { "meal1", "workout1", "chat1" });
        QuestSelector(page, "보통", "medium", new[] { "식사 2회", "운동 70%", "식사+운동" }, new[] { "meal2", "workout70", "meal_workout" });
        QuestSelector(page, "주간", "weekly", new[] { "운동 3일", "식사 5일", "일일 6개" }, new[] { "workout_days3", "meal_days5", "daily6" });
        Button("QuestList", page, "현재 퀘스트·진행 상황 보기", () => manager.ShowQuest());
    }

    private void QuestSelector(Transform page, string title, string slot, string[] names, string[] candidates)
    {
        int selected = 0;
        Label(page, title, 64, 30);
        Button picker = null;
        picker = Button("Choose" + slot, page, names[0] + "  ›", () => {
            selected = (selected + 1) % names.Length; picker.GetComponentInChildren<TMP_Text>().text = names[selected] + "  ›";
        });
        TestButton(page, title + " 퀘스트 적용", () => Connection.Api.SelectTestQuest(slot, candidates[selected], Applied, Failed));
    }

    private void BuildConnection(Transform page)
    {
        connectionStatus = Label(page, "연결 상태 확인 중", 110);
        address = Input(page, "서버 주소", Connection?.ConnectionAddress ?? "http://127.0.0.1:8020");
        token = Input(page, "사용자 토큰", ""); token.contentType = TMP_InputField.ContentType.Password;
        pet = Input(page, "펫 ID · 비워두면 기존 선택 유지", "");
        Button("Connect", page, "서버 연결 / 연결 변경", () => {
            Connection.Connect(address.text, token.text, pet.text); token.text = ""; notice.text = "서버 연결을 확인하고 있어요.";
        });
        Button("Refresh", page, "서버 상태 새로고침", () => { Connection.RefreshState(); Connection.RefreshQuests(); });
        Button("Evolution", page, "진화 요청 / 같은 작업 재시도", () => Healthmon.Evolution.EvolutionClient.Instance?.RequestCommonEvolution());
        Button("PhoneSync", page, "휴대폰 운동 동기화", () => { HealthMonAndroidBridge.RequestServerSync(); Connection.RefreshPhoneStatus(); });
    }

    private void SelectPage(int index)
    {
        pageIndex = index;
        for (int i = 0; i < pages.Count; i++) { pages[i].SetActive(i == index); tabs[i].GetComponent<Image>().color = i == index ? Accent : Card; }
        content.anchoredPosition = Vector2.zero;
    }
    private void Update()
    {
        if (panel == null || launcher == null || safeRoot == null) return;
        bool open = panel.activeInHierarchy;
        launcher.gameObject.SetActive(!open);
        Rect safe = Screen.safeArea;
        safeRoot.anchorMin = new Vector2(safe.xMin / Screen.width, safe.yMin / Screen.height);
        safeRoot.anchorMax = new Vector2(safe.xMax / Screen.width, safe.yMax / Screen.height);
        float scale = launcher.GetComponentInParent<Canvas>().scaleFactor;
        launcher.anchoredPosition = new Vector2(-(Screen.width - safe.xMax) / scale - 24, -(Screen.height - safe.yMax) / scale - 24);
        if (!open) { wasOpen = false; return; }
        panel.transform.SetAsLastSibling();
        var connection = Connection;
        string scope = connection == null ? "" : connection.ServerInstanceId + ":" + connection.OwnerId + ":" + connection.Api.PetId;
        if (!wasOpen || scope != currentScope) { LoadState(); currentScope = scope; }
        wasOpen = true;
        bool allowed = connection != null && connection.IsConnected && connection.CanUseTestControls && !connection.Api.IsBusy && !connection.Api.HasPendingChat;
        foreach (var button in testButtons) button.interactable = allowed;
        connectionStatus.text = connection == null ? "서버 연결이 필요합니다." : connection.IsConnected
            ? "연결됨 · " + connection.EnvironmentName + "\n" + connection.BaseUrl + "\n펫 " + connection.Api.PetId
            : connection.Status;
        if (!allowed && string.IsNullOrEmpty(notice.text)) notice.text = "연결된 테스트 계정에서 캐릭터·운동·퀘스트를 조작할 수 있어요.";
    }

    public void LoadState()
    {
        var state = Connection?.LatestState;
        if (state == null) return;
        level.text = state.level.ToString(); coin.text = state.coin.ToString();
        axes["affinity"].value = state.affinity; axes["activity"].value = state.activity; axes["initiative"].value = state.initiative;
        axes["upper_body"].value = state.upper_body; axes["lower_body"].value = state.lower_body;
        axes["nutrition"].value = state.nutrition; axes["energy_balance"].value = state.energy_balance;
        stateSummary.text = state.settings?.name + " · Lv. " + state.level + " · 코인 " + state.coin + "\n친밀도 " + state.affinity + " · 활동성 " + state.activity + " · 주도성 " + state.initiative;
    }
    private void ApplyState()
    {
        int selectedLevel, selectedCoin;
        if (!int.TryParse(level.text, out selectedLevel) || selectedLevel < 1 || selectedLevel > 100 || !int.TryParse(coin.text, out selectedCoin) || selectedCoin < 0)
        { notice.text = "레벨 1~100, 코인 0 이상의 정수를 입력해 주세요."; return; }
        Connection.Api.ApplyTestState(new TestPetStateRequest { level = selectedLevel, coin = selectedCoin,
            affinity = axes["affinity"].value, activity = axes["activity"].value, initiative = axes["initiative"].value,
            upper_body = axes["upper_body"].value, lower_body = axes["lower_body"].value, nutrition = axes["nutrition"].value,
            energy_balance = axes["energy_balance"].value }, Applied, Failed);
    }
    private void Applied(PetState state) { notice.text = "서버에 적용했습니다."; LoadState(); Connection.RefreshQuests(); }
    private void Failed(ApiFailure error) { notice.text = "적용하지 못했습니다. 연결과 테스트 계정을 확인해 주세요. (" + error.StatusCode + ")"; }

    private Button TestButton(Transform parent, string label, UnityEngine.Events.UnityAction action)
    { var button = Button("TestControl", parent, label, action); testButtons.Add(button); return button; }
    private TMP_Text Label(Transform parent, string value, float height, float size = 28)
    { var text = Text("Label", parent, value, size); text.gameObject.AddComponent<LayoutElement>().preferredHeight = height; return text; }
    private RectTransform Row(Transform parent, float height)
    {
        var row = Rect("Row", parent); row.gameObject.AddComponent<LayoutElement>().preferredHeight = height;
        var layout = row.gameObject.AddComponent<HorizontalLayoutGroup>(); layout.spacing = 20; layout.childControlWidth = layout.childControlHeight = true;
        layout.childForceExpandWidth = true; return row;
    }
    private TMP_InputField Input(Transform parent, string label, string value, TMP_InputField.ContentType type = TMP_InputField.ContentType.Standard)
    {
        var row = Vertical(label, parent); row.gameObject.AddComponent<LayoutElement>().preferredHeight = 184;
        Label(row, label, 44, 26);
        var background = Rect("Input", row); background.gameObject.AddComponent<Image>().color = new Color(.92f, .96f, 1);
        background.gameObject.AddComponent<LayoutElement>().preferredHeight = 104;
        var viewport = Rect("TextArea", background); viewport.offsetMin = new Vector2(20, 8); viewport.offsetMax = new Vector2(-20, -8);
        viewport.gameObject.AddComponent<RectMask2D>();
        var text = Text("Text", viewport, "", 30); text.color = Background;
        var field = background.gameObject.AddComponent<TMP_InputField>(); field.textViewport = viewport; field.textComponent = text;
        field.contentType = type; field.lineType = TMP_InputField.LineType.SingleLine; field.text = value;
        return field;
    }
    private Slider SliderRow(Transform parent, string name, float min, float max)
    {
        var row = Rect(name, parent); row.gameObject.AddComponent<LayoutElement>().preferredHeight = 132;
        var title = Text("Value", row, name, 30); title.rectTransform.anchorMin = new Vector2(0, .6f);
        var area = Rect("Slider", row); area.anchorMax = new Vector2(1, .56f);
        area.gameObject.AddComponent<Image>().color = new Color(1, 1, 1, .01f);
        var track = Rect("Track", area); track.anchorMin = new Vector2(0, .4f); track.anchorMax = new Vector2(1, .6f);
        track.gameObject.AddComponent<Image>().color = new Color(.2f, .3f, .42f);
        var fillArea = Rect("FillArea", area); var fill = Rect("Fill", fillArea); fill.gameObject.AddComponent<Image>().color = Accent;
        fill.anchorMin = new Vector2(0, .4f); fill.anchorMax = new Vector2(1, .6f);
        var handleArea = Rect("HandleArea", area); handleArea.offsetMin = new Vector2(26, 0); handleArea.offsetMax = new Vector2(-26, 0);
        var handle = Rect("Handle", handleArea); handle.sizeDelta = new Vector2(52, 0); handle.gameObject.AddComponent<Image>().color = Color.white;
        var slider = area.gameObject.AddComponent<Slider>(); slider.fillRect = fill; slider.handleRect = handle; slider.targetGraphic = handle.GetComponent<Image>();
        slider.minValue = min; slider.maxValue = max; slider.wholeNumbers = true;
        slider.onValueChanged.AddListener(value => title.text = name + "  " + value.ToString("0")); slider.value = min;
        title.text = name + "  " + min.ToString("0"); return slider;
    }
    private Button Button(string name, Transform parent, string label, UnityEngine.Events.UnityAction action, float height = 112)
    { var rect = FixedButton(name, parent, label, action); rect.gameObject.AddComponent<LayoutElement>().preferredHeight = height; return rect.GetComponent<Button>(); }
    private RectTransform FixedButton(string name, Transform parent, string label, UnityEngine.Events.UnityAction action)
    {
        var rect = Rect(name, parent); rect.gameObject.AddComponent<Image>().color = Accent;
        var button = rect.gameObject.AddComponent<Button>(); button.onClick.AddListener(action);
        var text = Text("Label", rect, label, 30); text.alignment = TextAlignmentOptions.Center;
        text.rectTransform.offsetMin = new Vector2(16, 6); text.rectTransform.offsetMax = new Vector2(-16, -6); return rect;
    }
    private TMP_Text Text(string name, Transform parent, string value, float size)
    {
        var rect = Rect(name, parent); var text = rect.gameObject.AddComponent<TextMeshProUGUI>();
        text.font = font; text.text = value; text.fontSize = size; text.color = Color.white; text.raycastTarget = false;
        text.alignment = TextAlignmentOptions.MidlineLeft; text.enableAutoSizing = true; text.fontSizeMin = 22; text.fontSizeMax = size; return text;
    }
    private RectTransform Vertical(string name, Transform parent)
    {
        var rect = Rect(name, parent); rect.anchorMin = new Vector2(0, 1); rect.anchorMax = Vector2.one; rect.pivot = new Vector2(.5f, 1);
        var layout = rect.gameObject.AddComponent<VerticalLayoutGroup>(); layout.spacing = 18; layout.padding = new RectOffset(12, 12, 12, 12);
        layout.childControlWidth = layout.childControlHeight = true; layout.childForceExpandWidth = true; layout.childForceExpandHeight = false;
        rect.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize; return rect;
    }
    private RectTransform Rect(string name, Transform parent)
    { var rect = (RectTransform)new GameObject(name, typeof(RectTransform)).transform; rect.SetParent(parent, false); rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one; rect.offsetMin = rect.offsetMax = Vector2.zero; return rect; }
    private void Top(RectTransform rect, float offset, float height)
    { rect.anchorMin = new Vector2(0, 1); rect.anchorMax = Vector2.one; rect.pivot = new Vector2(.5f, 1); rect.anchoredPosition = new Vector2(0, -offset); rect.sizeDelta = new Vector2(0, height); }
    private void Bottom(RectTransform rect, float offset, float height)
    { rect.anchorMin = new Vector2(0, 0); rect.anchorMax = new Vector2(1, 0); rect.pivot = new Vector2(.5f, 0); rect.sizeDelta = new Vector2(-48, height); rect.anchoredPosition = new Vector2(0, offset); }
    private void OnDestroy() { if (Instance == this) Instance = null; }
}
