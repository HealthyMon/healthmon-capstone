using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class HealthMonShopProductCard : MonoBehaviour
{
    public Image icon;
    public Image cardBackground;
    public TMP_Text nameLabel;
    public TMP_Text subtitleLabel;
    public TMP_Text priceLabel;
    public Button cardButton;
    public Sprite normalBackground;
    public Sprite featuredBackground;
    private HealthMonShopItem item;
    private Action<HealthMonShopItem> onSelect;

    public void Bind(HealthMonShopItem next, bool owned, Action<HealthMonShopItem> onClick)
    {
        item = next;
        onSelect = onClick;
        if (icon != null) { icon.sprite = item.icon; icon.enabled = item.icon != null; icon.preserveAspect = true; }
        if (cardBackground != null && normalBackground != null)
            cardBackground.sprite = item.featured && featuredBackground != null ? featuredBackground : normalBackground;
        if (nameLabel != null) nameLabel.text = item.displayName;
        if (subtitleLabel != null) subtitleLabel.text = item.category == HealthMonShopCategory.Accessory ? "장신구" : "새로운 헬스몬";
        if (priceLabel != null) priceLabel.text = owned ? "보유 중" : (item.displayCoinPrice.ToString("N0") + " C");
        if (cardButton != null)
        {
            cardButton.onClick.RemoveAllListeners();
            cardButton.onClick.AddListener(() => onSelect?.Invoke(item));
        }
    }
}
