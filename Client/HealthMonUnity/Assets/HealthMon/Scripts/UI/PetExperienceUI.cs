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

    public void Configure(UIManager owner, GameObject home, GameObject status, GameObject admin)
    {
        manager = owner;
        var reference = home.GetComponentInChildren<TMP_Text>(true);
        font = reference != null ? reference.font : TMP_Settings.defaultFontAsset;
        evolutionButton = MakeButton("HomeEvolutionButton", home.transform, "진화", RequestEvolution,
            new Vector2(.82f, .36f), new Vector2(.97f, .45f));
        evolutionLabel = evolutionButton.GetComponentInChildren<TMP_Text>();

        if (CommonServerConnection.UsesServerAuthority)
        {
            foreach (var name in new[] { "ProfilePanel", "StatPanel", "GrowthPanel" })
            {
                var old = status.transform.Find(name);
                if (old != null) old.gameObject.SetActive(false);
            }
            var card = MakePanel("CommonPetStatus", status.transform, new Vector2(.22f, .20f),
                new Vector2(.78f, .82f), new Color(.11f, .17f, .26f));
            statusText = MakeText("ServerStats", card.transform, "서버에 연결하면 상태를 불러와요.",
                new Vector2(.05f, .04f), new Vector2(.95f, .96f));
            statusText.alignment = TextAlignmentOptions.Left;
            statusText.color = Color.white;
            statusText.lineSpacing = 9;
            statusText.fontSizeMax = 42;
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
            foreach (var nav in canvas.GetComponentsInChildren<HorizontalLayoutGroup>(true))
            {
                if (nav.name != "BottomNav") continue;
                var arButton = MakeButton("PetARButton", nav.transform, "펫 AR", manager.ShowAR, Vector2.zero, Vector2.one);
                arButton.transform.SetSiblingIndex(2);
                var layout = arButton.gameObject.AddComponent<LayoutElement>();
                layout.flexibleWidth = 1;
                break;
            }
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
            evolutionButton.interactable = available && evolution != null && (!pending || !string.IsNullOrEmpty(evolution.LastError));
            evolutionLabel.text = state == null ? "진화 · 연결 필요" :
                pending ? (string.IsNullOrEmpty(evolution.LastError) ? "진화 진행 중" : "진화 다시 시도") :
                available ? "진화하기" : state.published_model_stage >= 3 ? "3차 진화 완료" :
                state.published_model_stage > 0 ? $"{state.published_model_stage}차 진화 완료 · 다음 Lv.{(state.published_model_stage + 1) * 10}" : "첫 진화 · Lv.10";
        }
        if (freshPetButton != null)
            freshPetButton.interactable = state != null && connection.EnvironmentName == "test" &&
                !connection.Api.IsBusy && !connection.Api.HasPendingChat && !pending;
        if (statusText != null)
            statusText.text = state == null ? "서버에 연결하면 상태를 불러와요." :
                $"<b>{state.settings?.name ?? "헬스몬"} · Lv. {state.level}</b>\n" +
                $"EXP {state.current_exp} / {state.required_exp}    코인 {state.coin}\n\n" +
                $"상체 {state.upper_body:0.#}    하체 {state.lower_body:0.#}\n" +
                $"영양 {state.nutrition:0.#}    에너지 균형 {state.energy_balance:0.#}\n" +
                $"친밀도 {state.affinity:0.#}    활동성 {state.activity:0.#}\n" +
                $"주도성 {state.initiative:0.#}\n\n" +
                $"현재 모습: {(state.published_model_stage == 0 ? "초기형" : state.published_model_stage + "차 진화")}\n" +
                "Lv. 10 · 20 · 30에 다음 진화가 열려요.";
        if (arPanel != null && arPanel.activeSelf)
        {
            bool desktop = Application.isEditor || !Application.isMobilePlatform;
            arHint.text = state == null ? "서버에 연결하면 내 펫을 불러와요." : desktop ?
                "PC에서는 펫 미리보기를 표시해요. 실제 바닥 배치는 AR을 지원하는 휴대폰에서 사용할 수 있어요." :
                "휴대폰으로 바닥을 비추고, 인식된 바닥을 터치해 펫을 배치하세요.";
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

    private void RequestEvolution() { EvolutionClient.Instance?.RequestCommonEvolution(); }
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
