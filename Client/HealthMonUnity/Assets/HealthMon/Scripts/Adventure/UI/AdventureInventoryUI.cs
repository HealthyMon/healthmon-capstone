using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Shared inventory popup: uses existing item definitions, never stores a second inventory.
public class AdventureInventoryUI : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private AdventureInventory inventory;
    [SerializeField] private AdventureManager adventureManager;
    [SerializeField] private BattleManager battleManager;

    [Header("UI")]
    [SerializeField] private Button explorationOpenButton;
    [SerializeField] private GameObject popup;
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text hintText;
    [SerializeField] private Transform itemListContent;
    [SerializeField] private AdventureInventoryRowUI rowPrefab;
    [SerializeField] private Button closeButton;
    [SerializeField] private Button debugGrantButton;

    private readonly List<AdventureInventoryRowUI> rows = new List<AdventureInventoryRowUI>();
    private bool inBattle;

    private void Awake()
    {
        if (inventory == null) inventory = FindFirstObjectByType<AdventureInventory>();
        if (adventureManager == null) adventureManager = FindFirstObjectByType<AdventureManager>();
        if (battleManager == null) battleManager = FindFirstObjectByType<BattleManager>();
        if (popup != null) popup.SetActive(false);
        if (rowPrefab != null) rowPrefab.gameObject.SetActive(false);
        if (explorationOpenButton != null) explorationOpenButton.onClick.AddListener(OpenExploration);
        if (closeButton != null) closeButton.onClick.AddListener(Close);
#if UNITY_EDITOR
        if (debugGrantButton != null) debugGrantButton.onClick.AddListener(GrantTestItems);
#endif
    }

    private void OnEnable()
    {
        if (inventory != null) inventory.InventoryChanged += Refresh;
    }

    private void OnDisable()
    {
        if (inventory != null) inventory.InventoryChanged -= Refresh;
    }

    private void OnDestroy()
    {
        if (explorationOpenButton != null) explorationOpenButton.onClick.RemoveListener(OpenExploration);
        if (closeButton != null) closeButton.onClick.RemoveListener(Close);
#if UNITY_EDITOR
        if (debugGrantButton != null) debugGrantButton.onClick.RemoveListener(GrantTestItems);
#endif
    }

    private void Update()
    {
        bool canExplore = adventureManager != null && adventureManager.CanUseExplorationItem;
        if (debugGrantButton != null)
        {
#if UNITY_EDITOR
            bool showDebug = canExplore;
#else
            bool showDebug = false;
#endif
            if (debugGrantButton.gameObject.activeSelf != showDebug) debugGrantButton.gameObject.SetActive(showDebug);
        }
        if (explorationOpenButton != null && explorationOpenButton.gameObject.activeSelf != canExplore)
            explorationOpenButton.gameObject.SetActive(canExplore);
        if (popup != null && popup.activeSelf)
        {
            bool valid = inBattle ? IsPlayerTurn() : canExplore;
            if (!valid) Close();
        }
    }

    private bool IsPlayerTurn()
    {
        return battleManager != null && battleManager.currentState == BattleState.PlayerSelecting
               && battleManager.player != null && battleManager.player.IsAlive;
    }

    public void OpenExploration()
    {
        if (adventureManager == null || !adventureManager.CanUseExplorationItem) return;
        inBattle = false;
        Open();
    }

    // Called from existing BattleUI Item button, not from an additional battle HUD.
    public void OpenBattle()
    {
        if (!IsPlayerTurn()) return;
        inBattle = true;
        Open();
    }

    private void Open()
    {
        if (popup == null || inventory == null || rowPrefab == null || itemListContent == null) return;
        popup.SetActive(true);
        if (titleText != null) titleText.text = inBattle ? "전투 아이템" : "탐험 인벤토리";
        Refresh();
    }

    public void Close()
    {
        if (popup != null) popup.SetActive(false);
    }

    public void Refresh()
    {
        if (popup == null || !popup.activeSelf || inventory == null) return;
        foreach (var row in rows) if (row != null) Destroy(row.gameObject);
        rows.Clear();
        int total = 0, usable = 0;
        foreach (var entry in inventory.CreateSnapshot())
        {
            if (entry == null || entry.count < 1) continue;
            var def = inventory.Database != null ? inventory.Database.Find(entry.itemId) : null;
            if (def == null) continue;
            total++;
            bool allowed = def.consumable && def.CanUse(inBattle);
            // For battle, check ST. Detailed effect feasibility is checked atomically by TryUseInBattle.
            if (inBattle && (battleManager == null || battleManager.player == null ||
                !battleManager.player.CanSpendST(battleManager.itemCost))) allowed = false;
            var row = Instantiate(rowPrefab, itemListContent);
            row.gameObject.SetActive(true);
            bool useAllowed = allowed;
            string itemId = entry.itemId;
            row.Bind(def, entry.count, allowed, () => Use(itemId));
            rows.Add(row);
            if (useAllowed) usable++;
        }
        if (hintText != null)
        {
            if (total == 0) hintText.text = "보유한 아이템이 없습니다.";
            else if (usable == 0) hintText.text = "현재 사용 가능한 아이템이 없습니다.";
            else hintText.text = inBattle ? "사용 시 행동 1회를 소비하고 ST가 소모됩니다." : "아이템을 선택하면 즉시 사용됩니다.";
        }
    }

#if UNITY_EDITOR
    private void GrantTestItems()
    {
        if (inventory == null || adventureManager == null || !adventureManager.CanUseExplorationItem) return;
        string[] ids = { "potion_hp_01", "potion_st_01", "fruit_atk_01", "potion_all_01" };
        foreach (var id in ids) inventory.AddItem(id, 2);
        Debug.Log("[Inventory UI] Editor-only test items granted (2 each for IDs available in database).");
    }
#endif

    private void Use(string itemId)
    {
        if (inventory == null) return;
        if (inBattle)
        {
            if (!IsPlayerTurn() || inventory.GetCount(itemId) <= 0) { Refresh(); return; }
            // BattleManager handles validation, effect, consumption and spending the turn.
            battleManager.SelectBattleItem(itemId);
            battleManager.ExecutePlayerAction(BattleActionType.Item);
            if (battleManager.currentState != BattleState.PlayerSelecting) Close();
            else Refresh();
        }
        else
        {
            if (adventureManager == null || !adventureManager.CanUseExplorationItem) { Close(); return; }
            if (!inventory.TryUseInExploration(itemId))
            {
                if (hintText != null) hintText.text = "지금은 사용할 수 없습니다. HP/ST가 최대치인지 확인하세요.";
                Refresh();
                return;
            }
            Refresh();
        }
    }
}
