using UnityEngine;

public class UIManager : MonoBehaviour
{
    [Header("Main Panels")]
    [SerializeField] private GameObject homePanel;
    [SerializeField] private GameObject statusPanel;
    [SerializeField] private GameObject dialoguePanel;
    [SerializeField] private GameObject foodScanPanel;
    [SerializeField] private GameObject questPanel;
    [SerializeField] private GameObject rewardPanel;
    [SerializeField] private GameObject customizationPanel;
    [SerializeField] private GameObject collectionPanel;

    // 관리자 패널 추가
    [Header("Admin Panel")]
    [SerializeField] private GameObject adminPanel;

    private void Start()
    {
        ShowHome();
    }

    private void HideAllPanels()
    {
        homePanel.SetActive(false);
        statusPanel.SetActive(false);
        dialoguePanel.SetActive(false);
        foodScanPanel.SetActive(false);
        questPanel.SetActive(false);
        rewardPanel.SetActive(false);
        customizationPanel.SetActive(false);
        collectionPanel.SetActive(false);

        if (adminPanel != null)
            adminPanel.SetActive(false);
    }

    public void ShowHome()
    {
        HideAllPanels();
        homePanel.SetActive(true);
    }

    public void ShowStatus()
    {
        HideAllPanels();
        statusPanel.SetActive(true);
    }

    public void ShowDialogue()
    {
        HideAllPanels();
        dialoguePanel.SetActive(true);
    }

    public void ShowFoodScan()
    {
        HideAllPanels();
        foodScanPanel.SetActive(true);
    }

    public void ShowQuest()
    {
        HideAllPanels();
        questPanel.SetActive(true);
    }

    public void ShowReward()
    {
        HideAllPanels();
        rewardPanel.SetActive(true);
    }

    public void ShowCustomization()
    {
        HideAllPanels();
        customizationPanel.SetActive(true);
    }

    public void ShowCollection()
    {
        HideAllPanels();
        collectionPanel.SetActive(true);
    }

    // 관리자 모드 열기
    public void ShowAdmin()
    {
        if (adminPanel == null)
        {
            Debug.LogError("[UIManager] AdminPanel 연결 안 됨!");
            return;
        }

        HideAllPanels();
        adminPanel.SetActive(true);

        Debug.Log("[UIManager] 관리자 모드 열기");
    }

    // 관리자 모드 닫기
    public void CloseAdmin()
    {
        ShowHome();

        Debug.Log("[UIManager] 관리자 모드 닫기");
    }
}