
using System;
using System.Collections.Generic;
using UnityEngine;

public enum ExplorationEventType
{
    Battle,
    Reward,
    Rest,
    Quiz,
    Special
}

[Serializable]
public class ExplorationEventData
{
    public ExplorationEventType eventType;

    [Min(0)]
    public int weight = 10;
}

public class ExplorationEventManager : MonoBehaviour
{
    [Header("Event Probability")]
    [SerializeField]
    private List<ExplorationEventData> eventList = new()
    {
        new ExplorationEventData
        {
            eventType = ExplorationEventType.Battle,
            weight = 40
        },
        new ExplorationEventData
        {
            eventType = ExplorationEventType.Reward,
            weight = 25
        },
        new ExplorationEventData
        {
            eventType = ExplorationEventType.Rest,
            weight = 15
        },
        new ExplorationEventData
        {
            eventType = ExplorationEventType.Quiz,
            weight = 15
        },
        new ExplorationEventData
        {
            eventType = ExplorationEventType.Special,
            weight = 5
        }
    };

    public ExplorationEventType? GenerateEvent()
    {
        int totalWeight = 0;

        foreach (var eventData in eventList)
        {
            if (eventData != null && eventData.weight > 0)
                totalWeight += eventData.weight;
        }

        if (totalWeight <= 0)
        {
            Debug.LogWarning(
                "[Exploration] 발생 가능한 이벤트가 없습니다."
            );

            return null;
        }

        int randomValue = UnityEngine.Random.Range(0, totalWeight);

        foreach (var eventData in eventList)
        {
            if (eventData == null || eventData.weight <= 0)
                continue;

            randomValue -= eventData.weight;

            if (randomValue < 0)
            {
                return eventData.eventType;
            }
        }

        return null;
    }
}
