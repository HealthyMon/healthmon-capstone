using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Visual-only layer for the real server quest ledger.
// This does not fabricate offers, intercept responses, change rewards or replace buttons.
[DisallowMultipleComponent]
public sealed class HealthMonQuestSkinV31 : MonoBehaviour
{
    private readonly Dictionary<int, Image> styledImages = new Dictionary<int, Image>();
    private float nextRefresh;
    private Sprite card, panel, acceptButton, rejectButton, track, fill;
    private static readonly Regex ProgressPattern = new Regex(@"진행도\s*([0-9.]+)\s*/\s*([0-9.]+)", RegexOptions.Compiled);

    private void OnEnable() { nextRefresh = 0f; }

    private void LateUpdate()
    {
        if (Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + 0.6f;
        if (!isActiveAndEnabled) return;

        if (card == null) card = Resources.Load<Sprite>("HMUI/Card_Quest");
        if (panel == null) panel = Resources.Load<Sprite>("HMUI/Card_Dark");
        if (acceptButton == null) acceptButton = Resources.Load<Sprite>("HMUI/Btn_Mint");
        if (rejectButton == null) rejectButton = Resources.Load<Sprite>("HMUI/Btn_White");
        if (track == null) track = Resources.Load<Sprite>("HMUI/Progress_Track");
        if (fill == null) fill = Resources.Load<Sprite>("HMUI/Progress_Mint");

        var serverPanel = transform.Find("ServerQuestPanel");
        if (serverPanel == null) return; // created by CommonServerQuestUI at runtime
        Skin(serverPanel.GetComponent<Image>(), panel, Color.white);
        SetText(serverPanel.Find("Summary"), new Color(.95f, .99f, 1f), 28f, TextAlignmentOptions.Left);
        SetText(serverPanel.Find("Notice"), new Color(.77f, .91f, .98f), 22f, TextAlignmentOptions.Center);
        SkinButton(serverPanel.Find("RefreshQuests"), acceptButton, new Color(.08f, .29f, .40f));
        var content = serverPanel.Find("Viewport/Content");
        if (content == null) return;
        foreach (Transform child in content)
        {
            if (!child.name.StartsWith("Quest-", StringComparison.Ordinal)) continue;
            var row = child.GetComponent<RectTransform>();
            if (row == null) continue;
            Skin(child.GetComponent<Image>(), card, Color.white);
            var le = child.GetComponent<LayoutElement>();
            if (le != null && le.preferredHeight < 190) le.preferredHeight = 195;
            SetText(child.Find("QuestDetails"), new Color(.09f, .25f, .44f), 27f, TextAlignmentOptions.Left);
            SkinButton(child.Find("Accept"), acceptButton, new Color(.07f, .30f, .37f));
            SkinButton(child.Find("Reject"), rejectButton, new Color(.18f, .30f, .49f));
            ApplyActualProgress(row, child.Find("QuestDetails") != null ? child.Find("QuestDetails").GetComponent<TMP_Text>() : null);
        }
        // remove cache entries for destroyed quest rows after server refresh
        if (styledImages.Count > 150) styledImages.Clear();
    }


    private void ApplyActualProgress(RectTransform cardRoot, TMP_Text questLabel)
    {
        if (cardRoot == null || questLabel == null) return;
        var match = ProgressPattern.Match(questLabel.text ?? string.Empty);
        if (!match.Success) return;
        if (!float.TryParse(match.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float now)) return;
        if (!float.TryParse(match.Groups[2].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float goal) || goal <= 0) return;
        var trackRect = cardRoot.Find("HM_ActualProgress") as RectTransform;
        if (trackRect == null)
        {
            var obj = new GameObject("HM_ActualProgress", typeof(RectTransform), typeof(Image));
            trackRect = obj.GetComponent<RectTransform>(); trackRect.SetParent(cardRoot, false);
            trackRect.anchorMin = new Vector2(.045f, .055f); trackRect.anchorMax = new Vector2(.72f, .145f);
            trackRect.offsetMin = trackRect.offsetMax = Vector2.zero;
            var image = obj.GetComponent<Image>();
            image.sprite = track; image.type = Image.Type.Sliced; image.color = Color.white; image.raycastTarget = false;
        }
        var fillRect = trackRect.Find("Fill") as RectTransform;
        if (fillRect == null)
        {
            var obj = new GameObject("Fill", typeof(RectTransform), typeof(Image));
            fillRect = obj.GetComponent<RectTransform>(); fillRect.SetParent(trackRect, false);
            fillRect.pivot = new Vector2(0,.5f);
            var image = obj.GetComponent<Image>();
            image.sprite = fill; image.type = Image.Type.Sliced; image.color = Color.white; image.raycastTarget = false;
        }
        fillRect.anchorMin = new Vector2(.02f,.13f);
        fillRect.anchorMax = new Vector2(Mathf.Lerp(.025f,.98f,Mathf.Clamp01(now/goal)),.87f);
        fillRect.offsetMin = fillRect.offsetMax = Vector2.zero;
    }

    private void Skin(Image img, Sprite sprite, Color color)
    {
        if (img == null || sprite == null) return;
        if (img.sprite == sprite && styledImages.ContainsKey(img.GetInstanceID())) return;
        img.sprite = sprite;
        img.type = Image.Type.Sliced;
        img.color = color;
        img.raycastTarget = false;
        styledImages[img.GetInstanceID()] = img;
    }

    private void SkinButton(Transform t, Sprite sprite, Color ink)
    {
        if (t == null) return;
        var button = t.GetComponent<Button>();
        if (button == null) return; // never create or replace original events
        var img = t.GetComponent<Image>();
        if (img == null || sprite == null) return;
        img.sprite = sprite; img.type = Image.Type.Sliced; img.color = Color.white;
        img.raycastTarget = true;
        var label = t.GetComponentInChildren<TMP_Text>(true);
        if (label != null) { label.color = ink; label.enableAutoSizing = true; label.fontSizeMin = 16; label.fontSizeMax = 26; }
    }

    private static void SetText(Transform t, Color color, float size, TextAlignmentOptions align)
    {
        if (t == null) return;
        var txt = t.GetComponent<TMP_Text>();
        if (txt == null) return;
        txt.color = color;
        txt.enableAutoSizing = true;
        txt.fontSizeMin = size * 0.70f;
        txt.fontSizeMax = size;
        txt.alignment = align;
    }
}
