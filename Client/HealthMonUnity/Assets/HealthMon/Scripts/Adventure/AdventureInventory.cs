using System;
using System.Collections.Generic;
using UnityEngine;

// One component per adventure run. Stores only IDs and counts in save data.
public class AdventureInventory : MonoBehaviour
{
    [SerializeField] private AdventureItemDatabase database;
    [SerializeField] private AdventurePlayerStats playerStats;
    [SerializeField] private AdventureManager adventureManager;
    private readonly List<AdventureItemData> owned = new List<AdventureItemData>();

    public event Action InventoryChanged;
    public AdventureItemDatabase Database => database;

    private void Awake()
    {
        if (playerStats == null) playerStats = GetComponent<AdventurePlayerStats>();
        if (adventureManager == null) adventureManager = GetComponent<AdventureManager>();
    }

    public void Clear()
    {
        owned.Clear();
        InventoryChanged?.Invoke();
    }

    public int GetCount(string itemId)
    {
        var entry = owned.Find(x => x.itemId == itemId);
        return entry == null ? 0 : entry.count;
    }

    public bool AddItem(string itemId, int count = 1)
    {
        if (count <= 0 || database == null || database.Find(itemId) == null) return false;
        var entry = owned.Find(x => x.itemId == itemId);
        if (entry == null)
        {
            entry = new AdventureItemData { itemId = itemId, count = 0 };
            owned.Add(entry);
        }
        if (entry.count > int.MaxValue - count) return false;
        entry.count += count;
        InventoryChanged?.Invoke();
        return true;
    }

    public bool RemoveItem(string itemId, int count = 1)
    {
        if (count <= 0) return false;
        var entry = owned.Find(x => x.itemId == itemId);
        if (entry == null || entry.count < count) return false;
        entry.count -= count;
        if (entry.count == 0) owned.Remove(entry);
        InventoryChanged?.Invoke();
        return true;
    }

    public List<AdventureItemData> CreateSnapshot()
    {
        var result = new List<AdventureItemData>();
        foreach (var x in owned)
            result.Add(new AdventureItemData { itemId = x.itemId, count = x.count });
        return result;
    }

    public bool RestoreSnapshot(List<AdventureItemData> data)
    {
        if (data == null || database == null) return false;
        var seen = new HashSet<string>();
        foreach (var x in data)
            if (x == null || x.count <= 0 || database.Find(x.itemId) == null || !seen.Add(x.itemId))
                return false;
        owned.Clear();
        foreach (var x in data)
            owned.Add(new AdventureItemData { itemId = x.itemId, count = x.count });
        InventoryChanged?.Invoke();
        return true;
    }

    // Exploration use only. Battle use is performed by BattleManager on the player's action turn.
    public bool TryUseInExploration(string itemId)
    {
        if (adventureManager == null ||
            (adventureManager.State != ExplorationState.Exploring &&
             adventureManager.State != ExplorationState.Resting) ||
            !adventureManager.CanUseExplorationItem) return false;
        if (database == null || playerStats == null || !playerStats.IsInitialized || !playerStats.IsAlive || GetCount(itemId) <= 0)
            return false;
        var item = database.Find(itemId);
        if (item == null || !item.CanUse(false) || !item.consumable || item.effects == null || item.effects.Count == 0)
            return false;
        bool hasEffect = false;
        foreach (var effect in item.effects)
        {
            if (effect == null || !IsValidEffect(effect) || !CanChangeAdventureStat(effect)) return false;
            hasEffect = true;
        }
        if (!hasEffect) return false;
        foreach (var effect in item.effects) playerStats.ModifyStat(effect.stat, effect.amount);
        RemoveItem(itemId);
        Debug.Log("[Inventory] Exploration used " + itemId);
        return true;
    }

    private bool CanChangeAdventureStat(AdventureItemEffect effect)
    {
        float now = playerStats.GetStatValue(effect.stat);
        float amount = effect.stat == AdventureStatType.ST || effect.stat == AdventureStatType.MaxST
            ? effect.amount : Mathf.RoundToInt(effect.amount);
        if (Mathf.Approximately(amount, 0)) return false;
        if (amount > 0 && effect.stat == AdventureStatType.HP && now >= playerStats.MaxHP) return false;
        if (amount > 0 && effect.stat == AdventureStatType.ST && now >= playerStats.MaxST) return false;
        if (amount < 0 && (effect.stat == AdventureStatType.HP || effect.stat == AdventureStatType.ST) && now <= 0) return false;
        return true;
    }

    private static bool IsValidEffect(AdventureItemEffect effect)
    {
        return !float.IsNaN(effect.amount) && !float.IsInfinity(effect.amount) &&
               !Mathf.Approximately(effect.amount, 0);
    }

    // Used by BattleManager.PlayerItem; use consumes the item after validating the effects.
    public bool TryUseInBattle(string itemId, BattleUnit target)
    {
        if (target == null || !target.IsAlive || database == null || GetCount(itemId) <= 0) return false;
        var item = database.Find(itemId);
        if (item == null || !item.CanUse(true) || !item.consumable || item.effects == null || item.effects.Count == 0)
            return false;
        foreach (var effect in item.effects)
            if (effect == null || !IsValidEffect(effect) || !CanApplyBattleEffect(target, effect)) return false;
        foreach (var effect in item.effects) ApplyBattleEffect(target, effect);
        RemoveItem(itemId);
        Debug.Log("[Inventory] Battle used " + itemId);
        return true;
    }

    private static bool CanApplyBattleEffect(BattleUnit unit, AdventureItemEffect e)
    {
        if (e.stat == AdventureStatType.HP && e.amount > 0 && unit.currentHP >= unit.maxHP) return false;
        if (e.stat == AdventureStatType.ST && e.amount > 0 && unit.currentST >= unit.maxST) return false;
        return true;
    }

    private static void ApplyBattleEffect(BattleUnit u, AdventureItemEffect e)
    {
        int n = Mathf.RoundToInt(e.amount);
        switch (e.stat)
        {
            case AdventureStatType.HP: u.currentHP = Mathf.Clamp(u.currentHP + n, 0, u.maxHP); break;
            case AdventureStatType.MaxHP: u.maxHP = Mathf.Max(1, u.maxHP + n); u.currentHP = Mathf.Min(u.currentHP, u.maxHP); break;
            case AdventureStatType.ST: u.currentST = Mathf.Clamp(u.currentST + e.amount, 0f, u.maxST); break;
            case AdventureStatType.MaxST: u.maxST = Mathf.Max(.1f, u.maxST + e.amount); u.currentST = Mathf.Min(u.currentST, u.maxST); break;
            case AdventureStatType.ATK: u.ATK = Mathf.Max(0, u.ATK + n); break;
            case AdventureStatType.DEF: u.DEF = Mathf.Max(0, u.DEF + n); break;
            case AdventureStatType.RES: u.RES = Mathf.Max(0, u.RES + n); break;
            case AdventureStatType.SPD: u.SPD = Mathf.Max(1, u.SPD + n); break;
            case AdventureStatType.LUK: u.LUK = Mathf.Max(0, u.LUK + n); break;
        }
    }
}
