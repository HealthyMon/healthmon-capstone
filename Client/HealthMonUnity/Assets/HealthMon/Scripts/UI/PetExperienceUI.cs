using Healthmon.Common;
using Healthmon.Evolution;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Bind the existing home, status and navigation to the authoritative pet state.
// Runtime controls keep the team's scene references and layout assets intact.
public sealed class PetExperienceUI : MonoBehaviour
{
    private UIManager manager;
    private GameObject arPanel;
    private TMP_FontAsset font;
    private Button evolutionButton, freshPetButton;
    private TMP_Text evolutionLabel, statusText, arHint;
    private ARPlacementManager placement;
    private EvolutionFlowController evolutionFlow;
    private PetStateManager localPet;

    public void Configure(UIManager owner, GameObject home, GameObject status, GameObject admin)
    {
        manager = owner;
        localPet = FindAnyObjectByType<PetStateManager>();
        if (CommonServerConnection.UsesServerAuthority)
        {
            evolutionFlow = gameObject.AddComponent<EvolutionFlowController>();
            evolutionFlow.Configure(owner);
        }
        var reference = home.GetComponentInChildren<TMP_Text>(true);
        font = reference != null ? reference.font : TMP_Settings.defaultFontAsset;
        evolutionButton = MakeButton("HomeEvolutionButton", home.transform, "진화", RequestEvolution,
            new Vector2(.70f, .38f), new Vector2(.97f, .45f));
        evolutionLabel = evolutionButton.GetComponentInChildren<TMP_Text>();
        var arButton = MakeButton("PetARButton", home.transform, "펫 AR", manager.ShowAR,
            new Vector2(.74f, .76f), new Vector2(.98f, .81f));
        foreach (var button in home.GetComponentsInChildren<Button>(true))
        {
            var label = button.GetComponentInChildren<TMP_Text>(true);
            if (button == evolutionButton || label == null || label.text.Replace(" ", "") != "상태보기") continue;
            if (button.targetGraphic is Image style && evolutionButton.targetGraphic is Image target)
            {
                target.sprite = style.sprite; target.type = style.type; target.color = style.color;
                var arStyle = arButton.GetComponent<Image>();
                arStyle.sprite = style.sprite; arStyle.type = style.type; arStyle.color = style.color;
            }
            var colors = button.colors;
            colors.disabledColor = Color.white;
            evolutionButton.colors = colors;
            break;
        }

        // Replace the legacy unlabeled sample values in both authority modes.
        {
            var style = status.transform.Find("StatPanel")?.GetComponent<Image>();
            foreach (var name in new[] { "ProfilePanel", "StatPanel", "GrowthPanel" })
            {
                var old = status.transform.Find(name);
                if (old != null) old.gameObject.SetActive(false);
            }
            var card = MakePanel("CommonPetStatus", status.transform, new Vector2(.08f, .20f),
                new Vector2(.92f, .88f), new Color(.11f, .17f, .26f));
            if (style != null) { var target = card.GetComponent<Image>(); target.sprite = style.sprite; target.type = style.type; target.color = style.color; }
            statusText = MakeText("ServerStats", card.transform, "상태 동기화 대기",
                new Vector2(.08f, .07f), new Vector2(.92f, .93f));
            statusText.alignment = TextAlignmentOptions.Left;
            statusText.color = Color.white;
            statusText.lineSpacing = 9;
            statusText.fontSizeMax = 36;
        }

        var canvas = home.GetComponentInParent<Canvas>();
        if (canvas != null)
        {
            arPanel = MakePanel("PetARPanel", canvas.transform, Vector2.zero, Vector2.one, Color.clear);
            var header = MakePanel("ARHeader", arPanel.transform, new Vector2(.02f, .82f),
                new Vector2(.98f, .96f), new Color(.02f, .08f, .18f, .94f));
            var title = MakeText("Title", header.transform, "내 펫 AR", new Vector2(.05f, .1f), new Vector2(.95f, .9f));
            title.color = Color.white; title.fontSizeMax = 42;
            var hint = MakePanel("ARInstructions", arPanel.transform, new Vector2(.12f, .17f),
                new Vector2(.88f, .31f), new Color(.02f, .08f, .18f, .94f));
            arHint = MakeText("Hint", hint.transform, "", new Vector2(.03f, .05f), new Vector2(.97f, .95f));
            arHint.color = Color.white;
            arPanel.SetActive(false);
        }

        if (admin != null && CommonServerConnection.UsesServerAuthority)
            gameObject.AddComponent<MobileAdminMenu>().Configure(manager, admin, canvas, font);
    }

    private void OnEnable()
    {
        if (manager == null) manager = GetComponent<UIManager>();
        if (evolutionButton != null)
        { evolutionButton.onClick.RemoveAllListeners(); evolutionButton.onClick.AddListener(RequestEvolution); }
        if (freshPetButton != null)
        { freshPetButton.onClick.RemoveAllListeners(); freshPetButton.onClick.AddListener(StartFreshPet); }
        var canvas = arPanel == null ? null : arPanel.GetComponentInParent<Canvas>();
        if (canvas != null && manager != null)
            foreach (var button in canvas.GetComponentsInChildren<Button>(true))
                if (button.name == "PetARButton")
                { button.onClick.RemoveAllListeners(); button.onClick.AddListener(manager.ShowAR); }
    }

    private void Update()
    {
        var connection = CommonServerConnection.Instance;
        var state = connection != null && connection.IsConnected ? connection.LatestState : null;
        var evolution = EvolutionClient.Instance;
        bool pending = evolution != null && !string.IsNullOrEmpty(evolution.ActiveRequestId);
        bool available = state != null && state.evolution_target_stage > state.published_model_stage;
        if (evolutionButton != null)
        {
            bool retryModel = evolutionFlow != null && evolutionFlow.NeedsModelRetry;
            bool published = state != null && state.published_model_stage > 0 && evolutionFlow != null && evolutionFlow.IsApplied;
            evolutionButton.interactable = state != null && evolution != null && (available || pending || retryModel || published);
            evolutionLabel.text = state == null ? "진화 · 연결 필요" :
                retryModel ? "진화 외형 다시 받기" :
                pending ? (evolution.HasTerminalError ? "진화 다시 시도" : "진화 확인") :
                available ? "진화하기" : state.published_model_stage >= 3 ? "3차 진화 확인" :
                state.published_model_stage > 0 ? $"{state.published_model_stage}차 진화 확인\n다음 Lv.{(state.published_model_stage + 1) * 10}" : "첫 진화 · Lv.10";
        }
        if (freshPetButton != null)
            freshPetButton.interactable = state != null && connection.EnvironmentName == "test" &&
                !connection.Api.IsBusy && !connection.Api.HasPendingChat && !pending;
        if (statusText != null)
            statusText.text = !CommonServerConnection.UsesServerAuthority ? LocalStatus() : state == null ? "서버 접속 대기" :
                $"<b>{state.settings?.name ?? "헬스몬"} · Lv. {state.level}</b>\n" +
                $"EXP {state.current_exp} / {state.required_exp}    코인 {state.coin}\n\n" +
                $"상체 {state.upper_body:0.#}    하체 {state.lower_body:0.#}\n" +
                $"영양 {state.nutrition:0.#}    에너지 균형 {state.energy_balance:0.#}\n" +
                $"친밀도 {state.affinity:0.#}    활동성 {state.activity:0.#}\n" +
                $"주도성 {state.initiative:0.#}\n\n" +
                $"현재 모습: {(state.published_model_stage == 0 ? "초기형" : state.published_model_stage + "차 진화")}\n" +
                "진화 해금 · Lv. 10 / 20 / 30";
        if (arPanel != null && arPanel.activeSelf)
        {
            bool desktop = Application.isEditor || !Application.isMobilePlatform;
            arHint.text = desktop ? "펫 미리보기\n바닥 소환은 AR 지원 휴대폰에서!" :
                "바닥을 스캔하고 터치!\n현실 세계에 헬스몬 소환";
        }
    }

    public void ShowAR()
    {
        if (arPanel != null) arPanel.SetActive(true);
        FindPlacement()?.SetARMode(true);
    }

    public void HideAR()
    {
        if (arPanel != null) arPanel.SetActive(false);
        FindPlacement()?.SetARMode(false);
    }

    private ARPlacementManager FindPlacement()
    {
        if (placement == null) placement = FindAnyObjectByType<ARPlacementManager>();
        return placement;
    }

    private void RequestEvolution() { evolutionFlow?.Begin(); }
    private string LocalStatus()
    {
        var pet = localPet;
        if (pet == null) return "캐릭터 상태 불러오는 중";
        return $"<b>헬스몬 · Lv. {pet.CurrentLevel}</b>\n\n" +
            $"보유 코인    {pet.CurrentCoin}\n\n" +
            $"친밀도    {pet.CurrentIntimacy} / 100\n\n" +
            $"활동성    {pet.CurrentActivity} / 100\n\n" +
            $"다정함    {pet.CurrentKindness} / 100\n\n" +
            $"호기심    {pet.CurrentCuriosity} / 100";
    }
    private void StartFreshPet()
    {
        CommonServerConnection.Instance?.CreateFreshTestPet();
        manager.ShowHome();
    }

    private GameObject MakePanel(string name, Transform parent, Vector2 min, Vector2 max, Color color)
    {
        var panel = new GameObject(name, typeof(RectTransform), typeof(Image));
        panel.transform.SetParent(parent, false);
        var rect = (RectTransform)panel.transform;
        rect.anchorMin = min; rect.anchorMax = max; rect.offsetMin = rect.offsetMax = Vector2.zero;
        var image = panel.GetComponent<Image>(); image.color = color; image.raycastTarget = false;
        return panel;
    }

    private TMP_Text MakeText(string name, Transform parent, string value, Vector2 min, Vector2 max)
    {
        var label = new GameObject(name, typeof(RectTransform), typeof(TextMeshProUGUI));
        label.transform.SetParent(parent, false);
        var rect = (RectTransform)label.transform;
        rect.anchorMin = min; rect.anchorMax = max; rect.offsetMin = rect.offsetMax = Vector2.zero;
        var text = label.GetComponent<TextMeshProUGUI>();
        text.font = font; text.text = value; text.alignment = TextAlignmentOptions.Center;
        text.color = new Color(.05f, .12f, .22f); text.raycastTarget = false;
        text.enableAutoSizing = true; text.fontSizeMin = 14; text.fontSizeMax = 32;
        return text;
    }

    private Button MakeButton(string name, Transform parent, string value, UnityEngine.Events.UnityAction click,
        Vector2 min, Vector2 max)
    {
        var panel = MakePanel(name, parent, min, max, new Color(.92f, .96f, 1f));
        panel.GetComponent<Image>().raycastTarget = true;
        var button = panel.AddComponent<Button>(); button.onClick.AddListener(click);
        MakeText("Label", panel.transform, value, new Vector2(.04f, .08f), new Vector2(.96f, .92f));
        return button;
    }
}
