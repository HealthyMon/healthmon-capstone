using System;
using System.Collections.Generic;

[Serializable]
public class AdventureSaveData
{
    public int version = 1;
    public int checkpointFloor;
    public int clearedFloors;
    public int defeatedEnemies;
    public int defeatedBosses;
    public int completedEvents;
    public AdventureStatsData playerStats;
    public List<AdventureItemData> items = new();
    public string savedAt;

    public bool IsValid()
    {
        if (version != 1 || checkpointFloor <= 0 || checkpointFloor % 10 != 0 ||
            clearedFloors != checkpointFloor || defeatedEnemies < 0 ||
            defeatedBosses != checkpointFloor / 10 || completedEvents < 0 ||
            completedEvents > clearedFloors || defeatedEnemies + defeatedBosses > completedEvents ||
            playerStats == null || !playerStats.IsValid() || items == null)
            return false;
        foreach (var item in items)
            if (item == null || string.IsNullOrWhiteSpace(item.itemId) || item.count <= 0)
                return false;
        return true;
    }
}

[Serializable]
public class AdventureStatsData
{
    public int maxHP, currentHP;
    public float maxST, currentST;
    public int ATK, DEF, RES, SPD, LUK;

    public bool IsValid()
    {
        return maxHP > 0 && currentHP > 0 && currentHP <= maxHP &&
            !float.IsNaN(maxST) && !float.IsInfinity(maxST) &&
            !float.IsNaN(currentST) && !float.IsInfinity(currentST) &&
            maxST > 0 && currentST >= 0 && currentST <= maxST;
    }
}

[Serializable]
public class AdventureItemData
{
    public string itemId;
    public int count;
}
