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

    private TMPro.TMP_Text evolutionStatusText;
    private bool showingEvolution;
    private PetExperienceUI petExperience;

    private void Start()
    {
        foreach (var label in homePanel.GetComponentsInChildren<TMPro.TMP_Text>(true))
        {
            if (label.text.Contains("오늘도 같이"))
            {
                evolutionStatusText = label;
                break;
            }
        }
        petExperience = gameObject.AddComponent<PetExperienceUI>();
        petExperience.Configure(this, homePanel, statusPanel, adminPanel);
        ShowHome();
    }

    private void Update()
    {
        var evolution = Healthmon.Evolution.EvolutionClient.Instance;
        if (evolution == null || evolutionStatusText == null)
            return;

        if (!string.IsNullOrEmpty(evolution.ActiveRequestId))
        {
            showingEvolution = true;
            switch (evolution.Phase)
            {
                case "waiting_for_gpu": evolutionStatusText.text = "이전 작업이 끝나면 진화를 시작해요."; break;
                case "plan": evolutionStatusText.text = "성장 기록으로 다음 모습을 구상하고 있어요."; break;
                case "image": evolutionStatusText.text = "새로운 진화 이미지를 만들고 있어요."; break;
                case "reconstruction": evolutionStatusText.text = "진화 모델과 움직일 뼈대를 만들고 있어요."; break;
                default: evolutionStatusText.text = "진화를 준비하고 있어요."; break;
            }
        }
        else if (showingEvolution)
        {
            evolutionStatusText.text = evolution.Phase == "complete"
                ? "새로운 모습으로 진화했어요!"
                : "진화를 완료하지 못했어요. 기존 모습은 유지돼요.";
        }
    }

    private void HideAllPanels()
    {
        if (petExperience != null) petExperience.HideAR();
        if (dialoguePanel.activeSelf)
        {
            FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include)?.LeaveConversation();
        }
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

    public void ShowAR()
    {
        HideAllPanels();
        if (petExperience != null) petExperience.ShowAR();
    }

    public void ShowDialogue()
    {
        if (dialoguePanel.activeSelf)
            return;

        HideAllPanels();
        dialoguePanel.SetActive(true);
        FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include)?.EnterConversation();
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
