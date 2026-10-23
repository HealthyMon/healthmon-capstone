using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Separate, optional four-slot accessory popup on the existing CustomizationPanel.
/// Reuses CustomizationPrototype's equip/unequip and PlayerPrefs save logic.
/// Created and wired by HealthMon > Jewelry > Create Equipment Popup.
/// </summary>
public class HealthMonJewelryOverlayUI : MonoBehaviour
{
    private static readonly string[] ItemNames = { "목걸이", "귀걸이", "펜던트", "반지" };

    [SerializeField] private GameObject overlay;
    [SerializeField] private Button openButton;
    [SerializeField] private Button closeButton;
    [SerializeField] private Button[] toggleButtons = new Button[4];
    [SerializeField] private TMP_Text[] statusTexts = new TMP_Text[4];
    [SerializeField] private TMP_Text[] actionTexts = new TMP_Text[4];
    [SerializeField] private TMP_Text equippedSummary;

    private CustomizationPrototype customization;

    // Called by the editor builder; not necessary to wire fields manually.
    public void Configure(GameObject overlayRoot, Button open, Button close,
        Button[] toggles, TMP_Text[] statuses, TMP_Text[] actions, TMP_Text summary)
    {
        overlay = overlayRoot;
        openButton = open;
        closeButton = close;
        toggleButtons = toggles;
        statusTexts = statuses;
        actionTexts = actions;
        equippedSummary = summary;
    }

    private void Awake()
    {
        if (openButton != null) openButton.onClick.AddListener(Open);
        if (closeButton != null) closeButton.onClick.AddListener(Close);
        if (toggleButtons != null)
        {
            for (int i = 0; i < Mathf.Min(4, toggleButtons.Length); i++)
            {
                int itemIndex = i;
                if (toggleButtons[i] != null)
                    toggleButtons[i].onClick.AddListener(() => Toggle(itemIndex));
            }
        }
    }

    private void OnEnable()
    {
        Connect();
        Refresh();
    }

    private void Start()
    {
        Connect();
        Refresh();
    }

    private void OnDisable()
    {
        if (customization != null)
            customization.OnEquippedItemChanged -= HandleChanged;
        customization = null;
    }

    private void Connect()
    {
        if (customization != null) return;
        customization = FindFirstObjectByType<CustomizationPrototype>();
        if (customization != null)
            customization.OnEquippedItemChanged += HandleChanged;
    }

    public void Open()
    {
        Connect();
        if (overlay != null) overlay.SetActive(true);
        Refresh();
    }

    public void Close()
    {
        if (overlay != null) overlay.SetActive(false);
    }

    private void HandleChanged(string changedItem)
    {
        Refresh();
    }

    private void Toggle(int index)
    {
        Connect();
        if (customization == null)
        {
            Debug.LogWarning("[HealthMon] CustomizationManager를 찾지 못했습니다.");
            return;
        }

        string item = ItemNames[index];
        if (!customization.IsUnlocked(item))
        {
            Debug.Log("[HealthMon] 아직 해금하지 않은 장신구: " + item);
            Refresh();
            return;
        }

        switch (index)
        {
            case 0: customization.SelectNecklace(); break;
            case 1: customization.SelectEarring(); break;
            case 2: customization.SelectPendant(); break;
            case 3: customization.SelectRing(); break;
        }
        customization.EquipSelectedItem();
        Refresh();
    }

    public void Refresh()
    {
        Connect();
        if (customization == null) return;

        int totalEquipped = 0;
        for (int i = 0; i < 4; i++)
        {
            bool unlocked = customization.IsUnlocked(ItemNames[i]);
            bool equipped = customization.IsEquipped(ItemNames[i]);
            if (equipped) totalEquipped++;

            if (toggleButtons != null && i < toggleButtons.Length && toggleButtons[i] != null)
                toggleButtons[i].interactable = unlocked;
            if (statusTexts != null && i < statusTexts.Length && statusTexts[i] != null)
                statusTexts[i].text = !unlocked ? "잠김" : equipped ? "착용 중" : "미착용";
            if (actionTexts != null && i < actionTexts.Length && actionTexts[i] != null)
                actionTexts[i].text = !unlocked ? "잠김" : equipped ? "해제" : "장착";
        }

        if (equippedSummary != null)
            equippedSummary.text = $"장착 중 {totalEquipped} / 4  ·  장신구별로 개별 장착 가능";
    }
}
