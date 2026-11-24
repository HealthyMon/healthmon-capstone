using System;
using System.Collections.Generic;
using Healthmon.Common;
using TMPro;
using UnityEngine;
using UnityEngine.Serialization;
using UnityEngine.UI;

/// <summary>
/// HealthMon jewelry collection with four independent equipment slots.
/// Preserves existing Inspector references, quest reward methods and admin methods.
/// Migrates the prior v2 single-equipped save and the original v1 save to v3.
/// </summary>
public class CustomizationPrototype : MonoBehaviour
{
    [Header("Collection")]
    [SerializeField] private TMP_Text collectionCountText;

    [FormerlySerializedAs("badgeLockText")]
    [SerializeField] private TMP_Text necklaceLockText;
    [FormerlySerializedAs("ribbonLockText")]
    [SerializeField] private TMP_Text earringLockText;
    [FormerlySerializedAs("glassesLockText")]
    [SerializeField] private TMP_Text pendantLockText;
    [FormerlySerializedAs("capLockText")]
    [SerializeField] private TMP_Text ringLockText;

    [Header("Collection Selected Item")]
    [SerializeField] private TMP_Text selectedItemNameText;
    [SerializeField] private TMP_Text selectedItemDescriptionText;
    [SerializeField] private Button customizeButton;

    [Header("Customization")]
    [SerializeField] private TMP_Text customizeItemNameText;
    [SerializeField] private TMP_Text customizeDescriptionText;
    [SerializeField] private TMP_Text equippedItemText;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private Button equipButton;

    // Optional: drag the child TMP text of the existing equip button here.
    [Header("Optional Equip Button Label")]
    [SerializeField] private TMP_Text equipButtonText;

    private const string SaveKey = "HealthMon_Customization_Jewelry_v3";
    private const string PreviousKey = "HealthMon_Customization_Jewelry_v2";
    private const string LegacyKey = "HealthMon_Customization_Save_v1";

    private bool necklaceUnlocked = true;
    private bool earringUnlocked;
    private bool pendantUnlocked;
    private bool ringUnlocked;
    private readonly HashSet<string> serverJewelry = new HashSet<string>();

    // Server entitlements are an in-memory projection, scoped by the shop
    // connection. Never merge them into the device's offline demo save.
    public void ApplyServerShopInventory(IEnumerable<string> slots)
    {
        serverJewelry.Clear();
        if (slots != null) foreach (string slot in slots) serverJewelry.Add(slot);
        RefreshUI();
        OnEquippedItemChanged?.Invoke(selectedItem);
    }

    // Each accessory can be equipped at the same time.
    private bool necklaceEquipped;
    private bool earringEquipped;
    private bool pendantEquipped;
    private bool ringEquipped;

    private string selectedItem = "목걸이";

    // Legacy single-item access for any older script still reading this property.
    // New 3D code should call IsEquipped(itemName), not EquippedItem.
    public string EquippedItem
    {
        get
        {
            if (IsEquipped("목걸이")) return "목걸이";
            if (IsEquipped("귀걸이")) return "귀걸이";
            if (IsEquipped("펜던트")) return "펜던트";
            if (IsEquipped("반지")) return "반지";
            return "없음";
        }
    }

    // Same event signature as prior versions for Inspector/external code compatibility.
    // Its argument is the item that just changed; inspect IsEquipped() for all states.
    public event Action<string> OnEquippedItemChanged;

    [Serializable]
    private class JewelrySaveDataV3
    {
        public bool necklaceUnlocked;
        public bool earringUnlocked;
        public bool pendantUnlocked;
        public bool ringUnlocked;
        public bool necklaceEquipped;
        public bool earringEquipped;
        public bool pendantEquipped;
        public bool ringEquipped;
    }

    [Serializable]
    private class JewelrySaveDataV2
    {
        public bool necklaceUnlocked;
        public bool earringUnlocked;
        public bool pendantUnlocked;
        public bool ringUnlocked;
        public string equippedItem;
    }

    [Serializable]
    private class LegacySaveDataV1
    {
        public bool ribbonUnlocked;
        public bool glassesUnlocked;
        public bool capUnlocked;
        public string equippedItem;
    }

    private void Awake()
    {
        LoadCustomizationData();
    }

    private void Start()
    {
        LayoutDetails();
        SelectNecklace();
        RefreshUI();
    }

    private void LayoutDetails()
    {
        foreach (var locked in new[] { necklaceLockText, earringLockText, pendantLockText, ringLockText })
        {
            if (locked == null) continue;
            HealthMonUILayout.Text(locked, .08f, .10f, .92f, .25f, 25);
            HealthMonUILayout.Text(locked.transform.parent.Find("ItemNameText")?.GetComponent<TMP_Text>(), .08f, .29f, .92f, .45f, 30);
        }
        if (selectedItemNameText != null)
        {
            var panel = selectedItemNameText.transform.parent as RectTransform;
            var collection = panel.parent;
            var grid = collection.Find("ItemGrid");
            if (grid != null) foreach (var card in grid.GetComponentsInChildren<Button>(true))
            {
                HealthMonUILayout.Text(card.transform.Find("ItemNameText")?.GetComponent<TMP_Text>(), .08f, .29f, .92f, .45f, 30);
                HealthMonUILayout.Text(card.transform.Find("LockText")?.GetComponent<TMP_Text>(), .08f, .10f, .92f, .25f, 25);
            }
            var guide = collection.Find("GuideText")?.GetComponent<TMP_Text>();
            HealthMonUILayout.Text(guide, .12f, .373f, .88f, .393f, 24);
            HealthMonUILayout.Place(grid as RectTransform, .04f, .405f, .96f, .79f);
            if (guide != null) guide.text = "장신구를 선택해 상세 정보 확인";
            HealthMonUILayout.Place(panel, .09f, .17f, .91f, .36f);
            HealthMonUILayout.Text(selectedItemNameText, .08f, .69f, .73f, .90f, 35);
            HealthMonUILayout.Text(selectedItemDescriptionText, .08f, .39f, .73f, .64f, 28);
            HealthMonUILayout.Place(panel.Find("SelectedItemJewelryIcon") as RectTransform, .77f, .40f, .92f, .83f);
            if (customizeButton != null) HealthMonUILayout.Place(customizeButton.transform as RectTransform, .27f, .10f, .73f, .32f);
        }
        HealthMonUILayout.Text(customizeItemNameText, .08f, .74f, .73f, .91f, 38);
        HealthMonUILayout.Text(customizeDescriptionText, .08f, .49f, .73f, .71f, 30);
        if (customizeItemNameText != null)
            HealthMonUILayout.Place(customizeItemNameText.transform.parent.Find("SelectedItemJewelryIcon") as RectTransform, .77f, .51f, .92f, .86f);
        if (equipButton != null) HealthMonUILayout.Place(equipButton.transform as RectTransform, .30f, .21f, .70f, .44f);
        HealthMonUILayout.Text(statusText, .08f, .06f, .92f, .18f, 26);
        if (statusText != null) statusText.text = "장착할 아이템 선택";
        HealthMonUILayout.Text(equippedItemText, .08f, .05f, .92f, .15f, 28);
        if (equippedItemText == null) return;
        var preview = equippedItemText.transform.parent;
        var image = preview.Find("PetPreviewImage")?.GetComponent<RawImage>();
        if (image == null || image.texture == null) return;
        var placeholder = preview.Find("PreviewText");
        if (placeholder != null) placeholder.gameObject.SetActive(false);
        // Keep the render texture's proportions inside the preview card.
        var frame = new GameObject("FittedPetPreview", typeof(RectTransform)).GetComponent<RectTransform>();
        frame.SetParent(preview, false);
        HealthMonUILayout.Place(frame, .07f, .18f, .93f, .93f);
        image.transform.SetParent(frame, false);
        var fitter = image.GetComponent<AspectRatioFitter>() ?? image.gameObject.AddComponent<AspectRatioFitter>();
        fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;
        fitter.aspectRatio = (float)image.texture.width / image.texture.height;
        Camera previewCamera = null;
        GameObject previewRoot = null;
        // The preview gate disables its camera while the home page is open.
        // GameObject.Find therefore misses it during this component's Start.
        foreach (var candidate in FindObjectsByType<Camera>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (candidate.name == "PetPreviewCamera") { previewCamera = candidate; break; }
        foreach (var candidate in FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (candidate.name == "PetPreviewRoot") { previewRoot = candidate.gameObject; break; }
        if (previewCamera != null && previewRoot != null)
        {
            var framing = previewCamera.GetComponent<HealthMonPreviewFraming>() ?? previewCamera.gameObject.AddComponent<HealthMonPreviewFraming>();
            framing.target = previewRoot.transform;
        }
    }

    public void SelectNecklace() => SelectItem("목걸이", "기본 지급 장신구 · 목걸이 슬롯", IsUnlocked("목걸이"));
    public void SelectEarring() => SelectItem("귀걸이", "상점 획득 장신구 · 귀걸이 슬롯", IsUnlocked("귀걸이"));
    public void SelectPendant() => SelectItem("펜던트", "상점 획득 장신구 · 펜던트 슬롯", IsUnlocked("펜던트"));
    public void SelectRing() => SelectItem("반지", "상점 획득 장신구 · 반지 슬롯", IsUnlocked("반지"));

    // Old button OnClick aliases retained temporarily.
    public void SelectBadge() => SelectNecklace();
    public void SelectRibbon() => SelectEarring();
    public void SelectGlasses() => SelectPendant();
    public void SelectCap() => SelectRing();

    private void SelectItem(string itemName, string description, bool unlocked)
    {
        selectedItem = itemName;
        if (selectedItemNameText != null) selectedItemNameText.text = itemName;
        if (selectedItemDescriptionText != null)
            selectedItemDescriptionText.text = unlocked ? description : "아직 획득하지 않은 아이템입니다.";
        if (customizeButton != null) customizeButton.interactable = unlocked;
        if (customizeItemNameText != null) customizeItemNameText.text = itemName;
        if (customizeDescriptionText != null)
            customizeDescriptionText.text = unlocked ? description : "잠긴 아이템입니다.";
        RefreshEquipButton();
    }

    /// <summary>
    /// Existing EquipButton OnClick still targets this method.
    /// Pressing it again for an equipped item unequips just that slot.
    /// </summary>
    public void EquipSelectedItem()
    {
        if (!IsItemUnlocked(selectedItem)) return;

        bool nextValue = !IsEquipped(selectedItem);
        SetEquipped(selectedItem, nextValue);

        if (statusText != null)
            statusText.text = $"{selectedItem} {(nextValue ? "장착 완료" : "장착 해제")}";

        SaveCustomizationData();
        RefreshUI();
        OnEquippedItemChanged?.Invoke(selectedItem);
        Debug.Log($"[Customization] {selectedItem} {(nextValue ? "장착" : "해제")}");
    }

    public bool IsEquipped(string itemName)
    {
        if (!IsItemUnlocked(itemName)) return false;
        switch (itemName)
        {
            case "목걸이": return necklaceEquipped;
            case "귀걸이": return earringEquipped;
            case "펜던트": return pendantEquipped;
            case "반지": return ringEquipped;
            default: return false;
        }
    }

    // Public read-only access for accessory management UI.
    public bool IsUnlocked(string itemName)
    {
        return IsItemUnlocked(itemName);
    }

    private void SetEquipped(string itemName, bool value)
    {
        switch (itemName)
        {
            case "목걸이": necklaceEquipped = value; break;
            case "귀걸이": earringEquipped = value; break;
            case "펜던트": pendantEquipped = value; break;
            case "반지": ringEquipped = value; break;
        }
    }

    private bool IsItemUnlocked(string itemName)
    {
        if (CommonServerConnection.UsesServerAuthority)
            return itemName == "목걸이" || serverJewelry.Contains(itemName);
        switch (itemName)
        {
            case "목걸이": return necklaceUnlocked;
            case "귀걸이": return earringUnlocked;
            case "펜던트": return pendantUnlocked;
            case "반지": return ringUnlocked;
            default: return false;
        }
    }

    public void UnlockEarring() { if (earringUnlocked) return; earringUnlocked = true; SaveCustomizationData(); RefreshUI(); }
    public void UnlockPendant() { if (pendantUnlocked) return; pendantUnlocked = true; SaveCustomizationData(); RefreshUI(); }
    public void UnlockRing() { if (ringUnlocked) return; ringUnlocked = true; SaveCustomizationData(); RefreshUI(); }

    // Preserve QuestPrototype reward calls: Food -> Earring, Dialogue -> Pendant, Walk -> Ring.
    public void UnlockRibbon() => UnlockEarring();
    public void UnlockGlasses() => UnlockPendant();
    public void UnlockCap() => UnlockRing();

    // Preserve HealthMonAdminPanel's call.
    public void UnlockAllItems()
    {
        necklaceUnlocked = true;
        earringUnlocked = true;
        pendantUnlocked = true;
        ringUnlocked = true;
        SaveCustomizationData();
        RefreshUI();
        Debug.Log("[Customization] 장신구 모두 해금 완료");
    }

    private void RefreshEquipButton()
    {
        bool unlocked = IsItemUnlocked(selectedItem);
        if (equipButton != null) equipButton.interactable = unlocked;
        if (equipButtonText != null)
            equipButtonText.text = unlocked ? (IsEquipped(selectedItem) ? "장착 해제" : "장착하기") : "잠김";
    }

    private void RefreshUI()
    {
        if (customizeButton != null) customizeButton.interactable = IsUnlocked(selectedItem);
        if (necklaceLockText != null) necklaceLockText.text = IsUnlocked("목걸이") ? "해금됨" : "잠김";
        if (earringLockText != null) earringLockText.text = IsUnlocked("귀걸이") ? "해금됨" : "잠김";
        if (pendantLockText != null) pendantLockText.text = IsUnlocked("펜던트") ? "해금됨" : "잠김";
        if (ringLockText != null) ringLockText.text = IsUnlocked("반지") ? "해금됨" : "잠김";

        int unlocked = (IsUnlocked("목걸이") ? 1 : 0) + (IsUnlocked("귀걸이") ? 1 : 0)
            + (IsUnlocked("펜던트") ? 1 : 0) + (IsUnlocked("반지") ? 1 : 0);
        if (collectionCountText != null) collectionCountText.text = $"{unlocked} / 4 해금";

        string names = "";
        if (IsEquipped("목걸이")) names += "목걸이, ";
        if (IsEquipped("귀걸이")) names += "귀걸이, ";
        if (IsEquipped("펜던트")) names += "펜던트, ";
        if (IsEquipped("반지")) names += "반지, ";
        if (names.Length > 0) names = names.Substring(0, names.Length - 2);
        else names = "없음";

        if (equippedItemText != null) equippedItemText.text = "현재 장착 : " + names;
        RefreshEquipButton();
    }

    private void SaveCustomizationData()
    {
        if (CommonServerConnection.UsesServerAuthority) return;
        var data = new JewelrySaveDataV3
        {
            necklaceUnlocked = necklaceUnlocked,
            earringUnlocked = earringUnlocked,
            pendantUnlocked = pendantUnlocked,
            ringUnlocked = ringUnlocked,
            necklaceEquipped = necklaceEquipped,
            earringEquipped = earringEquipped,
            pendantEquipped = pendantEquipped,
            ringEquipped = ringEquipped
        };
        PlayerPrefs.SetString(SaveKey, JsonUtility.ToJson(data));
        PlayerPrefs.Save();
        Debug.Log("[Customization] 장신구 다중 장착 데이터 저장 완료");
    }

    private void LoadCustomizationData()
    {
        try
        {
            if (PlayerPrefs.HasKey(SaveKey))
            {
                var d = JsonUtility.FromJson<JewelrySaveDataV3>(PlayerPrefs.GetString(SaveKey));
                if (d == null) return;
                necklaceUnlocked = true;
                earringUnlocked = d.earringUnlocked;
                pendantUnlocked = d.pendantUnlocked;
                ringUnlocked = d.ringUnlocked;
                necklaceEquipped = d.necklaceEquipped;
                earringEquipped = d.earringEquipped && earringUnlocked;
                pendantEquipped = d.pendantEquipped && pendantUnlocked;
                ringEquipped = d.ringEquipped && ringUnlocked;
                Debug.Log("[Customization] 다중 장착 데이터 불러오기 완료");
                return;
            }

            if (PlayerPrefs.HasKey(PreviousKey))
            {
                var d = JsonUtility.FromJson<JewelrySaveDataV2>(PlayerPrefs.GetString(PreviousKey));
                if (d == null) return;
                necklaceUnlocked = true;
                earringUnlocked = d.earringUnlocked;
                pendantUnlocked = d.pendantUnlocked;
                ringUnlocked = d.ringUnlocked;
                SetEquipped(d.equippedItem, IsItemUnlocked(d.equippedItem));
                SaveCustomizationData();
                Debug.Log("[Customization] v2 저장 데이터 → 동시 착용 v3 변환 완료");
                return;
            }

            if (PlayerPrefs.HasKey(LegacyKey))
            {
                var d = JsonUtility.FromJson<LegacySaveDataV1>(PlayerPrefs.GetString(LegacyKey));
                if (d == null) return;
                necklaceUnlocked = true;
                earringUnlocked = d.ribbonUnlocked;
                pendantUnlocked = d.glassesUnlocked;
                ringUnlocked = d.capUnlocked;
                string item = ConvertOldName(d.equippedItem);
                SetEquipped(item, IsItemUnlocked(item));
                SaveCustomizationData();
                Debug.Log("[Customization] v1 저장 데이터 → 동시 착용 v3 변환 완료");
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning("[Customization] 다중 장착 데이터 읽기 실패: " + e.Message);
        }
    }

    private static string ConvertOldName(string name)
    {
        switch (name)
        {
            case "기본 배지": return "목걸이";
            case "리본": return "귀걸이";
            case "안경": return "펜던트";
            case "운동 모자": return "반지";
            case "목걸이": return "목걸이";
            default: return "목걸이";
        }
    }
}
