using UnityEngine;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// Presentation-only state for the six existing HealthMon screens.
/// Does not change screen routing or existing Button.onClick listeners.
/// </summary>
public sealed class HealthMonSixNavHighlighter : MonoBehaviour
{
    [SerializeField] private Image[] buttonImages = new Image[6];
    [SerializeField] private TMP_Text[] buttonLabels = new TMP_Text[6];
    [SerializeField] private GameObject[] watchedPanels = new GameObject[6];
    [SerializeField] private Sprite normalSprite;
    [SerializeField] private Sprite selectedSprite;
    [SerializeField] private int selectedIndex = 0;

    public void Configure(Image[] images, TMP_Text[] labels, GameObject[] panels, Sprite normal, Sprite selected)
    {
        buttonImages = images;
        buttonLabels = labels;
        watchedPanels = panels;
        normalSprite = normal;
        selectedSprite = selected;
        selectedIndex = 0;
        RefreshVisuals();
    }

    private void OnEnable() { RefreshVisuals(); }

    private void LateUpdate()
    {
        if (watchedPanels == null) return;
        for (int i = 0; i < Mathf.Min(6, watchedPanels.Length); i++)
        {
            if (watchedPanels[i] == null || !watchedPanels[i].activeInHierarchy) continue;
            if (selectedIndex != i)
            {
                selectedIndex = i;
                RefreshVisuals();
            }
            return;
        }
        // Other panels (e.g. customization) intentionally keep the last selection.
    }

    private void RefreshVisuals()
    {
        if (buttonImages == null) return;
        for (int i = 0; i < buttonImages.Length; i++)
        {
            if (buttonImages[i] == null) continue;
            buttonImages[i].sprite = i == selectedIndex ? selectedSprite : normalSprite;
            buttonImages[i].type = Image.Type.Sliced;
            buttonImages[i].color = Color.white;
            if (buttonLabels != null && i < buttonLabels.Length && buttonLabels[i] != null)
                buttonLabels[i].color = i == selectedIndex
                    ? new Color(0.20f, 0.16f, 0.10f, 1f) : Color.white;
        }
    }
}
