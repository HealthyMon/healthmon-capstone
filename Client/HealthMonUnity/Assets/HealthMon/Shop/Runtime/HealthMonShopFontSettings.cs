using TMPro;
using UnityEngine;

/// <summary>
/// Assign a Korean-capable TMP font for the entire ShopOverlay.
/// Choose fonts on HealthMonShopUI and click Apply All Shop Fonts in Inspector.
/// Does not modify non-shop text, dialogue, scene assets or gameplay.
/// </summary>
[DisallowMultipleComponent]
public sealed class HealthMonShopFontSettings : MonoBehaviour
{
    [Header("한글이 포함된 Dynamic TMP Font Asset")]
    public TMP_FontAsset bodyFont;
    public TMP_FontAsset headingFont;
    [Header("상점 글자 표시 설정")]
    [Range(.65f, 1f)] public float minimumAutoSizeRatio = .76f;
    public bool enableAutoSize = true;

    [ContextMenu("Apply All Shop Fonts / 상점 전체 폰트 적용")]
    public void ApplyAllShopFonts()
    {
        TMP_FontAsset baseFont = bodyFont != null ? bodyFont : headingFont;
        if (baseFont == null)
        {
            Debug.LogWarning("[HealthMon Shop] 먼저 Body Font에 한글 TMP 폰트를 연결하세요.", this);
            return;
        }
        int count = 0;
        foreach (TMP_Text label in GetComponentsInChildren<TMP_Text>(true))
        {
            bool title = label.name == "ShopTitle" || label.name == "BannerTitle" ||
                         label.name == "ModalTitle" || label.name == "SelectedName" ||
                         label.name == "SuccessTitle" || label.name == "Name";
            label.font = title && headingFont != null ? headingFont : baseFont;
            if (enableAutoSize)
            {
                label.enableAutoSizing = true;
                label.fontSizeMax = label.fontSize;
                label.fontSizeMin = Mathf.Max(14f, label.fontSize * minimumAutoSizeRatio);
            }
            label.SetAllDirty();
            count++;
        }
        Debug.Log("[HealthMon Shop] 상점 TMP 폰트를 " + count + "개 텍스트에 적용했습니다.", this);
    }
}
