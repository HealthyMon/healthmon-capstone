using System;
using System.Globalization;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>Character-free status screen. All displayed values come from the current pet.</summary>
[DisallowMultipleComponent]
public sealed class HealthMonStatusView : MonoBehaviour
{
    private static readonly Color White = new Color(.94f, .98f, 1);
    private static readonly Color Cyan = new Color(.29f, .88f, 1);
    private static readonly Color Gold = new Color(1, .84f, .18f);
    private static readonly Color Muted = new Color(.65f, .85f, .94f);
    private static readonly Color Edge = new Color(.17f, .62f, .81f, .9f);
    private RectTransform safeArea, frame, life, battle, growth, confirm, chart;
    private RectTransform experienceFill, energyMarker, energyFill, hpFill, stFill;
    private TMP_FontAsset font;
    private TMP_Text nameLabel, levelLabel, experienceLabel, bodyLabel, energyLabel, growthLabel, connectionLabel;
    private TMP_Text hpLabel, stLabel, speedLabel, recoveryLabel;
    private readonly TMP_Text[] axisValues = new TMP_Text[6];
    private readonly RectTransform[] axisGroups = new RectTransform[6];
    private readonly TMP_Text[] combatValues = new TMP_Text[5];
    private HealthMonRadarGraphic radar;
    private PetStateManager localPet;
    private float nextRefresh;
    private Vector2 lastAvailable;
    private Rect lastSafe;
    private bool built;
    public HealthMonStatusSnapshot CurrentSnapshot { get; private set; }

    public void Configure(TMP_FontAsset sourceFont, Action close)
    {
        if (built) return;
        font = sourceFont != null ? sourceFont : TMP_Settings.defaultFontAsset;
        // The old static home atlas contains only the characters used by that screen.
        // Reuse the scene's existing dynamic Korean font for new labels and player names.
        if (font == null || font.atlasPopulationMode == AtlasPopulationMode.Static)
            foreach (var label in transform.root.GetComponentsInChildren<TMP_Text>(true))
            {
                var candidate = label.font;
                if (candidate == null || candidate.atlasPopulationMode == AtlasPopulationMode.Static ||
                    !candidate.HasCharacter('헬', true, true)) continue;
                font = candidate;
                break;
            }
        foreach (Transform old in transform) old.gameObject.SetActive(false);
        if (TryGetComponent<Image>(out var previousBackground)) previousBackground.enabled = false;
        var rect = (RectTransform)transform;
        rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one;
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        // The existing navigation is a sibling; the status screen is a complete modal page.
        var parentCanvas = GetComponentInParent<Canvas>();
        var overlay = gameObject.GetComponent<Canvas>();
        if (overlay == null) overlay = gameObject.AddComponent<Canvas>();
        overlay.overrideSorting = true;
        overlay.sortingOrder = (parentCanvas != null ? parentCanvas.sortingOrder : 0) + 20;
        if (GetComponent<GraphicRaycaster>() == null) gameObject.AddComponent<GraphicRaycaster>();

        var background = Panel("StatusBackdrop", transform, new Color(.13f, .34f, .79f), new Color(.02f, .12f, .12f), Color.clear, 0);
        Stretch(background.rectTransform);
        background.raycastTarget = true;
        safeArea = Rect("SafeArea", transform);
        frame = Rect("StatusContent", safeArea);
        frame.anchorMin = frame.anchorMax = frame.pivot = new Vector2(.5f, .5f);

        var back = Button("Back", frame, "‹", close, false);
        Place(back, 16, 0, 88, 88);
        Text("Title", frame, "헬스몬 상태", 124, 0, 472, 88, 34, White, TextAlignmentOptions.Center);

        var profile = Card("Profile", frame, 24, 100, 672, 112);
        nameLabel = Text("PetName", profile, "", 24, 14, 268, 39, 31, White);
        nameLabel.richText = false;
        levelLabel = Text("Level", profile, "", 298, 14, 120, 39, 27, Cyan);
        var body = Panel("BodyType", profile, new Color(.02f, .36f, .52f), new Color(.02f, .27f, .43f), Edge, 18);
        Place(body.rectTransform, 438, 17, 212, 36);
        bodyLabel = Text("BodyTypeLabel", body.transform, "", 10, 0, 192, 36, 21, Cyan, TextAlignmentOptions.Center);
        Text("ExpCaption", profile, "EXP", 24, 70, 64, 28, 22, Muted);
        var expTrack = Track("ExperienceTrack", profile, 91, 77, 384, 15);
        experienceFill = Fill("ExperienceFill", expTrack, Gold, new Color(1, .68f, .10f));
        experienceLabel = Text("Experience", profile, "", 484, 69, 164, 30, 22, White, TextAlignmentOptions.Right);

        life = Card("Lifestyle", frame, 24, 234, 672, 512);
        SectionTitle(life, "생활 스탯");
        chart = Rect("LifestyleRadar", life);
        radar = chart.gameObject.AddComponent<HealthMonRadarGraphic>(); radar.raycastTarget = false;
        for (int i = 0; i < 6; i++)
        {
            axisGroups[i] = Rect("Axis" + i, life);
            Text("Caption", axisGroups[i], HealthMonStatusSnapshot.AxisNames[i], 0, 0, 116, 24, 22, Muted, TextAlignmentOptions.Center);
            axisValues[i] = Text("Value", axisGroups[i], "—", 0, 24, 116, 24, 25, Gold, TextAlignmentOptions.Center);
        }
        var energy = Rect("Energy", life);
        energy.anchorMin = energy.anchorMax = energy.pivot = new Vector2(0, 0);
        energy.anchoredPosition = new Vector2(24, 8); energy.sizeDelta = new Vector2(624, 100);
        var separator = Panel("Divider", energy, Edge, Edge, Color.clear, 0); Place(separator.rectTransform, 0, 0, 624, 1);
        Text("EnergyCaption", energy, "에너지 균형", 4, 10, 280, 30, 22, Cyan);
        energyLabel = Text("EnergyValue", energy, "—", 482, 10, 136, 30, 23, Gold, TextAlignmentOptions.Right);
        var energyTrack = Track("EnergyTrack", energy, 16, 53, 592, 12);
        energyFill = Fill("EnergyDelta", energyTrack, Gold, new Color(1, .65f, .12f));
        var zero = Panel("ZeroTick", energyTrack, Muted, Muted, Color.clear, 0);
        zero.rectTransform.anchorMin = zero.rectTransform.anchorMax = new Vector2(.5f, .5f);
        zero.rectTransform.sizeDelta = new Vector2(2, 24); zero.rectTransform.anchoredPosition = Vector2.zero;
        var marker = Panel("EnergyMarker", energyTrack, new Color(1, .96f, .55f), Gold, White, 3);
        energyMarker = marker.rectTransform;
        energyMarker.anchorMin = energyMarker.anchorMax = energyMarker.pivot = new Vector2(.5f, .5f);
        energyMarker.sizeDelta = new Vector2(12, 26); energyMarker.anchoredPosition = Vector2.zero;
        Text("EnergyLow", energy, "-100", 16, 72, 100, 22, 18, Muted);
        Text("EnergyZero", energy, "0", 262, 72, 100, 22, 18, Muted, TextAlignmentOptions.Center);
        Text("EnergyHigh", energy, "+100", 508, 72, 100, 22, 18, Muted, TextAlignmentOptions.Right);

        battle = Card("Combat", frame, 24, 766, 672, 282);
        SectionTitle(battle, "전투 스탯");
        hpLabel = Resource(battle, "HP", "최대 HP", 28, new Color(.11f, .86f, .48f), new Color(.70f, .95f, .31f), out hpFill);
        stLabel = Resource(battle, "ST", "최대 ST", 88, new Color(.14f, .72f, .94f), new Color(.59f, .96f, 1), out stFill);
        string[] combatNames = { "공격", "방어", "저항", "속도", "행운" };
        for (int i = 0; i < 5; i++)
        {
            var slot = Panel("Combat" + i, battle, new Color(.025f, .12f, .25f), new Color(.015f, .08f, .18f), Edge, 17);
            Place(slot.rectTransform, 24 + i * 126, 152, 120, 76);
            Text("Caption", slot.transform, combatNames[i], 8, 8, 104, 25, 21, i == 0 ? Gold : Cyan, TextAlignmentOptions.Center);
            combatValues[i] = Text("Value", slot.transform, "—", 8, 34, 104, 33, 28, White, TextAlignmentOptions.Center);
        }
        speedLabel = Text("ActionSpeed", battle, "", 24, 238, 305, 30, 21, Muted, TextAlignmentOptions.Center);
        recoveryLabel = Text("StaminaRecovery", battle, "", 343, 238, 305, 30, 21, Gold, TextAlignmentOptions.Center);
        growth = Card("Evolution", frame, 24, 1064, 672, 62);
        growthLabel = Text("EvolutionLabel", growth, "", 20, 4, 632, 54, 25, White, TextAlignmentOptions.Center);
        confirm = Button("Confirm", frame, "확인", close, true); Place(confirm, 24, 1144, 672, 88);
        connectionLabel = Text("ConnectionState", frame, "", 24, 1238, 672, 28, 18, Muted, TextAlignmentOptions.Center);
        built = true;
        ApplyLayout(true);
        RefreshNow();
    }

    private void OnEnable() { if (built) { ApplyLayout(true); RefreshNow(); } }
    private void Update()
    {
        if (!built) return;
        ApplyLayout(false);
        if (Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + .2f;
        RefreshNow();
    }

    public void RefreshNow()
    {
        if (!built) return;
        HealthMonStatusSnapshot snapshot = null;
        if (CommonServerConnection.UsesServerAuthority)
        {
            var c = CommonServerConnection.Instance;
            if (c?.Api != null) snapshot = HealthMonStatusSnapshot.FromServer(c.LatestState, c.Api.PetId, c.IsConnected);
        }
        else
        {
            if (localPet == null) localPet = FindAnyObjectByType<PetStateManager>(FindObjectsInactive.Include);
            if (localPet != null)
            {
                var rules = HealthMonGameRules.Instance;
                string selected = rules != null && !string.IsNullOrEmpty(rules.CharacterId) ? rules.CharacterId :
                    PlayerPrefs.GetString("HealthMon_Roster_Selected_v1", "pet_starter");
                var p = rules != null ? rules.ForId(selected) : null;
                // Offline combat uses neutral nutrition/energy until that mode owns these scores.
                snapshot = HealthMonStatusSnapshot.Create(localPet.CurrentName, selected, localPet.CurrentLevel,
                    localPet.CurrentExperience, localPet.RequiredExperience, p?.upperBody ?? 50, p?.lowerBody ?? 50,
                    50, 0, localPet.CurrentActivity, localPet.CurrentIntimacy, p?.initiative ?? localPet.CurrentCuriosity);
                snapshot.Evolution = "성장 단계 · " + localPet.CurrentGrowthStage;
            }
        }
        Present(snapshot);
    }

    public void Present(HealthMonStatusSnapshot s)
    {
        CurrentSnapshot = s;
        Set(nameLabel, s?.Name ?? "헬스몬");
        Set(levelLabel, s == null ? "Lv.—" : "Lv." + s.Level);
        Set(bodyLabel, s == null ? "상태 확인 중" : s.Combat.BodyName);
        Set(experienceLabel, s == null ? "— / —" : s.Level >= 30 ? "MAX" : s.Experience + " / " + s.RequiredExperience);
        SetFill(experienceFill, 0, s?.ExperienceFraction ?? 0);
        radar.SetValues(s?.Axes);
        for (int i = 0; i < 6; i++) Set(axisValues[i], s == null ? "—" : HealthMonStatusSnapshot.Number(s.Axes[i]));
        Set(energyLabel, s?.EnergyText ?? "—");
        float energy = HealthMonStatusSnapshot.EnergyFraction(s?.Energy ?? 0);
        energyMarker.gameObject.SetActive(s != null);
        energyMarker.anchorMin = energyMarker.anchorMax = new Vector2(Mathf.Lerp(.012f, .988f, energy), .5f);
        SetFill(energyFill, Mathf.Min(.5f, energy), Mathf.Max(.5f, energy));
        Set(hpLabel, s == null ? "—" : s.Combat.MaxHP.ToString(CultureInfo.InvariantCulture));
        Set(stLabel, s == null ? "—" : HealthMonStatusSnapshot.Number(s.Combat.MaxST));
        hpFill.gameObject.SetActive(s != null); stFill.gameObject.SetActive(s != null);
        int[] stats = s == null ? null : new[] { s.Combat.ATK, s.Combat.DEF, s.Combat.RES, s.Combat.SPD, s.Combat.LUK };
        for (int i = 0; i < 5; i++) Set(combatValues[i], stats == null ? "—" : stats[i].ToString(CultureInfo.InvariantCulture));
        Set(speedLabel, "행동 속도  " + (s == null ? "—" : "×" + s.Combat.ActionSpeedMultiplier.ToString("0.00", CultureInfo.InvariantCulture)));
        Set(recoveryLabel, "ST 회복  " + (s == null ? "—" : "×" + s.Combat.StaminaRecoveryMultiplier.ToString("0.00", CultureInfo.InvariantCulture)));
        Set(growthLabel, s?.Evolution ?? "상태 불러오는 중");
        Set(connectionLabel, s == null ? "연결 대기" : s.IsCached ? "연결 재시도 중 · 마지막 기록" : "");
    }

    public string AxisText(int index) => axisValues[index].text;
    public string EnergyText => energyLabel.text;
    public string CombatText(int index) => combatValues[index].text;

    private void ApplyLayout(bool force)
    {
        var bounds = ((RectTransform)transform).rect;
        var available = new Vector2(bounds.width, bounds.height);
        var safe = Screen.safeArea;
        if (!force && available == lastAvailable && safe == lastSafe) return;
        lastAvailable = available; lastSafe = safe;
        if (available.x <= 0 || available.y <= 0 || Screen.width <= 0 || Screen.height <= 0) return;
        ApplyViewport(available, new Rect(safe.x / Screen.width, safe.y / Screen.height, safe.width / Screen.width, safe.height / Screen.height));
    }

    private void ApplyViewport(Vector2 available, Rect normalizedSafe)
    {
        safeArea.anchorMin = normalizedSafe.min;
        safeArea.anchorMax = normalizedSafe.max;
        safeArea.offsetMin = safeArea.offsetMax = Vector2.zero;
        float width = available.x * normalizedSafe.width, height = available.y * normalizedSafe.height;
        float scale = Mathf.Min(width / 720, height / 1280);
        if (scale <= 0) return;
        float extra = Mathf.Max(0, height / scale - 1280);
        frame.sizeDelta = new Vector2(720, 1280 + extra); frame.localScale = Vector3.one * scale;
        frame.anchoredPosition = Vector2.zero;
        Place(life, 24, 234, 672, 512 + extra);
        Place(battle, 24, 766 + extra, 672, 282);
        Place(growth, 24, 1064 + extra, 672, 62);
        Place(confirm, 24, 1144 + extra, 672, 88);
        Place(connectionLabel.rectTransform, 24, 1238 + extra, 672, 28);
        float chartHeight = 512 + extra - 130;
        float diameter = Mathf.Min(376, chartHeight - 122);
        float centerY = chartHeight * .5f + 17;
        Place(chart, (672 - diameter) * .5f, centerY - diameter * .5f, diameter, diameter);
        float labelRadius = diameter * .46f + 32;
        for (int i = 0; i < 6; i++)
        {
            Vector2 p = HealthMonRadarGraphic.AxisPoint(i, labelRadius);
            // Side captions stay outside the graph; top/bottom captions follow its radius.
            float x = i == 0 || i == 3 ? 336 : i < 3 ? 584 : 88;
            Place(axisGroups[i], x - 58, centerY - p.y - 24, 116, 48);
        }
    }

    private static void Set(TMP_Text text, string value) { if (text.text != value) text.text = value; }
    private static void SetFill(RectTransform rect, float min, float max)
    {
        rect.anchorMin = new Vector2(min, 0); rect.anchorMax = new Vector2(max, 1);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        rect.gameObject.SetActive(max - min > .0001f);
    }
    private static RectTransform Rect(string name, Transform parent)
    {
        var go = new GameObject(name, typeof(RectTransform)); go.transform.SetParent(parent, false);
        return (RectTransform)go.transform;
    }
    private static void Stretch(RectTransform rect)
    {
        rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one; rect.offsetMin = rect.offsetMax = Vector2.zero;
    }
    private static void Place(RectTransform rect, float x, float y, float w, float h)
    {
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0, 1);
        rect.anchoredPosition = new Vector2(x, -y); rect.sizeDelta = new Vector2(w, h);
    }
    private static HealthMonStatusPanelGraphic Panel(string name, Transform parent, Color top, Color bottom, Color border, float radius)
    {
        var rect = Rect(name, parent); var panel = rect.gameObject.AddComponent<HealthMonStatusPanelGraphic>();
        panel.Top = top; panel.Bottom = bottom; panel.Border = border; panel.Radius = radius;
        panel.raycastTarget = false;
        return panel;
    }
    private static RectTransform Card(string name, Transform parent, float x, float y, float w, float h)
    {
        var panel = Panel(name, parent, new Color(.08f, .22f, .40f), new Color(.035f, .12f, .24f), Edge, 24);
        Place(panel.rectTransform, x, y, w, h); return panel.rectTransform;
    }
    private TMP_Text Text(string name, Transform parent, string value, float x, float y, float w, float h, float size, Color tint,
        TextAlignmentOptions alignment = TextAlignmentOptions.Left)
    {
        var rect = Rect(name, parent); Place(rect, x, y, w, h);
        var label = rect.gameObject.AddComponent<TextMeshProUGUI>(); label.font = font;
        label.text = value; label.color = tint; label.alignment = alignment;
        label.fontStyle = FontStyles.Bold; label.enableAutoSizing = true; label.fontSize = size;
        label.fontSizeMin = size * .78f; label.fontSizeMax = size;
        label.textWrappingMode = TextWrappingModes.NoWrap; label.overflowMode = TextOverflowModes.Ellipsis;
        label.margin = Vector4.zero; label.raycastTarget = false;
        return label;
    }
    private void SectionTitle(RectTransform parent, string value)
    {
        var panel = Panel("SectionTitle", parent, new Color(.08f, .42f, .68f), new Color(.04f, .25f, .46f), Cyan, 22);
        Place(panel.rectTransform, 232, -20, 208, 44);
        Text("Label", panel.transform, value, 10, 0, 188, 44, 24, White, TextAlignmentOptions.Center);
    }
    private RectTransform Button(string name, Transform parent, string value, Action close, bool gold)
    {
        var panel = Panel(name, parent, gold ? new Color(1, .87f, .35f) : new Color(.05f, .24f, .44f),
            gold ? new Color(.94f, .48f, .01f) : new Color(.03f, .16f, .31f), gold ? new Color(1, .97f, .65f) : Edge, gold ? 24 : 44);
        panel.BorderWidth = gold ? 3 : 1.5f; panel.raycastTarget = true;
        var button = panel.gameObject.AddComponent<UnityEngine.UI.Button>(); button.targetGraphic = panel;
        button.onClick.AddListener(() => close?.Invoke());
        var nav = button.navigation; nav.mode = Navigation.Mode.None; button.navigation = nav;
        var label = Text("Label", panel.transform, value, 0, 0, gold ? 672 : 88, 88, gold ? 32 : 50,
            gold ? new Color(.15f, .10f, .02f) : White, TextAlignmentOptions.Center);
        Stretch(label.rectTransform);
        return panel.rectTransform;
    }
    private static RectTransform Track(string name, Transform parent, float x, float y, float w, float h)
    {
        var panel = Panel(name, parent, new Color(.01f, .06f, .13f), new Color(.01f, .06f, .13f), Edge, h * .5f);
        Place(panel.rectTransform, x, y, w, h);
        var inner = Rect("Inner", panel.transform); Stretch(inner); inner.offsetMin = new Vector2(3, 3); inner.offsetMax = new Vector2(-3, -3);
        return inner;
    }
    private static RectTransform Fill(string name, Transform parent, Color top, Color bottom)
    {
        var fill = Panel(name, parent, top, bottom, Color.clear, 8); Stretch(fill.rectTransform); return fill.rectTransform;
    }
    private TMP_Text Resource(Transform parent, string key, string caption, float y, Color left, Color right, out RectTransform capacityFill)
    {
        var panel = Panel(key, parent, new Color(.02f, .11f, .23f), new Color(.015f, .08f, .18f), Edge, 18);
        Place(panel.rectTransform, 24, y, 624, 50);
        Text("Caption", panel.transform, caption, 16, 0, 116, 50, 21, key == "HP" ? new Color(1, .50f, .57f) : Cyan);
        var track = Track("Capacity", panel.transform, 140, 17, 332, 16);
        capacityFill = Fill("Fill", track, right, left);
        return Text("Value", panel.transform, "—", 484, 0, 124, 50, 24, White, TextAlignmentOptions.Right);
    }
}
