using System;
using System.Collections.Generic;
using UnityEngine;

[CreateAssetMenu(menuName = "HealthMon/Character Roster Catalog")]
public sealed class HealthMonCharacterRosterAsset : ScriptableObject
{
    [Serializable]
    public class Entry
    {
        public string id;
        public string title;
        public string description;
        public string shopItemId;
        public GameObject visualPrefab;
        public Sprite portrait;
        public bool includedByDefault;
    }
    public List<Entry> entries = new List<Entry>();
}
