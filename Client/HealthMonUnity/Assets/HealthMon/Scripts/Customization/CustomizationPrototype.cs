using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// HealthMon collection/customization prototype.
/// Keeps the original Unity Inspector fields and button functions intact.
/// Adds local save/load for unlock and equipped-item state.
/// </summary>
public class CustomizationPrototype : MonoBehaviour
{
    [Header("Collection")]
    [SerializeField] private TMP_Text collectionCountText;

    [SerializeField] private TMP_Text badgeLockText;
    [SerializeField] private TMP_Text ribbonLockText;
    [SerializeField] private TMP_Text glassesLockText;
    [SerializeField] private TMP_Text capLockText;

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

    private const string SaveKey = "HealthMon_Customization_Save_v1";

    private bool badgeUnlocked = true;
    private bool ribbonUnlocked = false;
    private bool glassesUnlocked = false;
    private bool capUnlocked = false;

    private string selectedItem = "기본 배지";
    private string equippedItem = "기본 배지";

    [Serializable]
    private class CustomizationSaveData
    {
        public bool ribbonUnlocked;
        public bool glassesUnlocked;
        public bool capUnlocked;
        public string equippedItem;
    }

    private void Awake()
    {
        // Read persisted state before any quest/admin action can save a new state.
        LoadCustomizationData();
    }

    private void Start()
    {
        RefreshUI();
        SelectBadge();
    }

    public void UnlockRibbon()
    {
        if (ribbonUnlocked) return;
        ribbonUnlocked = true;
        SaveCustomizationData();
        RefreshUI();
    }

    public void UnlockGlasses()
    {
        if (glassesUnlocked) return;
        glassesUnlocked = true;
        SaveCustomizationData();
        RefreshUI();
    }

    public void UnlockCap()
    {
        if (capUnlocked) return;
        capUnlocked = true;
        SaveCustomizationData();
        RefreshUI();
    }

    // Kept for the AdminUnlockAllItems() call from HealthMonAdminPanel.
    public void UnlockAllItems()
    {
        ribbonUnlocked = true;
        glassesUnlocked = true;
        capUnlocked = true;
        SaveCustomizationData();
        RefreshUI();
        Debug.Log("[Customization] 모든 아이템 해금 완료!");
    }

    public void SelectBadge()
    {
        SelectItem(
            "기본 배지",
            "헬스몬이 처음부터 가지고 있는 기본 꾸미기 아이템입니다.",
            badgeUnlocked
        );
    }

    public void SelectRibbon()
    {
        SelectItem(
            "리본",
            "음식 기록 퀘스트를 통해 획득하는 꾸미기 아이템입니다.",
            ribbonUnlocked
        );
    }

    public void SelectGlasses()
    {
        SelectItem(
            "안경",
            "헬스몬과 대화 퀘스트를 완료하면 획득할 수 있습니다.",
            glassesUnlocked
        );
    }

    public void SelectCap()
    {
        SelectItem(
            "운동 모자",
            "활동 퀘스트를 완료하면 획득할 수 있는 아이템입니다.",
            capUnlocked
        );
    }

    private void SelectItem(string itemName, string description, bool unlocked)
    {
        selectedItem = itemName;

        if (selectedItemNameText != null) selectedItemNameText.text = itemName;

        if (unlocked)
        {
            if (selectedItemDescriptionText != null) selectedItemDescriptionText.text = description;
            if (customizeButton != null) customizeButton.interactable = true;
        }
        else
        {
            if (selectedItemDescriptionText != null)
                selectedItemDescriptionText.text = "아직 획득하지 않은 아이템입니다.";
            if (customizeButton != null) customizeButton.interactable = false;
        }

        if (customizeItemNameText != null) customizeItemNameText.text = itemName;
        if (customizeDescriptionText != null)
            customizeDescriptionText.text = unlocked ? description : "잠긴 아이템입니다.";
        if (equipButton != null) equipButton.interactable = unlocked;
    }

    public void EquipSelectedItem()
    {
        if (!IsItemUnlocked(selectedItem)) return;

        equippedItem = selectedItem;
        if (statusText != null) statusText.text = $"{equippedItem}을(를) 장착했습니다.";

        SaveCustomizationData();
        RefreshUI();
    }

    private bool IsItemUnlocked(string itemName)
    {
        switch (itemName)
        {
            case "기본 배지": return true;
            case "리본": return ribbonUnlocked;
            case "안경": return glassesUnlocked;
            case "운동 모자": return capUnlocked;
            default: return false;
        }
    }

    private void SaveCustomizationData()
    {
        var data = new CustomizationSaveData
        {
            ribbonUnlocked = ribbonUnlocked,
            glassesUnlocked = glassesUnlocked,
            capUnlocked = capUnlocked,
            equippedItem = equippedItem
        };

        PlayerPrefs.SetString(SaveKey, JsonUtility.ToJson(data));
        PlayerPrefs.Save();
        Debug.Log("[Customization] 아이템 데이터 저장 완료");
    }

    private void LoadCustomizationData()
    {
        if (!PlayerPrefs.HasKey(SaveKey))
        {
            Debug.Log("[Customization] 기존 저장 데이터 없음: 초기 아이템 사용");
            return;
        }

        try
        {
            var data = JsonUtility.FromJson<CustomizationSaveData>(PlayerPrefs.GetString(SaveKey));
            if (data == null) return;

            ribbonUnlocked = data.ribbonUnlocked;
            glassesUnlocked = data.glassesUnlocked;
            capUnlocked = data.capUnlocked;
            equippedItem = IsItemUnlocked(data.equippedItem) ? data.equippedItem : "기본 배지";

            Debug.Log("[Customization] 아이템 데이터 불러오기 완료");
        }
        catch (Exception e)
        {
            Debug.LogWarning("[Customization] 아이템 저장 데이터 읽기 실패: " + e.Message);
        }
    }

    private void RefreshUI()
    {
        if (badgeLockText != null) badgeLockText.text = badgeUnlocked ? "해금됨" : "잠김";
        if (ribbonLockText != null) ribbonLockText.text = ribbonUnlocked ? "해금됨" : "잠김";
        if (glassesLockText != null) glassesLockText.text = glassesUnlocked ? "해금됨" : "잠김";
        if (capLockText != null) capLockText.text = capUnlocked ? "해금됨" : "잠김";

        int unlockedCount = 1;
        if (ribbonUnlocked) unlockedCount++;
        if (glassesUnlocked) unlockedCount++;
        if (capUnlocked) unlockedCount++;

        if (collectionCountText != null) collectionCountText.text = $"{unlockedCount} / 4 해금";
        if (equippedItemText != null) equippedItemText.text = $"현재 장착 : {equippedItem}";
    }
}
