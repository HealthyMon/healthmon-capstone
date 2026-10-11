using TMPro;
using UnityEngine;
using UnityEngine.UI;

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

    private bool badgeUnlocked = true;
    private bool ribbonUnlocked = false;
    private bool glassesUnlocked = false;
    private bool capUnlocked = false;

    private string selectedItem = "기본 배지";
    private string equippedItem = "기본 배지";

    private void Start()
    {
        RefreshUI();
        SelectBadge();
    }

    public void UnlockRibbon()
    {
        ribbonUnlocked = true;
        RefreshUI();
    }

    public void UnlockGlasses()
    {
        glassesUnlocked = true;
        RefreshUI();
    }

    public void UnlockCap()
    {
        capUnlocked = true;
        RefreshUI();
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

    private void SelectItem(
        string itemName,
        string description,
        bool unlocked)
    {
        selectedItem = itemName;

        selectedItemNameText.text = itemName;

        if (unlocked)
        {
            selectedItemDescriptionText.text = description;
            customizeButton.interactable = true;
        }
        else
        {
            selectedItemDescriptionText.text =
                "아직 획득하지 않은 아이템입니다.";

            customizeButton.interactable = false;
        }

        customizeItemNameText.text = itemName;
        customizeDescriptionText.text =
            unlocked ? description : "잠긴 아이템입니다.";

        equipButton.interactable = unlocked;
    }

    public void EquipSelectedItem()
    {
        if (!IsSelectedItemUnlocked())
            return;

        equippedItem = selectedItem;

        equippedItemText.text =
            $"현재 장착 : {equippedItem}";

        statusText.text =
            $"{equippedItem}을(를) 장착했습니다.";

        RefreshUI();
    }

    private bool IsSelectedItemUnlocked()
    {
        switch (selectedItem)
        {
            case "기본 배지":
                return badgeUnlocked;

            case "리본":
                return ribbonUnlocked;

            case "안경":
                return glassesUnlocked;

            case "운동 모자":
                return capUnlocked;
        }

        return false;
    }

    private void RefreshUI()
    {
        badgeLockText.text =
            badgeUnlocked ? "해금됨" : "잠김";

        ribbonLockText.text =
            ribbonUnlocked ? "해금됨" : "잠김";

        glassesLockText.text =
            glassesUnlocked ? "해금됨" : "잠김";

        capLockText.text =
            capUnlocked ? "해금됨" : "잠김";

        int unlockedCount = 0;

        if (badgeUnlocked) unlockedCount++;
        if (ribbonUnlocked) unlockedCount++;
        if (glassesUnlocked) unlockedCount++;
        if (capUnlocked) unlockedCount++;

        collectionCountText.text =
            $"{unlockedCount} / 4 해금";

        equippedItemText.text =
            $"현재 장착 : {equippedItem}";
    }
}