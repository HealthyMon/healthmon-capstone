using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Entry/selection UI uses the same account, pet list and selection path as the game.
public sealed class PortraitCharacterMenu : MonoBehaviour
{
    private PortraitGameUI theme;
    private UIManager manager;
    private TMP_FontAsset font;
    private RectTransform start, selection, preview, list, footer, nameInputRect;
    private TMP_Text currentPet, notice;
    private TMP_InputField newName;
    private bool fromHome;
    public Rect PreviewBounds { get; private set; }
    public bool IsOpen => start != null && start.gameObject.activeSelf || selection != null && selection.gameObject.activeSelf;
    public bool IsSelecting => selection != null && selection.gameObject.activeSelf;
    private CommonServerConnection Connection => CommonServerConnection.Instance;
    private void OnEnable()
    {
        if (!Application.isPlaying) return;
        theme = GetComponent<PortraitGameUI>(); manager = FindAnyObjectByType<UIManager>();
        font = GetComponentInChildren<TMP_Text>(true)?.font ?? TMP_Settings.defaultFontAsset;
        start = transform.Find("PortraitStartPanel") as RectTransform;
        selection = transform.Find("PortraitCharacterPanel") as RectTransform;
        if (start == null || selection == null) return;
        preview = selection.Find("PreviewFrame") as RectTransform; list = selection.Find("OwnedPets/Content") as RectTransform;
        footer = selection.Find("Enter") as RectTransform; nameInputRect = selection.Find("NewPetName") as RectTransform;
        newName = nameInputRect.GetComponent<TMP_InputField>(); currentPet = selection.Find("CurrentPet").GetComponent<TMP_Text>(); notice = selection.Find("Notice").GetComponent<TMP_Text>();
        BindCallbacks(); PortraitGameUI.Refresh();
        if (IsSelecting) OpenSelection(fromHome);
    }

    public void Configure(PortraitGameUI visual, UIManager owner)
    {
        theme = visual; manager = owner;
        font = GetComponentInChildren<TMP_Text>(true)?.font ?? TMP_Settings.defaultFontAsset;
        if (start != null) { BindCallbacks(); return; }
        start = Rect("PortraitStartPanel", transform); Overlay(start);
        Text("Logo", start, "HEALTHMON", 94, true);
        Text("Subtitle", start, "나의 기록과 함께\n자라는 캐릭터", 40, true);
        Button("Continue", start, "이어서 시작하기", EnterGame);
        Button("SelectCharacter", start, "캐릭터 선택", () => OpenSelection(false));
        selection = Rect("PortraitCharacterPanel", transform); Overlay(selection);
        var header = Rect("Header", selection); Surface(header, "header-panel");
        Text("Title", header, "캐릭터 선택", 43, true);
        Button("Back", header, "뒤로", () => { if (fromHome) EnterGame(); else OpenStart(); });
        preview = Rect("PreviewFrame", selection); Surface(preview, "card-dark"); preview.GetComponent<Image>().fillCenter = false;
        Surface(Rect("CurrentPetCard", selection), "card-dark"); Surface(Rect("NoticeCard", selection), "card-dark");
        currentPet = Text("CurrentPet", selection, "저장된 캐릭터", 38, true);
        var viewport = Rect("OwnedPets", selection); Surface(viewport, "card-default"); viewport.gameObject.AddComponent<RectMask2D>();
        var scroll = viewport.gameObject.AddComponent<ScrollRect>(); scroll.horizontal = false; scroll.movementType = ScrollRect.MovementType.Clamped;
        list = Rect("Content", viewport); list.anchorMin = new Vector2(0, 1); list.anchorMax = Vector2.one; list.pivot = new Vector2(.5f, 1);
        var layout = list.gameObject.AddComponent<VerticalLayoutGroup>(); layout.spacing = 16; layout.padding = new RectOffset(18, 18, 18, 18); layout.childControlHeight = layout.childControlWidth = true; layout.childForceExpandHeight = false;
        list.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize; scroll.content = list; scroll.viewport = viewport;
        nameInputRect = Rect("NewPetName", selection); Surface(nameInputRect, "input-default");
        var value = Text("Value", nameInputRect, "", 36, false); var hint = Text("Hint", nameInputRect, "새 캐릭터 이름", 34, false); hint.color = new Color(.4f, .49f, .48f);
        newName = nameInputRect.gameObject.AddComponent<TMP_InputField>(); newName.textComponent = value; newName.textViewport = nameInputRect; newName.placeholder = hint; newName.characterLimit = 24;
        notice = Text("Notice", selection, "새 캐릭터를 만들어도 기존 펫과 기록은 보존돼요.", 29, true);
        Button("NewPet", selection, "새 캐릭터 만들기", CreatePet);
        footer = (RectTransform)Button("Enter", selection, "함께 시작하기", EnterGame).transform;
        var profile = transform.Find("HomePanel/TopInfoPanel");
        if (profile != null)
        {
            var button = profile.GetComponent<Button>() ?? profile.gameObject.AddComponent<Button>(); button.targetGraphic = profile.GetComponent<Image>();
            button.transition = Selectable.Transition.None;
        }
        BindCallbacks();
        OpenStart();
    }
    private void OpenFromHome() { OpenSelection(true); }
    private void BindCallbacks()
    {
        Bind(start, "Continue", EnterGame); Bind(start, "SelectCharacter", () => OpenSelection(false));
        Bind(selection, "Header/Back", () => { if (fromHome) EnterGame(); else OpenStart(); });
        Bind(selection, "NewPet", CreatePet); Bind(selection, "Enter", EnterGame);
        var profile = transform.Find("HomePanel/TopInfoPanel")?.GetComponent<Button>();
        if (profile != null) { profile.onClick.RemoveListener(OpenFromHome); profile.onClick.AddListener(OpenFromHome); }
    }
    private static void Bind(Transform parent, string path, UnityEngine.Events.UnityAction callback)
    { var button = parent.Find(path).GetComponent<Button>(); button.onClick.RemoveAllListeners(); button.onClick.AddListener(callback); }
    public void OpenStart()
    {
        start.gameObject.SetActive(true); selection.gameObject.SetActive(false);
        var home = transform.Find("HomePanel"); if (home != null) home.gameObject.SetActive(false);
        start.SetAsLastSibling(); PortraitGameUI.Refresh();
    }
    public void OpenSelection(bool openedFromHome)
    {
        fromHome = openedFromHome; start.gameObject.SetActive(false); selection.gameObject.SetActive(true);
        var home = transform.Find("HomePanel"); if (home != null) home.gameObject.SetActive(false);
        selection.SetAsLastSibling(); PortraitGameUI.Refresh();
        foreach (Transform row in list) { row.gameObject.SetActive(false); Destroy(row.gameObject); }
        var connection = Connection;
        if (connection == null || connection.Api == null || string.IsNullOrEmpty(connection.OwnerId) || connection.Api.IsBusy)
        { EmptyList("서버 연결 후 다시 열면\n내 캐릭터 목록을 불러와요."); notice.text = "현재 캐릭터로 시작한 뒤 설정·관리에서 연결을 확인할 수 있어요."; return; }
        string scope = connection.ServerInstanceId + "/" + connection.OwnerId;
        connection.Api.ListPets(result => {
            if (this == null || connection != Connection || scope != connection.ServerInstanceId + "/" + connection.OwnerId || !IsSelecting) return;
            var pets = result.pets ?? new PetSummary[0];
            if (pets.Length == 0) EmptyList("저장된 캐릭터가 없어요.\n아래에서 새 캐릭터를 만들 수 있어요.");
            foreach (var pet in pets)
            {
                string id = pet.pet_id;
                var button = Button("OwnedPet", list, pet.name ?? "헬스몬", () => {
                    if (Connection.TryChooseOwnedPet(id)) notice.text = "선택한 캐릭터를 불러오고 있어요.";
                    else notice.text = "진행 중인 대화나 진화가 끝난 뒤 다시 선택해 주세요.";
                });
                button.gameObject.AddComponent<LayoutElement>().preferredHeight = 144;
            }
            notice.text = "캐릭터를 고른 뒤 함께 시작하기를 눌러 주세요."; PortraitGameUI.Refresh();
        }, _ => { if (this != null && connection == Connection && scope == connection.ServerInstanceId + "/" + connection.OwnerId && IsSelecting) { EmptyList("캐릭터 목록을 불러오지 못했어요."); notice.text = "현재 캐릭터로 계속할 수 있어요. 연결 후 다시 열어 주세요."; } });
    }
    private void EmptyList(string message)
    { Text("EmptyList", list, message, 32, false).gameObject.AddComponent<LayoutElement>().preferredHeight = 180; }
    private void CreatePet()
    {
        if (Connection == null || !Connection.TryCreateNamedPet(newName.text)) { notice.text = "서버 연결과 이름을 확인하고, 진행 중인 작업이 끝난 뒤 다시 시도해 주세요."; return; }
        notice.text = "새 캐릭터를 만들고 있어요. 기존 기록은 유지됩니다.";
    }
    public void EnterGame()
    { if (start != null) start.gameObject.SetActive(false); if (selection != null) selection.gameObject.SetActive(false); manager.ShowHome(); PortraitGameUI.Refresh(); }
    public void HideForVerification()
    { if (start != null) start.gameObject.SetActive(false); if (selection != null) selection.gameObject.SetActive(false); }
    private void Update()
    {
        if (currentPet == null) return;
        var state = Connection?.LatestState;
        currentPet.text = state == null ? "저장된 캐릭터 · 서버 연결 대기" : (state.settings?.name ?? "헬스몬") + " · Lv. " + state.level;
    }
    public void Arrange(Rect safe)
    {
        if (start == null) return;
        float width = safe.width;
        theme.Place((RectTransform)start.Find("Logo"), new Rect(safe.x, safe.yMax - 250, width, 140));
        theme.Place((RectTransform)start.Find("Subtitle"), new Rect(safe.x + 30, safe.yMax - 430, width - 60, 160));
        theme.Place((RectTransform)start.Find("Continue"), new Rect(safe.x + 50, safe.y + 260, width - 100, 158)); theme.StyleButton(start.Find("Continue").GetComponent<Button>(), true);
        theme.Place((RectTransform)start.Find("SelectCharacter"), new Rect(safe.x + 50, safe.y + 65, width - 100, 158));
        var header = selection.Find("Header"); theme.Place((RectTransform)header, new Rect(safe.x, safe.yMax - 160, width, 160));
        theme.Place((RectTransform)header.Find("Back"), new Rect(safe.x + 15, safe.yMax - 145, 150, 130));
        float previewHeight = Mathf.Min(720, safe.height * .32f);
        PreviewBounds = new Rect(safe.x, safe.yMax - 210 - previewHeight, width, previewHeight);
        theme.Place(preview, PreviewBounds);
        float currentY = PreviewBounds.yMin - 110;
        theme.Place((RectTransform)selection.Find("CurrentPetCard"), new Rect(safe.x + 20, currentY, width - 40, 90));
        theme.Place(currentPet.rectTransform, new Rect(safe.x + 30, currentY, width - 60, 90));
        theme.Place((RectTransform)selection.Find("OwnedPets"), new Rect(safe.x, safe.y + 680, width, Mathf.Max(145, currentY - 35 - safe.y - 680)));
        theme.Place(nameInputRect, new Rect(safe.x + 20, safe.y + 495, width - 40, 144));
        theme.Place((RectTransform)selection.Find("NewPet"), new Rect(safe.x + 20, safe.y + 320, width - 40, 144));
        theme.Place(notice.rectTransform, new Rect(safe.x + 20, safe.y + 175, width - 40, 125));
        theme.Place((RectTransform)selection.Find("NoticeCard"), new Rect(safe.x + 15, safe.y + 175, width - 30, 125));
        theme.Place(footer, new Rect(safe.x + 20, safe.y + 10, width - 40, 144)); theme.StyleButton(footer.GetComponent<Button>(), true);
        foreach (var text in start.GetComponentsInChildren<TMP_Text>(true)) if (text.GetComponentInParent<Button>() == null) text.color = PortraitGameUI.Cream;
        foreach (var text in selection.GetComponentsInChildren<TMP_Text>(true)) if (text.GetComponentInParent<Button>() == null && text.GetComponentInParent<TMP_InputField>() == null) text.color = PortraitGameUI.Cream;
        foreach (var text in list.GetComponentsInChildren<TMP_Text>(true)) if (text.GetComponentInParent<Button>() == null) text.color = PortraitGameUI.Ink;
    }
    private RectTransform Rect(string name, Transform parent)
    { var rect = new GameObject(name, typeof(RectTransform)).GetComponent<RectTransform>(); rect.SetParent(parent, false); rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one; rect.offsetMin = rect.offsetMax = Vector2.zero; return rect; }
    private void Surface(RectTransform rect, string sprite)
    { var image = rect.gameObject.AddComponent<Image>(); image.sprite = theme.Sprite("Components/" + sprite); image.type = Image.Type.Sliced; image.color = Color.white; image.raycastTarget = false; }
    private void Overlay(RectTransform rect)
    { var image = rect.gameObject.AddComponent<Image>(); image.color = new Color(.04f, .12f, .18f, .035f); image.raycastTarget = true; }
    private TMP_Text Text(string name, Transform parent, string value, float size, bool light)
    {
        var rect = Rect(name, parent); rect.offsetMin = new Vector2(24, 10); rect.offsetMax = new Vector2(-24, -10);
        var text = rect.gameObject.AddComponent<TextMeshProUGUI>(); text.font = font; text.text = value; text.fontSize = text.fontSizeMax = size; text.fontSizeMin = 28; text.enableAutoSizing = true; text.color = light ? PortraitGameUI.Cream : PortraitGameUI.Ink; text.alignment = TextAlignmentOptions.Center; text.raycastTarget = false; return text;
    }
    private Button Button(string name, Transform parent, string value, UnityEngine.Events.UnityAction callback)
    { var rect = Rect(name, parent); rect.gameObject.AddComponent<Image>(); var button = rect.gameObject.AddComponent<Button>(); Text("Label", rect, value, 36, true); button.onClick.AddListener(callback); theme.StyleButton(button, false); return button; }
}
