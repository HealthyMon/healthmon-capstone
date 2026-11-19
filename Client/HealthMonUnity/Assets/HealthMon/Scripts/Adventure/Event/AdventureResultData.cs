using System;
using System.Collections.Generic;

public enum AdventureEndReason
{
    Voluntary,
    Defeat
}

[Serializable]
public class AdventureResultData
{
    public AdventureEndReason endReason;
    public int startFloor;
    public int reachedFloor;
    public int clearedFloors;
    public int defeatedEnemies;
    public int defeatedBosses;
    public int completedEvents;

    // Progress since this entry, not a record of rewards already granted.
    public int sessionClearedFloors;
    public int sessionDefeatedEnemies;
    public int sessionDefeatedBosses;
    public int sessionCompletedEvents;
    public float elapsedSeconds;

    // A result may have zero HP; do not validate it as a resumable checkpoint.
    public AdventureStatsData playerStats;
    public List<AdventureItemData> items = new List<AdventureItemData>();
}
