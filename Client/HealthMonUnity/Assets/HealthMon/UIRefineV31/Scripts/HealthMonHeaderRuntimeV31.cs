using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Adapts only the settings launcher generated at runtime by MobileAdminMenu.
// Keeps all existing click events, server connections, evolution visuals and 3D cameras.
[DisallowMultipleComponent]
public sealed class HealthMonHeaderRuntimeV31 : MonoBehaviour
{
    private float nextCheck;
    private Sprite buttonSprite;
    private void LateUpdate()
    {
        if (Time.unscaledTime < nextCheck) return;
        nextCheck = Time.unscaledTime + .5f;
        var settings = transform.Find("UnifiedSettingsButton");
        if (settings == null) return;
        var evolution = transform.Find("EvolutionOverlay");
        bool evolving = evolution != null && evolution.gameObject.activeInHierarchy &&
            (evolution.GetComponent<CanvasGroup>() == null || evolution.GetComponent<CanvasGroup>().alpha > 0.05f);
        if (settings.gameObject.activeSelf == evolving) settings.gameObject.SetActive(!evolving);
        if (evolving) return;
        var rt = settings as RectTransform;
        if (rt == null) return;
        rt.anchorMin = rt.anchorMax = rt.pivot = Vector2.one;
        rt.sizeDelta = new Vector2(142, 62);
        rt.anchoredPosition = new Vector2(-20, -22);
        if (buttonSprite == null) buttonSprite = Resources.Load<Sprite>("HMUI/Btn_Blue");
        var img = settings.GetComponent<Image>();
        if (img != null && buttonSprite != null)
        {
            img.sprite = buttonSprite; img.type = Image.Type.Sliced;
            img.color = Color.white;
        }
        var tmp = settings.GetComponentInChildren<TMP_Text>(true);
        if (tmp != null)
        {
            tmp.text = "설정";
            tmp.color = Color.white;
            tmp.enableAutoSizing = true;
            tmp.fontSizeMin = 21; tmp.fontSizeMax = 28;
        }
    }
}
