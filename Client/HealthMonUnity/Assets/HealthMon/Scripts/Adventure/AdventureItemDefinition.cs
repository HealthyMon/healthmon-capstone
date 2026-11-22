using System;
using System.Collections.Generic;
using UnityEngine;

public enum AdventureItemUsage { ExplorationOnly, BattleOnly, Both }

[Serializable]
public class AdventureItemEffect
{
    public AdventureStatType stat;
    public float amount;
}

[CreateAssetMenu(fileName = "Item_New", menuName = "HealthMon/Adventure/Item Definition")]
public class AdventureItemDefinition : ScriptableObject
{
    public string itemId;
    public string itemName;
    [TextArea] public string description;
    public Sprite icon;
    public AdventureItemUsage usage = AdventureItemUsage.Both;
    public bool consumable = true;
    public List<AdventureItemEffect> effects = new List<AdventureItemEffect>();

    public bool CanUse(bool inBattle)
    {
        return usage == AdventureItemUsage.Both ||
               (inBattle ? usage == AdventureItemUsage.BattleOnly : usage == AdventureItemUsage.ExplorationOnly);
    }
}
