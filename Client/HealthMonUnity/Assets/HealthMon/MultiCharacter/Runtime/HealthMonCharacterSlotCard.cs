using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public sealed class HealthMonCharacterSlotCard : MonoBehaviour
{
    public Image background;
    public Image portrait;
    public TMP_Text nameLabel;
    public TMP_Text levelLabel;
    public TMP_Text statusLabel;
    public TMP_Text statsLabel;
    public Button button;
    public Sprite normalSprite, activeSprite, lockedSprite;

    public void Bind(string name, string level, string stats, string status, Sprite image,
        bool active, bool locked, Action click)
    {
        if (nameLabel != null) nameLabel.text = name;
        if (levelLabel != null) levelLabel.text = level;
        if (statusLabel != null) statusLabel.text = status;
        if (statsLabel != null) statsLabel.text = stats;
        if (portrait != null)
        {
            portrait.sprite = image;
            portrait.enabled = image != null;
            portrait.preserveAspect = true;
            // Unpurchased pets are displayed as shaded previews, not as owned.
            portrait.color = locked ? new Color(.39f,.48f,.63f,1f) : Color.white;
        }
        if (nameLabel != null) nameLabel.color = locked ? new Color(.81f,.88f,.95f) : Color.white;
        if (levelLabel != null) levelLabel.color = locked ? new Color(.78f,.84f,.94f) : new Color(1f,.94f,.68f);
        if (statusLabel != null) statusLabel.color = locked ? new Color(1f,.84f,.53f) : new Color(.73f,1f,.90f);
        if (background != null)
        {
            Sprite s = active ? activeSprite : locked ? lockedSprite : normalSprite;
            if (s != null) { background.sprite = s; background.type = Image.Type.Sliced; }
        }
        if (button != null) { button.onClick.RemoveAllListeners(); button.onClick.AddListener(() => click?.Invoke()); }
    }
}
