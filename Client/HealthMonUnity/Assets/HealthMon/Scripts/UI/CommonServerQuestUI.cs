using System;
using System.Collections.Generic;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Present the server's quest ledger; no local completion or reward mutation.
public sealed class CommonServerQuestUI : MonoBehaviour
{
    private sealed class Row
    {
        public QuestOffer offer;
        public RectTransform rect;
        public TMP_Text label;
        public Button accept, reject;
        public int visibleFrame = -1;
    }
    private readonly List<Row> rows = new List<Row>();
    private RectTransform content, viewport;
    private TMP_Text summary, message;
    private TMP_FontAsset font;
    private QuestList rendered;
    private string renderedScope, lastError;
    private float nextRefresh;
    private bool configured;

    public void Configure()
    {
        font = GetComponentInChildren<TMP_Text>(true)?.font ?? TMP_Settings.defaultFontAsset;
        foreach (var oldName in new[] { "InfoText", "SummaryPanel", "QuestList" })
        {
            var old = transform.Find(oldName);
            if (old != null) old.gameObject.SetActive(false);
        }
        var panel = Rect("ServerQuestPanel", transform, new Vector2(.04f, .17f), new Vector2(.96f, .84f));
        var background = panel.gameObject.AddComponent<Image>();
        background.color = new Color(.05f, .12f, .22f); background.raycastTarget = false;
        summary = Text("Summary", panel, "서버에서 퀘스트를 불러와요.", new Vector2(.03f, .87f), new Vector2(.78f, .98f));
        var reload = Button("RefreshQuests", panel, "새로고침", new Vector2(.80f, .88f), new Vector2(.98f, .98f));
        reload.onClick.AddListener(() => { nextRefresh = 0; lastError = null; });
        message = Text("Notice", panel,
            "완료 보상은 자동 지급돼요. 식사는 아침·점심·저녁 기록만 집계하며, 간식은 기록 EXP에 반영돼요.",
            new Vector2(.03f, .01f), new Vector2(.97f, .16f));
        viewport = Rect("Viewport", panel, new Vector2(.02f, .18f), new Vector2(.98f, .86f));
        viewport.gameObject.AddComponent<Image>().color = Color.clear;
        viewport.gameObject.AddComponent<RectMask2D>();
        var scroll = viewport.gameObject.AddComponent<ScrollRect>();
        scroll.horizontal = false; scroll.movementType = ScrollRect.MovementType.Clamped;
        scroll.scrollSensitivity = 35;
        content = Rect("Content", viewport, new Vector2(0, 1), Vector2.one);
        content.pivot = new Vector2(.5f, 1);
        var layout = content.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.spacing = 12; layout.padding = new RectOffset(8, 8, 8, 8);
        layout.childControlWidth = layout.childControlHeight = true;
        layout.childForceExpandWidth = true; layout.childForceExpandHeight = false;
        var fitter = content.gameObject.AddComponent<ContentSizeFitter>();
        fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        scroll.content = content; scroll.viewport = viewport;
        configured = true;
    }

    private void OnEnable() { nextRefresh = 0; Canvas.willRenderCanvases += ObserveVisibleRows; }
    private void OnDisable()
    {
        Canvas.willRenderCanvases -= ObserveVisibleRows;
        foreach (var row in rows) row.visibleFrame = -1;
    }
    private void Update()
    {
        if (!configured) return;
        var connection = CommonServerConnection.Instance;
        string scope = connection == null || !connection.IsConnected ? null :
            connection.ServerInstanceId + "/" + connection.OwnerId + "/" + connection.Api.PetId;
        var list = scope == null ? null : connection.LatestQuests;
        if (renderedScope != scope || rendered != list) Rebuild(list, scope);
        if (scope == null) { summary.text = "서버에 연결하면 퀘스트를 불러와요."; return; }
        if (Time.unscaledTime >= nextRefresh && !connection.Api.IsBusy)
        {
            nextRefresh = Time.unscaledTime + 15;
            connection.RefreshState(); connection.RefreshQuests();
        }
        int complete = 0;
        foreach (var row in rows)
        {
            var offer = row.offer;
            if (offer.status == "completed") complete++;
            bool pending = offer.IsPendingProposal || (!offer.is_proposal && offer.status == "offered");
            bool failed = pending && connection.QuestDisplayFailed(offer);
            row.accept.gameObject.SetActive(pending); row.reject.gameObject.SetActive(pending);
            row.accept.GetComponentInChildren<TMP_Text>().text = failed ? "표시 확인 재시도" : "수락";
            bool idle = !connection.Api.IsBusy && !connection.Api.HasPendingChat;
            row.accept.interactable = idle && (failed || !offer.is_proposal || connection.QuestDisplayAcknowledged(offer));
            row.reject.interactable = idle && (!offer.is_proposal || connection.QuestDisplayAcknowledged(offer));
        }
        summary.text = list == null ? "퀘스트를 불러오는 중…" : $"서버 퀘스트 {rows.Count}개 · 완료 {complete}개 · 완료 보상 자동 지급";
        message.text = lastError ?? (list != null && rows.Count == 0 ? "현재 진행할 퀘스트가 없어요. 잠시 후 새로고침해 주세요." :
            "식사는 아침·점심·저녁 기록만 집계해요. 간식은 기록 EXP에 반영돼요. 목록을 위아래로 스크롤할 수 있어요.");
    }

    private void Rebuild(QuestList list, string scope)
    {
        foreach (var row in rows) Destroy(row.rect.gameObject);
        rows.Clear(); rendered = list; renderedScope = scope; lastError = null;
        var connection = CommonServerConnection.Instance;
        foreach (var offer in list?.offers ?? Array.Empty<QuestOffer>())
        {
            if (offer == null || offer.pet_id != connection.Api.PetId || offer.excluded || !string.IsNullOrEmpty(offer.cancelled_at)) continue;
            // The server owns KST day/week boundaries. Historical rows remain in
            // its ledger, but do not appear as today's unfinished quests.
            if (!offer.is_proposal && !string.IsNullOrEmpty(list.current_day) &&
                offer.period_start != (offer.slot == "weekly" ? list.current_week_start : list.current_day)) continue;
            var card = Rect("Quest-" + offer.id, content, Vector2.zero, Vector2.one);
            var background = card.gameObject.AddComponent<Image>(); background.color = new Color(.12f, .23f, .35f);
            card.gameObject.AddComponent<LayoutElement>().preferredHeight = 150;
            var label = Text("QuestDetails", card, Description(offer), new Vector2(.03f, .05f), new Vector2(.74f, .95f));
            label.alignment = TextAlignmentOptions.Left;
            var row = new Row { offer = offer, rect = card, label = label };
            row.accept = Button("Accept", card, "수락", new Vector2(.77f, .53f), new Vector2(.98f, .92f));
            row.reject = Button("Reject", card, "거절", new Vector2(.77f, .08f), new Vector2(.98f, .47f));
            row.accept.onClick.AddListener(() => Decide(row, true));
            row.reject.onClick.AddListener(() => Decide(row, false));
            rows.Add(row);
        }
    }
    private void Decide(Row row, bool accept)
    {
        var connection = CommonServerConnection.Instance;
        if (connection == null || row.offer.pet_id != connection.Api.PetId) return;
        if (connection.QuestDisplayFailed(row.offer)) { connection.RetryQuestDisplay(row.offer); return; }
        connection.DecideDisplayedQuest(row.offer, accept, error =>
        { lastError = "퀘스트를 변경하지 못했어요. 연결을 확인하고 다시 시도해 주세요. (" + error.StatusCode + ")"; });
    }

    // A fetched proposal does not count as shown. Its entire row must be visible
    // inside the scroll viewport over a rendered frame before acknowledgement.
    private void ObserveVisibleRows()
    {
        if (!configured || !isActiveAndEnabled) return;
        var connection = CommonServerConnection.Instance;
        if (connection == null || !connection.IsConnected) return;
        var canvas = GetComponentInParent<Canvas>();
        var camera = canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
        var corners = new Vector3[4];
        foreach (var row in rows)
        {
            if (!row.offer.IsPendingProposal) continue;
            row.rect.GetWorldCorners(corners);
            bool visible = true;
            foreach (var corner in corners)
                visible &= RectTransformUtility.RectangleContainsScreenPoint(viewport,
                    RectTransformUtility.WorldToScreenPoint(camera, corner), camera);
            if (!visible) { row.visibleFrame = -1; continue; }
            if (row.visibleFrame >= 0 && Time.frameCount > row.visibleFrame) connection.ObserveDisplayedQuest(row.offer);
            else if (row.visibleFrame < 0) row.visibleFrame = Time.frameCount;
        }
    }

    private static string Description(QuestOffer offer)
    {
        var t = offer.template;
        string title;
        switch (t?.candidate)
        {
            case "meal1": title = "식사 1회 기록"; break;
            case "meal2": title = "식사 2회 기록"; break;
            case "workout1": title = "운동 1회 기록"; break;
            case "workout70": title = "운동 목표 70% 이상 달성"; break;
            case "meal_workout": title = "식사와 운동 각각 기록"; break;
            case "chat1": title = "헬스몬과 대화하기"; break;
            case "workout_days3": title = "이번 주 3일 운동"; break;
            case "meal_days5": title = "이번 주 5일 식사 기록"; break;
            case "daily6": title = "이번 주 일일 퀘스트 6개 완료"; break;
            default: title = t?.kind ?? "헬스몬의 제안"; break;
        }
        string status = offer.status == "completed" ? "완료 · 보상 반영됨" :
            offer.status == "rejected" ? "거절함" : offer.status == "expired" ? "기간 종료" :
            offer.IsPendingProposal ? "새 제안" : "진행 중";
        string category = offer.is_proposal ? "헬스몬의 제안" : offer.slot == "weekly" ? "주간" : "일일";
        string reward = !offer.is_proposal && t != null ? $"  EXP +{t.exp} · 코인 +{t.coin}" : "";
        return $"<b>{category} · {title}</b>\n진행도  {offer.progress:0.#} / {t?.target:0.#}  ·  {status}\n{offer.period_start}{reward}";
    }
    private RectTransform Rect(string name, Transform parent, Vector2 min, Vector2 max)
    {
        var rect = new GameObject(name, typeof(RectTransform)).GetComponent<RectTransform>();
        rect.SetParent(parent, false); rect.anchorMin = min; rect.anchorMax = max;
        rect.offsetMin = rect.offsetMax = Vector2.zero; return rect;
    }
    private TMP_Text Text(string name, Transform parent, string value, Vector2 min, Vector2 max)
    {
        var rect = Rect(name, parent, min, max); var text = rect.gameObject.AddComponent<TextMeshProUGUI>();
        text.font = font; text.text = value; text.fontSizeMin = 18; text.fontSizeMax = 30;
        text.enableAutoSizing = true; text.alignment = TextAlignmentOptions.Center;
        text.color = Color.white; text.raycastTarget = false; return text;
    }
    private Button Button(string name, Transform parent, string title, Vector2 min, Vector2 max)
    {
        var rect = Rect(name, parent, min, max); rect.gameObject.AddComponent<Image>().color = new Color(.15f, .55f, .75f);
        var button = rect.gameObject.AddComponent<Button>();
        Text("Label", rect, title, new Vector2(.03f, .05f), new Vector2(.97f, .95f)); return button;
    }
}
