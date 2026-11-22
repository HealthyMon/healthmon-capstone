using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class AdventureInventoryRowUI : MonoBehaviour
{
    [SerializeField] private Image iconImage;
    [SerializeField] private TMP_Text nameText;
    [SerializeField] private TMP_Text detailText;
    [SerializeField] private TMP_Text countText;
    [SerializeField] private Button useButton;
    [SerializeField] private TMP_Text useButtonText;
    private Action onUse;

    private void Awake()
    {
        if (useButton != null) useButton.onClick.AddListener(Use);
    }
    private void OnDestroy()
    {
        if (useButton != null) useButton.onClick.RemoveListener(Use);
    }
    public void Bind(AdventureItemDefinition definition, int count, bool allowed, Action use)
    {
        onUse = use;
        if (nameText != null) nameText.text = definition.itemName;
        if (countText != null) countText.text = "x" + count;
        if (detailText != null)
        {
            var effects = new System.Text.StringBuilder();
            if (definition.effects != null)
                foreach (var effect in definition.effects)
                {
                    if (effect == null) continue;
                    if (effects.Length > 0) effects.Append(" / ");
                    effects.Append(effect.stat).Append(' ').Append(effect.amount >= 0 ? "+" : "").Append(effect.amount.ToString("0.##"));
                }
            detailText.text = effects.Length == 0 ? definition.description : effects.ToString();
        }
        if (iconImage != null)
        {
            iconImage.sprite = definition.icon;
            iconImage.enabled = definition.icon != null;
        }
        if (useButton != null) useButton.interactable = allowed;
        if (useButtonText != null) useButtonText.text = allowed ? "사용" : "불가";
    }
    private void Use() { onUse?.Invoke(); }
}
