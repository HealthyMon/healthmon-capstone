using System;
using System.Collections.Generic;
using UnityEngine;

[Serializable]
public class AdventureQuizQuestion
{
    [TextArea(2, 4)] public string question;
    public string[] choices = new string[4];
    [Range(0, 3)] public int correctIndex;
    [TextArea(1, 3)] public string explanation;
}

[CreateAssetMenu(fileName = "AdventureQuizDatabase", menuName = "HealthMon/Adventure/Quiz Database")]
public class AdventureQuizDatabase : ScriptableObject
{
    [SerializeField] private List<AdventureQuizQuestion> questions = new List<AdventureQuizQuestion>();

    public bool TryRandom(out AdventureQuizQuestion question)
    {
        var valid = new List<AdventureQuizQuestion>();
        foreach (var q in questions)
        {
            if (q == null || string.IsNullOrWhiteSpace(q.question) || q.choices == null ||
                q.choices.Length != 4 || q.correctIndex < 0 || q.correctIndex > 3) continue;
            bool ok = true;
            foreach (var choice in q.choices)
                if (string.IsNullOrWhiteSpace(choice)) { ok = false; break; }
            if (ok) valid.Add(q);
        }
        if (valid.Count == 0) { question = null; return false; }
        question = valid[UnityEngine.Random.Range(0, valid.Count)];
        return true;
    }
}
