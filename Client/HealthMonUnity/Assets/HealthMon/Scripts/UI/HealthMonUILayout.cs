using TMPro;
using UnityEngine;
using UnityEngine.UI;

public static class HealthMonUILayout
{
    public static void Place(RectTransform rect, float left, float bottom, float right, float top)
    {
        if (rect == null) return;
        rect.anchorMin = new Vector2(left, bottom);
        rect.anchorMax = new Vector2(right, top);
        rect.offsetMin = rect.offsetMax = Vector2.zero;
        rect.localScale = Vector3.one;
    }

    public static void Text(TMP_Text text, float left, float bottom, float right, float top, float maxSize)
    {
        if (text == null) return;
        Place(text.rectTransform, left, bottom, right, top);
        text.enableAutoSizing = true;
        text.fontSizeMin = 18;
        text.fontSizeMax = maxSize;
        text.overflowMode = TextOverflowModes.Ellipsis;
    }

    public static void Navigation(Transform canvas)
    {
        // Style-kit panels are nine-slice sprites. Stretching the complete bitmap
        // stretches their corner highlights through the entire panel.
        foreach (var image in canvas.GetComponentsInChildren<Image>(true))
        {
            if (image.sprite == null || image.sprite.border == Vector4.zero) continue;
            string name = image.sprite.name;
            if (!name.StartsWith("Card_") && !name.StartsWith("Bar_") && !name.StartsWith("BTN_")) continue;
            image.type = Image.Type.Sliced;
            image.preserveAspect = false;
        }
        var nav = canvas.Find("BottomNavV2");
        if (nav == null) return;
        foreach (var button in nav.GetComponentsInChildren<Button>(true))
        {
            foreach (var label in button.GetComponentsInChildren<TMP_Text>(true))
            {
                Text(label, .06f, .12f, .94f, .43f, 27);
                label.alignment = TextAlignmentOptions.Center;
            }
            foreach (var icon in button.GetComponentsInChildren<Image>(true))
            {
                if (icon.transform == button.transform) continue;
                Place(icon.rectTransform, .31f, .47f, .69f, .87f);
                icon.preserveAspect = true;
            }
            foreach (var icon in button.GetComponentsInChildren<RawImage>(true))
            {
                // Legacy color thumbnails sit on top of the installed nav icon.
                var installed = icon.transform.parent.GetComponent<Image>();
                if (installed != null && installed.sprite != null) icon.enabled = false;
            }
        }
    }
}
