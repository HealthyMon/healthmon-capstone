using System;
using System.Collections.Generic;
using UnityEngine;

public enum HealthMonShopCategory { Accessory, Character }

[Serializable]
public class HealthMonShopItem
{
    public string itemId;
    public string displayName;
    [TextArea(2, 4)] public string description;
    public HealthMonShopCategory category;
    [Min(0)] public int displayCoinPrice;
    public Sprite icon;
    public bool includedByDefault;
    public bool featured;
    // Original customization system: necklace, earring, pendant, ring (Korean names).
    public string jewelryName;
    // Actual source prefab for shop product; attached automatically by offline catalog importer.
    public GameObject productPrefab;
}

[CreateAssetMenu(menuName = "HealthMon/Shop/Catalog", fileName = "HealthMonShopCatalog")]
public class HealthMonShopCatalog : ScriptableObject
{
    public List<HealthMonShopItem> items = new List<HealthMonShopItem>();
}
