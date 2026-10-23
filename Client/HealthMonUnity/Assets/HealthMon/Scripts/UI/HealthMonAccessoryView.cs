using UnityEngine;

/// <summary>
/// Applied to each AR-spawned HealthMon_Slime.
/// Each jewelry object is toggled independently based on saved equipment state.
/// </summary>
public class HealthMonAccessoryView : MonoBehaviour
{
    [Header("3D Jewelry Objects")]
    [SerializeField] private GameObject necklaceAccessory;
    [SerializeField] private GameObject earringAccessory;
    [SerializeField] private GameObject pendantAccessory;
    [SerializeField] private GameObject ringAccessory;

    private CustomizationPrototype customization;

    public bool ContainsAccessory(Transform visual)
    {
        foreach (var accessory in new[] { necklaceAccessory, earringAccessory, pendantAccessory, ringAccessory })
            if (accessory != null && visual.IsChildOf(accessory.transform)) return true;
        return false;
    }

    private void OnEnable()
    {
        ConnectToCustomization();
        RefreshEquipment();
    }

    private void Start()
    {
        // Managers may Awake in a different order than the spawned character.
        ConnectToCustomization();
        RefreshEquipment();
    }

    private void OnDisable()
    {
        if (customization != null)
            customization.OnEquippedItemChanged -= OnAnyItemChanged;
        customization = null;
    }

    private void ConnectToCustomization()
    {
        if (customization != null) return;
        customization = FindFirstObjectByType<CustomizationPrototype>();
        if (customization != null)
            customization.OnEquippedItemChanged += OnAnyItemChanged;
    }

    private void OnAnyItemChanged(string changedItem)
    {
        RefreshEquipment();
    }

    private void RefreshEquipment()
    {
        SetActiveIfPresent(necklaceAccessory, customization != null && customization.IsEquipped("목걸이"));
        SetActiveIfPresent(earringAccessory, customization != null && customization.IsEquipped("귀걸이"));
        SetActiveIfPresent(pendantAccessory, customization != null && customization.IsEquipped("펜던트"));
        SetActiveIfPresent(ringAccessory, customization != null && customization.IsEquipped("반지"));
    }

    private static void SetActiveIfPresent(GameObject target, bool enabled)
    {
        if (target != null && target.activeSelf != enabled)
            target.SetActive(enabled);
    }
}
