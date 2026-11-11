
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class AdventurePlayerStatusUI : MonoBehaviour
{
    [SerializeField] private AdventurePlayerStats stats;

    [SerializeField] private TMP_Text hpText;
    [SerializeField] private TMP_Text stText;

    [SerializeField] private Slider hpBar;
    [SerializeField] private Slider stBar;

    private void OnEnable()
    {
        if (stats != null)
            stats.OnStatsChanged += RefreshUI;

        RefreshUI();
    }

    private void OnDisable()
    {
        if (stats != null)
            stats.OnStatsChanged -= RefreshUI;
    }

    public void RefreshUI()
    {
        if (stats == null || !stats.IsInitialized)
            return;

        if (hpText != null)
        {
            hpText.text =
                $"{stats.CurrentHP}/{stats.MaxHP}";
        }

        if (stText != null)
        {
            stText.text =
                $"{stats.CurrentST:F0}/{stats.MaxST:F0}";
        }

        if (hpBar != null)
        {
            hpBar.maxValue = Mathf.Max(1, stats.MaxHP);
            hpBar.value = stats.CurrentHP;
        }

        if (stBar != null)
        {
            stBar.maxValue = Mathf.Max(1f, stats.MaxST);
            stBar.value = stats.CurrentST;
        }
    }
}
