using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// A seventh BottomNavV2 entry. Stores and restores the other six
/// button colors when the shop overlay is opened/closed.
/// </summary>
public sealed class HealthMonShopNavVisual : MonoBehaviour
{
    public HealthMonShopScreen shop;
    public Image shopBackground;
    public TMP_Text shopLabel;
    public Sprite idleSprite;
    public Sprite selectedSprite;
    public Image[] previousNavBackgrounds;
    public TMP_Text[] previousNavLabels;

    private Sprite[] savedSprites;
    private Color[] savedColors;
    private bool wasOpen;

    private void LateUpdate()
    {
        if (shop == null || shop.overlay == null) return;
        bool open = shop.overlay.activeSelf;
        if (open == wasOpen) return;
        wasOpen = open;
        if (open)
        {
            int n = previousNavBackgrounds != null ? previousNavBackgrounds.Length : 0;
            savedSprites = new Sprite[n];
            savedColors = new Color[n];
            for (int i = 0; i < n; i++)
            {
                var img = previousNavBackgrounds[i];
                if (img != null)
                {
                    savedSprites[i] = img.sprite;
                    if (idleSprite != null) img.sprite = idleSprite;
                }
                if (previousNavLabels != null && i < previousNavLabels.Length && previousNavLabels[i] != null)
                {
                    savedColors[i] = previousNavLabels[i].color;
                    previousNavLabels[i].color = Color.white;
                }
            }
        }
        else
        {
            int n = previousNavBackgrounds != null ? previousNavBackgrounds.Length : 0;
            for (int i = 0; i < n; i++)
            {
                if (previousNavBackgrounds[i] != null && savedSprites != null && i < savedSprites.Length)
                    previousNavBackgrounds[i].sprite = savedSprites[i];
                if (previousNavLabels != null && i < previousNavLabels.Length && previousNavLabels[i] != null &&
                    savedColors != null && i < savedColors.Length)
                    previousNavLabels[i].color = savedColors[i];
            }
        }
        if (shopBackground != null)
        {
            shopBackground.sprite = open ? selectedSprite : idleSprite;
            if (shopBackground.sprite != null) shopBackground.type = Image.Type.Sliced;
        }
        if (shopLabel != null) shopLabel.color = open ? new Color(.2f,.16f,.10f) : Color.white;
    }
}
