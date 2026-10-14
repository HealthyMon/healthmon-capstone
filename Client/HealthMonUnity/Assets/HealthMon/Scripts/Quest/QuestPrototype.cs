using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class QuestPrototype : MonoBehaviour
{
    [Header("Quest Progress Text")]
    [SerializeField] private TMP_Text walkProgressText;
    [SerializeField] private TMP_Text foodProgressText;
    [SerializeField] private TMP_Text dialogueProgressText;
    [SerializeField] private TMP_Text arProgressText;

    [Header("Claim Buttons")]
    [SerializeField] private Button walkClaimButton;
    [SerializeField] private Button foodClaimButton;
    [SerializeField] private Button dialogueClaimButton;
    [SerializeField] private Button arClaimButton;

    [Header("Claim Button Text")]
    [SerializeField] private TMP_Text walkClaimText;
    [SerializeField] private TMP_Text foodClaimText;
    [SerializeField] private TMP_Text dialogueClaimText;
    [SerializeField] private TMP_Text arClaimText;

    [Header("Summary")]
    [SerializeField] private TMP_Text summaryText;

    [Header("Reward")]
    [SerializeField] private GameObject rewardPanel;
    [SerializeField] private TMP_Text rewardQuestText;
    [SerializeField] private TMP_Text rewardExpText;
    [SerializeField] private TMP_Text rewardCoinText;

    [Header("Pet State")]
    [SerializeField] private PetStateManager petStateManager;

    [Header("Customization")]
    [SerializeField]
    private CustomizationPrototype customizationPrototype;

    private int walkProgress = 1200;
    private int foodProgress = 0;
    private int dialogueProgress = 0;
    private int arProgress = 0;

    private bool walkClaimed;
    private bool foodClaimed;
    private bool dialogueClaimed;
    private bool arClaimed;

    private void Start()
    {
        rewardPanel.SetActive(false);
        RefreshUI();
    }

    public void AddFoodRecord()
    {
        foodProgress = 1;

        Debug.Log("[Quest] 음식 기록 퀘스트 진행");

        RefreshUI();
    }

    public void AddDialogue()
    {
        dialogueProgress = 1;

        Debug.Log("[Quest] 대화 퀘스트 진행");

        RefreshUI();
    }

    public void AddARInteraction()
    {
        arProgress++;

        if (arProgress > 3)
            arProgress = 3;

        Debug.Log("[Quest] AR 상호작용 진행: " + arProgress);

        RefreshUI();
    }

    public void AddWalkSteps(int steps)
    {
        walkProgress += steps;

        if (walkProgress > 3000)
            walkProgress = 3000;

        RefreshUI();
    }

    private void RefreshUI()
    {
        walkProgressText.text =
            $"진행도 : {walkProgress} / 3000";

        foodProgressText.text =
            $"진행도 : {foodProgress} / 1";

        dialogueProgressText.text =
            $"진행도 : {dialogueProgress} / 1";

        arProgressText.text =
            $"진행도 : {arProgress} / 3";

        UpdateButton(
            walkClaimButton,
            walkClaimText,
            walkProgress >= 3000,
            walkClaimed
        );

        UpdateButton(
            foodClaimButton,
            foodClaimText,
            foodProgress >= 1,
            foodClaimed
        );

        UpdateButton(
            dialogueClaimButton,
            dialogueClaimText,
            dialogueProgress >= 1,
            dialogueClaimed
        );

        UpdateButton(
            arClaimButton,
            arClaimText,
            arProgress >= 3,
            arClaimed
        );

        int completedCount = 0;

        if (walkProgress >= 3000) completedCount++;
        if (foodProgress >= 1) completedCount++;
        if (dialogueProgress >= 1) completedCount++;
        if (arProgress >= 3) completedCount++;

        summaryText.text =
            $"완료한 퀘스트 {completedCount} / 4";
    }

    private void UpdateButton(
        Button button,
        TMP_Text buttonText,
        bool completed,
        bool claimed)
    {
        if (claimed)
        {
            button.interactable = false;
            buttonText.text = "수령 완료";
            return;
        }

        if (completed)
        {
            button.interactable = true;
            buttonText.text = "보상 받기";
        }
        else
        {
            button.interactable = false;
            buttonText.text = "진행 중";
        }
    }

    public void ClaimWalkReward()
    {
        if (walkProgress < 3000 || walkClaimed)
            return;

        walkClaimed = true;

        if (customizationPrototype != null)
        {
            customizationPrototype.UnlockCap();
        }

        ShowReward(
            "3,000보 걷기",
            100,
            30
        );

        RefreshUI();
    }

    public void ClaimFoodReward()
    {
        if (foodProgress < 1 || foodClaimed)
            return;

        foodClaimed = true;

        if (customizationPrototype != null)
        {
            customizationPrototype.UnlockRibbon();
        }

        ShowReward(
            "음식 1회 기록하기",
            50,
            20
        );

        RefreshUI();
    }

    public void ClaimDialogueReward()
    {
        if (dialogueProgress < 1 || dialogueClaimed)
            return;

        dialogueClaimed = true;

        if (customizationPrototype != null)
        {
            customizationPrototype.UnlockGlasses();
        }

        ShowReward(
            "헬스몬과 대화하기",
            50,
            20
        );

        RefreshUI();
    }

    public void ClaimARReward()
    {
        if (arProgress < 3 || arClaimed)
            return;

        arClaimed = true;

        ShowReward(
            "AR 공간에서 3회 상호작용",
            80,
            25
        );

        RefreshUI();
    }

    private void ShowReward(
        string questName,
        int exp,
        int coin)
    {
        rewardQuestText.text = questName;
        rewardExpText.text = $"EXP +{exp}";
        rewardCoinText.text = $"코인 +{coin}";

        if (petStateManager != null)
        {
            petStateManager.AddReward(exp, coin);
        }

        rewardPanel.SetActive(true);
    }

    public void CloseReward()
    {
        rewardPanel.SetActive(false);
    }

    
    // ==========================================
    // 관리자 전용 - 퀘스트 초기화
    // ==========================================
    public void ResetQuestsForTesting()
    {
        // 퀘스트 진행도 초기화
        walkProgress = 1200;
        foodProgress = 0;
        dialogueProgress = 0;
        arProgress = 0;

        // 보상 수령 여부 초기화
        walkClaimed = false;
        foodClaimed = false;
        dialogueClaimed = false;
        arClaimed = false;

        // 보상 팝업 닫기
        if (rewardPanel != null)
        {
            rewardPanel.SetActive(false);
        }

        // UI 즉시 갱신
        RefreshUI();

        Debug.Log("[Quest] 관리자 퀘스트 초기화 완료");
    }

}