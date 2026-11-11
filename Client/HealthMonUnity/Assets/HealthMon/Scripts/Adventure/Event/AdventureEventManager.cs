using System;
using System.Collections.Generic;
using UnityEngine;

// 기존 인스펙터 enum 직렬화 값(0~4)을 유지하기 위해 EliteBattle은 마지막에 추가.
public enum AdventureEventType
{
    Battle,
    Reward,
    Rest,
    Quiz,
    Special,
    EliteBattle
}

[Serializable]
public class AdventureEventData
{
    public AdventureEventType eventType;
    [Min(0)] public int weight = 10;
}

public class AdventureEventManager : MonoBehaviour
{
    [Header("일반층 이벤트 가중치")]
    [SerializeField] private List<AdventureEventData> eventList = new()
    {
        new AdventureEventData { eventType = AdventureEventType.Battle, weight = 40 },
        new AdventureEventData { eventType = AdventureEventType.Reward, weight = 0 },
        new AdventureEventData { eventType = AdventureEventType.Rest, weight = 0 },
        new AdventureEventData { eventType = AdventureEventType.Quiz, weight = 0 },
        new AdventureEventData { eventType = AdventureEventType.Special, weight = 0 }
    };

    public AdventureEventType? GenerateEvent(int floor)
    {
        if (floor <= 0) return null;
        if (floor % 10 == 0) return AdventureEventType.EliteBattle;

        int total = 0;
        foreach (var item in eventList)
        {
            if (item != null && item.eventType != AdventureEventType.EliteBattle && item.weight > 0)
                total += item.weight;
        }
        if (total <= 0)
        {
            Debug.LogWarning("[Exploration] 유효한 이벤트 가중치가 없습니다.");
            return null;
        }

        int roll = UnityEngine.Random.Range(0, total);
        foreach (var item in eventList)
        {
            if (item == null || item.eventType == AdventureEventType.EliteBattle || item.weight <= 0)
                continue;
            roll -= item.weight;
            if (roll < 0) return item.eventType;
        }
        return null;
    }
}
