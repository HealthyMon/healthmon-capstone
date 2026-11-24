using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Presentation only. Does not alter panel routing, AI/server, pet preview, or button.onClick.
[DisallowMultipleComponent]
public sealed class HealthMonUIV4RuntimeSkin : MonoBehaviour
{
    [SerializeField] private Sprite settingsButtonSprite;
    [SerializeField] private GameObject evolutionOverlay;
    private RectTransform launcher;
    private bool applied;

    public void Configure(Sprite sprite, GameObject evolution)
    {
        settingsButtonSprite = sprite;
        evolutionOverlay = evolution;
        applied = false;
    }

    private void LateUpdate()
    {
        // MobileAdminMenu creates this button at runtime (not in the scene).
        if (launcher == null)
        {
            launcher = transform.Find("UnifiedSettingsButton") as RectTransform;
            applied = false;
        }
        if (launcher == null) return;
        if (!applied)
        {
            var background = launcher.GetComponent<Image>();
            if (background != null && settingsButtonSprite != null)
            {
                background.sprite = settingsButtonSprite;
                background.type = Image.Type.Sliced;
                background.color = Color.white;
            }
            launcher.anchorMin = launcher.anchorMax = launcher.pivot = Vector2.one;
            launcher.sizeDelta = new Vector2(166f, 72f);
            var label = launcher.GetComponentInChildren<TMP_Text>(true);
            if (label != null)
            {
                label.text = "설정";
                label.fontSize = 28f;
                label.fontSizeMin = 22f;
                label.fontSizeMax = 28f;
                label.alignment = TextAlignmentOptions.Center;
                label.color = Color.white;
            }
            applied = true;
        }
        // The evolution effect is a full-screen event: avoid floating controls over it.
        // The original MobileAdminMenu will restore normal launcher visibility itself.
        if (evolutionOverlay != null && evolutionOverlay.activeInHierarchy && launcher.gameObject.activeSelf)
            launcher.gameObject.SetActive(false);
    }
}
