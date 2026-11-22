using System.Collections.Generic;
using UnityEngine;

[CreateAssetMenu(fileName = "AdventureItemDatabase", menuName = "HealthMon/Adventure/Item Database")]
public class AdventureItemDatabase : ScriptableObject
{
    [SerializeField] private List<AdventureItemDefinition> items = new List<AdventureItemDefinition>();
    private Dictionary<string, AdventureItemDefinition> lookup;

    public AdventureItemDefinition Find(string id)
    {
        if (string.IsNullOrWhiteSpace(id)) return null;
        if (lookup == null) Rebuild();
        lookup.TryGetValue(id, out var item);
        return item;
    }

    private void OnEnable() { lookup = null; }
    private void OnValidate() { lookup = null; }

    private void Rebuild()
    {
        lookup = new Dictionary<string, AdventureItemDefinition>();
        foreach (var item in items)
        {
            if (item == null || string.IsNullOrWhiteSpace(item.itemId)) continue;
            if (lookup.ContainsKey(item.itemId))
            {
                Debug.LogError("[ItemDB] Duplicate itemId: " + item.itemId, this);
                continue;
            }
            lookup.Add(item.itemId, item);
        }
    }
}
