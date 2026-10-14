using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// 헬스몬 일일 퀘스트: 진행도/수령 상태 저장, 날짜 변경 시 일일 초기화.
/// 기존 Inspector 필드 및 외부 호출 함수 이름 유지.
/// </summary>
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
    [SerializeField] private CustomizationPrototype customizationPrototype;

    private const string SaveKey = "HealthMon_Quest_Save_v1";
    private const int WalkGoal = 3000;
    private const int ArGoal = 3;

    // 기존 임시 걸음 수(1,200보)를 유지. 웨어러블 연동 시 0으로 변경할 것.
    private const int MockStartingSteps = 1200;

    private int walkProgress = MockStartingSteps;
    private int foodProgress;
    private int dialogueProgress;
    private int arProgress;

    private bool walkClaimed;
    private bool foodClaimed;
    private bool dialogueClaimed;
    private bool arClaimed;
    private string questDate;
    private bool initialized;

    [Serializable]
    private class QuestSaveData
    {
        public string date;
        public int walkProgress;
        public int foodProgress;
        public int dialogueProgress;
        public int arProgress;
        public bool walkClaimed;
        public bool foodClaimed;
        public bool dialogueClaimed;
        public bool arClaimed;
    }

    private static string TodayLocalDate() => DateTime.Now.ToString("yyyy-MM-dd");

    private void Start()
    {
        LoadOrCreateToday();
        initialized = true;
        if (rewardPanel != null) rewardPanel.SetActive(false);
        RefreshUI();
    }

    // 앱이 잠시 백그라운드에 있다가 다음 날 돌아오는 경우에도 초기화.
    private void OnApplicationFocus(bool hasFocus)
    {
        if (hasFocus && initialized) CheckDateChange();
    }

    private void OnApplicationPause(bool pauseStatus)
    {
        if (!pauseStatus && initialized) CheckDateChange();
    }

    private void CheckDateChange()
    {
        if (questDate == TodayLocalDate()) return;
        ResetProgressAndClaims();
        questDate = TodayLocalDate();
        SaveQuestData();
        if (rewardPanel != null) rewardPanel.SetActive(false);
        RefreshUI();
        Debug.Log("[Quest] 새로운 날짜: 일일 퀘스트 초기화");
    }

    private void ResetProgressAndClaims()
    {
        walkProgress = MockStartingSteps;
        foodProgress = 0;
        dialogueProgress = 0;
        arProgress = 0;
        walkClaimed = false;
        foodClaimed = false;
        dialogueClaimed = false;
        arClaimed = false;
    }

    private void LoadOrCreateToday()
    {
        questDate = TodayLocalDate();
        if (!PlayerPrefs.HasKey(SaveKey))
        {
            ResetProgressAndClaims();
            SaveQuestData();
            Debug.Log("[Quest] 저장 데이터 없음: 오늘 퀘스트 생성");
            return;
        }

        try
        {
            var json = PlayerPrefs.GetString(SaveKey);
            var data = JsonUtility.FromJson<QuestSaveData>(json);
            if (data == null || data.date != questDate)
            {
                ResetProgressAndClaims();
                SaveQuestData();
                Debug.Log("[Quest] 날짜 변경 또는 저장 데이터 없음: 초기화");
                return;
            }

            walkProgress = Mathf.Clamp(data.walkProgress, 0, WalkGoal);
            foodProgress = Mathf.Clamp(data.foodProgress, 0, 1);
            dialogueProgress = Mathf.Clamp(data.dialogueProgress, 0, 1);
            arProgress = Mathf.Clamp(data.arProgress, 0, ArGoal);
            walkClaimed = data.walkClaimed;
            foodClaimed = data.foodClaimed;
            dialogueClaimed = data.dialogueClaimed;
            arClaimed = data.arClaimed;
            Debug.Log("[Quest] 오늘 퀘스트 불러오기 완료");
        }
        catch (Exception e)
        {
            Debug.LogWarning("[Quest] 저장 데이터 읽기 실패, 오늘 퀘스트 재생성: " + e.Message);
            ResetProgressAndClaims();
            SaveQuestData();
        }
    }

    private void SaveQuestData()
    {
        QuestSaveData data = new QuestSaveData
        {
            date = questDate,
            walkProgress = walkProgress,
            foodProgress = foodProgress,
            dialogueProgress = dialogueProgress,
            arProgress = arProgress,
            walkClaimed = walkClaimed,
            foodClaimed = foodClaimed,
            dialogueClaimed = dialogueClaimed,
            arClaimed = arClaimed
        };
        PlayerPrefs.SetString(SaveKey, JsonUtility.ToJson(data));
        PlayerPrefs.Save();
    }

    public void AddFoodRecord()
    {
        CheckDateChange();
        foodProgress = 1;
        SaveQuestData();
        RefreshUI();
        Debug.Log("[Quest] 음식 기록 퀘스트 진행");
    }

    public void AddDialogue()
    {
        CheckDateChange();
        dialogueProgress = 1;
        SaveQuestData();
        RefreshUI();
        Debug.Log("[Quest] 대화 퀘스트 진행");
    }

    public void AddARInteraction()
    {
        CheckDateChange();
        arProgress = Mathf.Min(ArGoal, arProgress + 1);
        SaveQuestData();
        RefreshUI();
        Debug.Log("[Quest] AR 상호작용 진행: " + arProgress);
    }

    // 기존 버튼 및 관리자 테스트 코드 호환용: 걸음 수를 '더하는' 함수.
    // 실제 누적 걸음 수 API에는 아래 SetDailyWalkSteps 를 사용할 것.
    public void AddWalkSteps(int steps)
    {
        CheckDateChange();
        if (steps <= 0) return;
        walkProgress = Mathf.Clamp(walkProgress + steps, 0, WalkGoal);
        SaveQuestData();
        RefreshUI();
    }

    // 향후 웨어러블 연동용: '오늘의 누적 걸음 수'를 그대로 갱신 (중복 더하기 방지).
    public void SetDailyWalkSteps(int steps)
    {
        CheckDateChange();
        walkProgress = Mathf.Clamp(steps, 0, WalkGoal);
        SaveQuestData();
        RefreshUI();
    }

    private void RefreshUI()
    {
        if (walkProgressText != null) walkProgressText.text = $"진행도 : {walkProgress} / {WalkGoal}";
        if (foodProgressText != null) foodProgressText.text = $"진행도 : {foodProgress} / 1";
        if (dialogueProgressText != null) dialogueProgressText.text = $"진행도 : {dialogueProgress} / 1";
        if (arProgressText != null) arProgressText.text = $"진행도 : {arProgress} / {ArGoal}";

        UpdateButton(walkClaimButton, walkClaimText, walkProgress >= WalkGoal, walkClaimed);
        UpdateButton(foodClaimButton, foodClaimText, foodProgress >= 1, foodClaimed);
        UpdateButton(dialogueClaimButton, dialogueClaimText, dialogueProgress >= 1, dialogueClaimed);
        UpdateButton(arClaimButton, arClaimText, arProgress >= ArGoal, arClaimed);

        int completedCount = 0;
        if (walkProgress >= WalkGoal) completedCount++;
        if (foodProgress >= 1) completedCount++;
        if (dialogueProgress >= 1) completedCount++;
        if (arProgress >= ArGoal) completedCount++;
        if (summaryText != null) summaryText.text = $"완료한 퀘스트 {completedCount} / 4";
    }

    private static void UpdateButton(Button button, TMP_Text buttonText, bool completed, bool claimed)
    {
        if (button != null) button.interactable = completed && !claimed;
        if (buttonText != null) buttonText.text = claimed ? "수령 완료" : (completed ? "보상 받기" : "진행 중");
    }

    public void ClaimWalkReward()
    {
        CheckDateChange();
        if (walkProgress < WalkGoal || walkClaimed) return;
        if (petStateManager == null) { Debug.LogError("[Quest] PetStateManager 연결 필요"); return; }
        walkClaimed = true;
        SaveQuestData();
        if (customizationPrototype != null) customizationPrototype.UnlockCap();
        ShowReward("3,000보 걷기", 100, 30);
        RefreshUI();
    }

    public void ClaimFoodReward()
    {
        CheckDateChange();
        if (foodProgress < 1 || foodClaimed) return;
        if (petStateManager == null) { Debug.LogError("[Quest] PetStateManager 연결 필요"); return; }
        foodClaimed = true;
        SaveQuestData();
        if (customizationPrototype != null) customizationPrototype.UnlockRibbon();
        ShowReward("음식 1회 기록하기", 50, 20);
        RefreshUI();
    }

    public void ClaimDialogueReward()
    {
        CheckDateChange();
        if (dialogueProgress < 1 || dialogueClaimed) return;
        if (petStateManager == null) { Debug.LogError("[Quest] PetStateManager 연결 필요"); return; }
        dialogueClaimed = true;
        SaveQuestData();
        if (customizationPrototype != null) customizationPrototype.UnlockGlasses();
        ShowReward("헬스몬과 대화하기", 50, 20);
        RefreshUI();
    }

    public void ClaimARReward()
    {
        CheckDateChange();
        if (arProgress < ArGoal || arClaimed) return;
        if (petStateManager == null) { Debug.LogError("[Quest] PetStateManager 연결 필요"); return; }
        arClaimed = true;
        SaveQuestData();
        ShowReward("AR 공간에서 3회 상호작용", 80, 25);
        RefreshUI();
    }

    private void ShowReward(string questName, int exp, int coin)
    {
        if (rewardQuestText != null) rewardQuestText.text = questName;
        if (rewardExpText != null) rewardExpText.text = $"EXP +{exp}";
        if (rewardCoinText != null) rewardCoinText.text = $"코인 +{coin}";
        petStateManager.AddReward(exp, coin);
        if (rewardPanel != null) rewardPanel.SetActive(true);
    }

    public void CloseReward()
    {
        if (rewardPanel != null) rewardPanel.SetActive(false);
    }

    // 이전에 만든 관리자 모드와 호환: 보상 수령 여부까지 초기화.
    public void ResetQuestsForTesting()
    {
        questDate = TodayLocalDate();
        ResetProgressAndClaims();
        SaveQuestData();
        if (rewardPanel != null) rewardPanel.SetActive(false);
        RefreshUI();
        Debug.Log("[Quest] 관리자 퀘스트 초기화 완료");
    }
}
