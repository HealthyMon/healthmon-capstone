using System;
using UnityEngine;

/// <summary>
/// Controls the four REAL 3D jewelry models under HealthMon_Slime/AccessoryAnchor.
/// Shared equipment/unlock state is still owned by CustomizationPrototype.
/// Saved data now includes local position, Y rotation, Z tilt and scale multiplier.
/// The existing v1 position-only save key is retained for backwards compatibility.
/// </summary>
[DisallowMultipleComponent]
public sealed class HealthMon3DJewelryRig : MonoBehaviour
{
    private static readonly string[] Names = { "목걸이", "귀걸이", "펜던트", "반지" };
    private static readonly string[] PrefabPrefixes =
        { "Jewelry_Chain", "Jewelry_Earring", "Jewelry_Pendant", "Jewelry_Ring" };
    private const string SaveKey = "HealthMon_3D_Jewelry_LocalPositions_v1";
    private static event Action TransformsSaved;

    [Header("Existing 3D jewelry under AccessoryAnchor")]
    [SerializeField] private Transform[] jewelry = new Transform[4];

    [Header("Pet body surface")]
    [SerializeField] private SphereCollider bodyCollider;
    [SerializeField, Min(0f)] private float surfaceGap = 0.012f;

    [Serializable]
    private class SavedTransforms
    {
        public Vector3[] positions = new Vector3[4];
        public bool[] hasPosition = new bool[4];
        public float[] yawDegrees = new float[4];
        public float[] rollDegrees = new float[4];
        public float[] scaleFactors = new float[4];
        public bool[] hasAppearance = new bool[4];
    }

    private SavedTransforms saved = new SavedTransforms();
    private readonly Quaternion[] baseRotations = new Quaternion[4];
    private readonly Vector3[] baseScales = new Vector3[4];
    private readonly float[] yaw = new float[4];
    private readonly float[] roll = new float[4];
    private readonly float[] scale = { 1f, 1f, 1f, 1f };
    private CustomizationPrototype customization;
    private bool initialized;

    private static bool Valid(int index) => index >= 0 && index < 4;
    public bool HasJewelry(int index) => Valid(index) && jewelry != null &&
        jewelry.Length > index && jewelry[index] != null;
    public bool IsUnlocked(int index) => Valid(index) && customization != null &&
        customization.IsUnlocked(Names[index]);
    public bool IsEquipped(int index) => Valid(index) && customization != null &&
        customization.IsEquipped(Names[index]);

    public float GetYaw(int index) => Valid(index) ? yaw[index] : 0f;
    public float GetRoll(int index) => Valid(index) ? roll[index] : 0f;
    public float GetScaleFactor(int index) => Valid(index) ? scale[index] : 1f;
    public string GetName(int index) => Valid(index) ? Names[index] : "없음";

    private void Awake()
    {
        FindParts();
        for (int i = 0; i < 4; i++)
        {
            if (!HasJewelry(i)) continue;
            baseRotations[i] = jewelry[i].localRotation;
            baseScales[i] = jewelry[i].localScale;
        }
        LoadTransforms();
        initialized = true;
    }

    private void OnEnable()
    {
        TransformsSaved -= ReloadFromOtherRig;
        TransformsSaved += ReloadFromOtherRig;
        if (!initialized) return;
        // A previously inactive preview/Home/AR pet must read the latest saved outfit.
        LoadTransforms();
        Connect();
        RefreshVisible();
    }

    private void Start()
    {
        Connect();
        RefreshVisible();
    }

    private void OnDisable()
    {
        TransformsSaved -= ReloadFromOtherRig;
        if (customization != null)
            customization.OnEquippedItemChanged -= EquipmentChanged;
        customization = null;
    }

    private void FindParts()
    {
        if (jewelry == null || jewelry.Length != 4) Array.Resize(ref jewelry, 4);
        var children = GetComponentsInChildren<Transform>(true);
        for (int i = 0; i < 4; i++)
        {
            if (jewelry[i] != null) continue;
            foreach (Transform child in children)
            {
                if (child != transform && child.name.StartsWith(PrefabPrefixes[i],
                    StringComparison.OrdinalIgnoreCase))
                {
                    jewelry[i] = child;
                    break;
                }
            }
            if (!HasJewelry(i))
                Debug.LogWarning("[Jewelry3D] Missing model: " + PrefabPrefixes[i], this);
        }
        if (bodyCollider == null) bodyCollider = GetComponent<SphereCollider>();
    }

    private static bool IsFour<T>(T[] array) => array != null && array.Length == 4;

    private void LoadTransforms()
    {
        SavedTransforms incoming = null;
        if (PlayerPrefs.HasKey(SaveKey))
        {
            try { incoming = JsonUtility.FromJson<SavedTransforms>(PlayerPrefs.GetString(SaveKey)); }
            catch (Exception error)
            {
                Debug.LogWarning("[Jewelry3D] Saved transform read failed: " + error.Message, this);
            }
        }
        saved = incoming ?? new SavedTransforms();
        if (!IsFour(saved.positions)) saved.positions = new Vector3[4];
        if (!IsFour(saved.hasPosition)) saved.hasPosition = new bool[4];
        if (!IsFour(saved.yawDegrees)) saved.yawDegrees = new float[4];
        if (!IsFour(saved.rollDegrees)) saved.rollDegrees = new float[4];
        if (!IsFour(saved.scaleFactors)) saved.scaleFactors = new float[4];
        if (!IsFour(saved.hasAppearance)) saved.hasAppearance = new bool[4];

        for (int i = 0; i < 4; i++)
        {
            yaw[i] = saved.hasAppearance[i] ? saved.yawDegrees[i] : 0f;
            roll[i] = saved.hasAppearance[i] ? saved.rollDegrees[i] : 0f;
            scale[i] = saved.hasAppearance[i] ? Mathf.Clamp(saved.scaleFactors[i], 0.4f, 2f) : 1f;
            if (!HasJewelry(i)) continue;
            if (saved.hasPosition[i]) jewelry[i].localPosition = saved.positions[i];
            ApplyAppearance(i);
        }
    }

    private void ReloadFromOtherRig()
    {
        if (!initialized) return;
        LoadTransforms();
        RefreshVisible();
    }

    private void Connect()
    {
        if (customization != null) return;
        customization = FindFirstObjectByType<CustomizationPrototype>(FindObjectsInactive.Include);
        if (customization == null) return;
        customization.OnEquippedItemChanged -= EquipmentChanged;
        customization.OnEquippedItemChanged += EquipmentChanged;
    }

    private void EquipmentChanged(string _) => RefreshVisible();

    public void RefreshVisible()
    {
        if (customization == null) Connect();
        if (customization == null) return;
        for (int i = 0; i < 4; i++)
            if (HasJewelry(i))
                jewelry[i].gameObject.SetActive(customization.IsEquipped(Names[i]));
    }

    public void SelectForCustomization(int index)
    {
        if (!Valid(index)) return;
        Connect();
        if (customization == null) return;
        switch (index)
        {
            case 0: customization.SelectNecklace(); break;
            case 1: customization.SelectEarring(); break;
            case 2: customization.SelectPendant(); break;
            case 3: customization.SelectRing(); break;
        }
    }

    private void SetEquipped(int index, bool desired)
    {
        Connect();
        if (customization == null || !IsUnlocked(index) || IsEquipped(index) == desired) return;
        SelectForCustomization(index);
        customization.EquipSelectedItem();
        RefreshVisible();
    }

    public bool EnsureEquipped(int index)
    {
        Connect();
        if (!HasJewelry(index) || !IsUnlocked(index)) return false;
        SetEquipped(index, true);
        return IsEquipped(index);
    }

    // Kept for the original button and other possible callers.
    public void Toggle(int index)
    {
        Connect();
        if (HasJewelry(index)) SetEquipped(index, !IsEquipped(index));
    }

    public bool BeginDrag(int index, out Vector3 previousLocalPosition, out bool previouslyEquipped)
    {
        previousLocalPosition = Vector3.zero;
        previouslyEquipped = false;
        Connect();
        if (!HasJewelry(index) || !IsUnlocked(index)) return false;
        previousLocalPosition = jewelry[index].localPosition;
        previouslyEquipped = IsEquipped(index);
        jewelry[index].gameObject.SetActive(true);
        return true;
    }

    public bool TryPreviewOnRay(int index, Ray ray)
    {
        if (!HasJewelry(index) || bodyCollider == null || !bodyCollider.enabled) return false;
        if (!bodyCollider.Raycast(ray, out RaycastHit hit, 10000f)) return false;
        jewelry[index].position = hit.point + hit.normal * surfaceGap;
        return true;
    }

    public bool TryPreviewAt(int index, Camera camera, Vector2 screenPosition)
    {
        return camera != null && TryPreviewOnRay(index, camera.ScreenPointToRay(screenPosition));
    }

    public void FinishDragOnRay(int index, Ray ray, Vector3 previousLocalPosition,
        bool previouslyEquipped)
    {
        if (!HasJewelry(index)) return;
        if (!TryPreviewOnRay(index, ray))
        {
            CancelDrag(index, previousLocalPosition, previouslyEquipped);
            return;
        }
        saved.positions[index] = jewelry[index].localPosition;
        saved.hasPosition[index] = true;
        SetEquipped(index, true);
        SaveAll();
        Debug.Log("[Jewelry3D] Saved position: " + Names[index], this);
    }

    public void FinishDrag(int index, Camera camera, Vector2 screenPosition,
        Vector3 previousLocalPosition, bool previouslyEquipped)
    {
        if (camera == null) { CancelDrag(index, previousLocalPosition, previouslyEquipped); return; }
        FinishDragOnRay(index, camera.ScreenPointToRay(screenPosition), previousLocalPosition, previouslyEquipped);
    }

    public void CancelDrag(int index, Vector3 previousLocalPosition, bool previouslyEquipped)
    {
        if (!HasJewelry(index)) return;
        jewelry[index].localPosition = previousLocalPosition;
        SetEquipped(index, previouslyEquipped);
        RefreshVisible();
    }

    public void PreviewYaw(int index, float degrees)
    {
        if (!HasJewelry(index)) return;
        yaw[index] = Mathf.Clamp(degrees, -180f, 180f);
        ApplyAppearance(index);
    }

    public void PreviewRoll(int index, float degrees)
    {
        if (!HasJewelry(index)) return;
        roll[index] = Mathf.Clamp(degrees, -180f, 180f);
        ApplyAppearance(index);
    }

    public void PreviewScale(int index, float factor)
    {
        if (!HasJewelry(index)) return;
        scale[index] = Mathf.Clamp(factor, 0.4f, 2f);
        ApplyAppearance(index);
    }

    private void ApplyAppearance(int index)
    {
        if (!HasJewelry(index)) return;
        jewelry[index].localRotation = Quaternion.Euler(0f, yaw[index], roll[index]) * baseRotations[index];
        jewelry[index].localScale = baseScales[index] * scale[index];
    }

    public void ResetAppearance(int index)
    {
        if (!HasJewelry(index)) return;
        yaw[index] = 0f;
        roll[index] = 0f;
        scale[index] = 1f;
        ApplyAppearance(index);
        CommitAppearance(index);
    }

    public void CommitAppearance(int index)
    {
        if (!HasJewelry(index)) return;
        SaveAll();
        Debug.Log("[Jewelry3D] Saved rotation/scale: " + Names[index], this);
    }

    private void SaveAll()
    {
        for (int i = 0; i < 4; i++)
        {
            saved.yawDegrees[i] = yaw[i];
            saved.rollDegrees[i] = roll[i];
            saved.scaleFactors[i] = scale[i];
            saved.hasAppearance[i] = true;
        }
        PlayerPrefs.SetString(SaveKey, JsonUtility.ToJson(saved));
        PlayerPrefs.Save();
        TransformsSaved?.Invoke();
    }

    public bool TryGetJewelryWorldCenter(int index, out Vector3 center)
    {
        center = Vector3.zero;
        if (!HasJewelry(index)) return false;
        Renderer[] renderers = jewelry[index].GetComponentsInChildren<Renderer>(true);
        bool found = false;
        Bounds bounds = new Bounds();
        foreach (Renderer renderer in renderers)
        {
            if (renderer == null) continue;
            if (!found) { bounds = renderer.bounds; found = true; }
            else bounds.Encapsulate(renderer.bounds);
        }
        center = found ? bounds.center : jewelry[index].position;
        return true;
    }
}
