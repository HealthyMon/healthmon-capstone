using System;
using System.Collections.Generic;
using UnityEngine;

public enum AdventureSpecialOutcomeKind { None, StatChange, Item }

[Serializable]
public class AdventureSpecialOutcome
{
    [Min(0)] public int weight = 1;
    public AdventureSpecialOutcomeKind kind;
    public AdventureStatType stat = AdventureStatType.HP;
    public float amount;
    public string itemId;
    [Min(1)] public int count = 1;
    [TextArea(1, 3)] public string resultText;
}

[Serializable]
public class AdventureSpecialChoice
{
    public string text;
    public List<AdventureSpecialOutcome> outcomes = new List<AdventureSpecialOutcome>();

    public bool TryRoll(out AdventureSpecialOutcome selected)
    {
        selected = null;
        if (outcomes == null) return false;
        int total = 0;
        foreach (var outcome in outcomes)
            if (outcome != null && outcome.weight > 0) total += outcome.weight;
        if (total <= 0) return false;
        int roll = UnityEngine.Random.Range(0, total);
        foreach (var outcome in outcomes)
        {
            if (outcome == null || outcome.weight <= 0) continue;
            if (roll < outcome.weight) { selected = outcome; return true; }
            roll -= outcome.weight;
        }
        return false;
    }
}

[Serializable]
public class AdventureSpecialEvent
{
    public string title;
    [TextArea(2, 4)] public string description;
    // 1~3개 선택지, 지나가기는 UI에서 별도 제공
    public List<AdventureSpecialChoice> choices = new List<AdventureSpecialChoice>();
}

[CreateAssetMenu(fileName = "AdventureSpecialDatabase", menuName = "HealthMon/Adventure/Special Event Database")]
public class AdventureSpecialDatabase : ScriptableObject
{
    [SerializeField] private List<AdventureSpecialEvent> events = new List<AdventureSpecialEvent>();

    public bool TryRandom(out AdventureSpecialEvent selected)
    {
        var valid = new List<AdventureSpecialEvent>();
        foreach (var evt in events)
        {
            if (evt == null || string.IsNullOrWhiteSpace(evt.title) || evt.choices == null ||
                evt.choices.Count < 1 || evt.choices.Count > 3) continue;
            bool allValid = true;
            foreach (var choice in evt.choices)
            {
                if (choice == null || string.IsNullOrWhiteSpace(choice.text) || choice.outcomes == null ||
                    !choice.outcomes.Exists(o => o != null && o.weight > 0)) { allValid = false; break; }
            }
            if (allValid) valid.Add(evt);
        }
        selected = valid.Count == 0 ? null : valid[UnityEngine.Random.Range(0, valid.Count)];
        return selected != null;
    }
}
