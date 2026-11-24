using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Reward event overlay. A pending reward is claimed exactly once by AdventureManager.
public class AdventureRewardEventUI : MonoBehaviour
{
    [Header("Reward Pool (IDs registered in AdventureItemDatabase)")]
    [SerializeField] private List<string> rewardItemIds = new List<string> {
        "potion_hp_01", "potion_st_01", "potion_all_01"
    };
    [Header("UI")]
    [SerializeField] private GameObject rewardPanel;
    [SerializeField] private TMP_Text itemNameText;
    [SerializeField] private TMP_Text itemDescriptionText;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private Image itemIcon;
    [SerializeField] private Button claimButton;

    private string selectedId;
    private Action<string> claimCallback;
    private bool pending;

    private void Awake()
    {
        if (rewardPanel != null) rewardPanel.SetActive(false);
        if (claimButton != null) claimButton.onClick.AddListener(Claim);
    }

    private void OnDestroy()
    {
        if (claimButton != null) claimButton.onClick.RemoveListener(Claim);
    }

    public bool BeginReward(AdventureInventory inventory, Action<string> onClaim)
    {
        if (pending || inventory == null || inventory.Database == null || onClaim == null ||
            rewardPanel == null || claimButton == null) return false;

        var candidates = new List<AdventureItemDefinition>();
        var seen = new HashSet<string>();
        foreach (var id in rewardItemIds)
        {
            if (string.IsNullOrWhiteSpace(id) || !seen.Add(id)) continue;
            var definition = inventory.Database.Find(id);
            if (definition != null && definition.consumable && definition.CanUse(true))
                candidates.Add(definition);
        }
        if (candidates.Count == 0) return false;
        var picked = candidates[UnityEngine.Random.Range(0, candidates.Count)];
        selectedId = picked.itemId;
        claimCallback = onClaim;
        pending = true;
        if (itemNameText != null) itemNameText.text = picked.itemName + "  x1";
        if (itemDescriptionText != null) itemDescriptionText.text = picked.description;
        if (statusText != null) statusText.text = "아이템을 수령하면 다음 층으로 이동할 수 있습니다.";
        if (itemIcon != null)
        {
            itemIcon.sprite = picked.icon;
            itemIcon.enabled = picked.icon != null;
        }
        claimButton.interactable = true;
        rewardPanel.SetActive(true);
        return true;
    }

    private void Claim()
    {
        if (!pending || string.IsNullOrEmpty(selectedId) || claimCallback == null) return;
        claimButton.interactable = false;
        claimCallback.Invoke(selectedId);
        // On success AdventureManager calls FinishReward(); on failure allow retry.
        if (pending)
        {
            if (statusText != null) statusText.text = "아이템 수령에 실패했습니다. 다시 시도해 주세요.";
            claimButton.interactable = true;
        }
    }

    public void FinishReward()
    {
        pending = false;
        selectedId = null;
        claimCallback = null;
        if (rewardPanel != null) rewardPanel.SetActive(false);
    }
}
