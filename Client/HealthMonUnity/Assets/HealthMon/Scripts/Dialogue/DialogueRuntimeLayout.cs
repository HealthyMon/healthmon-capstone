using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Runtime-only repair of the existing dialogue controls. No scene/prefab asset
// is saved, and the original text references, fonts, materials and colours stay.
public sealed class DialogueRuntimeLayout : MonoBehaviour
{
    public RectTransform Panel { get; private set; }
    public RectTransform UserBubble { get; private set; }
    public RectTransform ResponseBubble { get; private set; }
    public RectTransform InputArea { get; private set; }
    public RectTransform BottomNavigation { get; private set; }
    public ScrollRect UserScroll { get; private set; }
    public ScrollRect ResponseScroll { get; private set; }
    public bool HasValidLayout { get; private set; }
    private TMP_InputField input;
    private TMP_Text user, response;
    private RectTransform send, header;
    private string lastUser, lastResponse;
    private Vector2 lastPanelSize;
    private int lastScreenWidth, lastScreenHeight;
    private bool configured;
    private float userMaximumWidth = 650, responseMaximumWidth = 760;

    public void Configure(TMP_InputField field, TMP_Text userText, TMP_Text responseText, Button sendButton)
    {
        if (field == null || userText == null || responseText == null || sendButton == null) return;
        input = field; user = userText; response = responseText; send = (RectTransform)sendButton.transform;
        Panel = FindPanel(field.transform);
        if (Panel == null || FindPanel(userText.transform) != Panel || FindPanel(responseText.transform) != Panel) return;
        InputArea = field.transform.parent as RectTransform;
        header = Panel.Find("Header") as RectTransform;
        BottomNavigation = Panel.parent?.Find("BottomNav") as RectTransform;
        if (InputArea == null || BottomNavigation == null) return;
        UserBubble = BubbleOf(userText); ResponseBubble = BubbleOf(responseText);
        if (!configured)
        {
            if (UserBubble.rect.width > 0) userMaximumWidth = UserBubble.rect.width;
            if (ResponseBubble.rect.width > 0) responseMaximumWidth = ResponseBubble.rect.width;
        }
        UserScroll = EnsureScroll(UserBubble, userText, new Vector2(25, 20));
        ResponseScroll = EnsureScroll(ResponseBubble, responseText, new Vector2(30, 30));
        configured = true;
        ApplyNow();
    }

    private static RectTransform FindPanel(Transform child)
    {
        for (var at = child; at != null; at = at.parent)
            if (at.name == "DialoguePanel") return at as RectTransform;
        return null;
    }
    private static RectTransform BubbleOf(TMP_Text text)
    {
        var parent = text.transform.parent;
        if (parent.name == "RuntimeDialogueViewport") parent = parent.parent;
        return parent as RectTransform;
    }
    private static ScrollRect EnsureScroll(RectTransform bubble, TMP_Text text, Vector2 padding)
    {
        var viewport = bubble.Find("RuntimeDialogueViewport") as RectTransform;
        if (viewport == null)
        {
            viewport = (RectTransform)new GameObject("RuntimeDialogueViewport", typeof(RectTransform), typeof(RectMask2D)).transform;
            viewport.SetParent(bubble, false);
        }
        viewport.anchorMin = Vector2.zero; viewport.anchorMax = Vector2.one;
        viewport.offsetMin = padding; viewport.offsetMax = -padding;
        text.rectTransform.SetParent(viewport, false);
        text.rectTransform.anchorMin = new Vector2(0, 1); text.rectTransform.anchorMax = Vector2.one;
        text.rectTransform.pivot = new Vector2(.5f, 1);
        text.enableWordWrapping = true;
        text.verticalAlignment = VerticalAlignmentOptions.Top;
        text.overflowMode = TextOverflowModes.Overflow; // RectMask2D clips only the viewport; content remains scrollable.
        var scroll = bubble.GetComponent<ScrollRect>() ?? bubble.gameObject.AddComponent<ScrollRect>();
        scroll.viewport = viewport; scroll.content = text.rectTransform;
        scroll.horizontal = false; scroll.vertical = true;
        scroll.movementType = ScrollRect.MovementType.Clamped;
        scroll.scrollSensitivity = 36;
        return scroll;
    }

    private void LateUpdate()
    {
        if (!configured || Panel == null || !Panel.gameObject.activeInHierarchy) return;
        if (lastUser != user.text || lastResponse != response.text || lastPanelSize != Panel.rect.size ||
            lastScreenWidth != Screen.width || lastScreenHeight != Screen.height) ApplyNow();
    }

    public void ApplyNow()
    {
        if (!configured || Panel == null || !Panel.gameObject.activeInHierarchy) return;
        Canvas.ForceUpdateCanvases();
        Rect panel = Panel.rect;
        Rect nav = BoundsInPanel(BottomNavigation);
        float top = header == null ? panel.height - 100 : BoundsInPanel(header).yMin - panel.yMin;
        float margin = (float)Math.Min(30, panel.width * .04f);
        float userWidth = (float)Math.Min(userMaximumWidth, panel.width - 2 * margin);
        float responseWidth = (float)Math.Min(responseMaximumWidth, panel.width - 2 * margin);
        float preferredUser = user.GetPreferredValues(user.text, Math.Max(1, userWidth - 50), float.PositiveInfinity).y + 42;
        float preferredResponse = response.GetPreferredValues(response.text, Math.Max(1, responseWidth - 60), float.PositiveInfinity).y + 62;
        var plan = DialogueLayoutPlan.Calculate(panel.width, panel.height, nav.yMax - panel.yMin, top,
            userWidth, responseWidth, preferredUser, preferredResponse);
        HasValidLayout = plan.Valid;
        if (!plan.Valid) return;
        bool userChanged = lastUser != user.text, responseChanged = lastResponse != response.text;
        Place(InputArea, plan.Input); Place(UserBubble, plan.User); Place(ResponseBubble, plan.Response);
        bool portrait = panel.height > panel.width;
        float sendWidth = (float)Math.Min(portrait ? 230 : 170, plan.Input.width * .25f);
        float controlHeight = (float)Math.Max(1, plan.Input.height - (portrait ? 32 : 40));
        var sendBounds = new Rect(plan.Input.xMax - 20 - sendWidth, plan.Input.y + 20, sendWidth, controlHeight);
        var inputBounds = new Rect(plan.Input.x + 20, plan.Input.y + 20,
            (float)Math.Max(1, sendBounds.xMin - 20 - (plan.Input.x + 20)), controlHeight);
        Place(send, sendBounds); Place(input.GetComponent<RectTransform>(), inputBounds);
        Canvas.ForceUpdateCanvases();
        SizeContent(UserScroll, user, userChanged); SizeContent(ResponseScroll, response, responseChanged);
        lastUser = user.text; lastResponse = response.text; lastPanelSize = panel.size;
        lastScreenWidth = Screen.width; lastScreenHeight = Screen.height;
    }

    private static void SizeContent(ScrollRect scroll, TMP_Text text, bool changed)
    {
        float position = changed ? 1 : scroll.verticalNormalizedPosition;
        float height = text.GetPreferredValues(text.text, Math.Max(1, scroll.viewport.rect.width), float.PositiveInfinity).y + 2;
        text.rectTransform.sizeDelta = new Vector2(0, (float)Math.Max(scroll.viewport.rect.height, height));
        text.rectTransform.anchoredPosition = Vector2.zero;
        text.ForceMeshUpdate();
        Canvas.ForceUpdateCanvases();
        scroll.StopMovement(); scroll.verticalNormalizedPosition = position;
    }

    private void Place(RectTransform target, Rect bounds)
    {
        // Plan coordinates start at the panel's lower left. Transform them into
        // each existing parent, including the original CharacterArea hierarchy.
        var parent = (RectTransform)target.parent;
        Vector3 min = parent.InverseTransformPoint(Panel.TransformPoint(Panel.rect.min + bounds.min));
        Vector3 max = parent.InverseTransformPoint(Panel.TransformPoint(Panel.rect.min + bounds.max));
        target.anchorMin = target.anchorMax = target.pivot = Vector2.zero;
        target.anchoredPosition = (Vector2)min - parent.rect.min;
        target.sizeDelta = (Vector2)(max - min);
    }

    public Rect BoundsInPanel(RectTransform target)
    {
        var corners = new Vector3[4]; target.GetWorldCorners(corners);
        Vector2 min = new Vector2(float.PositiveInfinity, float.PositiveInfinity), max = -min;
        foreach (var corner in corners)
        {
            Vector2 point = Panel.InverseTransformPoint(corner);
            min = Vector2.Min(min, point); max = Vector2.Max(max, point);
        }
        return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
    }
}

// Pure geometry, exercised without a native runtime for portrait/landscape and
// very long text. Runtime verification additionally checks transformed bounds.
public sealed class DialogueLayoutPlan
{
    public bool Valid;
    public Rect User, Response, Input;
    public static DialogueLayoutPlan Calculate(float width, float height, float navTop, float headerBottom,
        float userWidth, float responseWidth, float userPreferredHeight, float responsePreferredHeight)
    {
        var plan = new DialogueLayoutPlan();
        if (height > width)
        {
            float marginPortrait = Math.Min(40, width * .04f), gapPortrait = 28;
            plan.Input = new Rect(marginPortrait, Math.Max(0, navTop + 40), width - 2 * marginPortrait, 180);
            float availablePortrait = Math.Min(height * .34f, headerBottom - plan.Input.yMax - 3 * gapPortrait);
            if (width <= 0 || availablePortrait < 100) return plan;
            float userHeightPortrait = Math.Min(Math.Max(112, userPreferredHeight), availablePortrait * .35f);
            float responseHeightPortrait = Math.Min(Math.Max(155, responsePreferredHeight), availablePortrait - userHeightPortrait - gapPortrait);
            userWidth = Math.Min(width * .78f, width - 2 * marginPortrait);
            responseWidth = width - 2 * marginPortrait;
            plan.User = new Rect(width - marginPortrait - userWidth, plan.Input.yMax + gapPortrait, userWidth, userHeightPortrait);
            plan.Response = new Rect(marginPortrait, plan.User.yMax + gapPortrait, responseWidth, responseHeightPortrait);
            plan.Valid = plan.Input.width > 0 && responseHeightPortrait > 0 && plan.Response.yMax < headerBottom;
            return plan;
        }
        float gap = 16, margin = (float)Math.Min(30, width * .04f);
        float inputHeight = (float)Math.Min(130, Math.Max(48, height * .15f));
        plan.Input = new Rect(margin, (float)Math.Max(0, navTop + gap), width - 2 * margin, inputHeight);
        float bottom = plan.Input.yMax + gap, available = (float)Math.Min(height, headerBottom) - gap - bottom;
        if (width <= 0 || available <= gap + 2 || userWidth <= 50 || responseWidth <= 60) return plan;
        float userHeight = (float)Math.Min(Math.Max(1, userPreferredHeight), (available - gap) * .4f);
        float responseHeight = (float)Math.Min(Math.Max(1, responsePreferredHeight), available - gap - userHeight);
        plan.Response = new Rect((width - responseWidth) / 2, bottom, responseWidth, responseHeight);
        plan.User = new Rect(width - margin - userWidth, plan.Response.yMax + gap, userWidth, userHeight);
        plan.Valid = plan.Input.width > 0 && userHeight > 0 && responseHeight > 0 && plan.User.yMax <= height;
        return plan;
    }
}
