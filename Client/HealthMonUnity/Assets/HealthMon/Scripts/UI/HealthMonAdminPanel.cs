
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class HealthMonAdminPanel : MonoBehaviour
{
    [Header("Pet State")]
    [SerializeField]
    private PetStateManager petStateManager;

    [Header("Quest System")]
    [SerializeField] private QuestPrototype questPrototype;

    [Header("Customization System")]
    [SerializeField]
    private CustomizationPrototype customizationPrototype;

    [Header("Basic Inputs")]
    [SerializeField]
    private TMP_InputField levelInput;

    [SerializeField]
    private TMP_InputField coinInput;

    [Header("Stat Sliders")]
    [SerializeField]
    private Slider intimacySlider;

    [SerializeField]
    private Slider activitySlider;

    [SerializeField]
    private Slider kindnessSlider;

    [SerializeField]
    private Slider curiositySlider;

    [Header("Slider Value Texts")]
    [SerializeField]
    private TMP_Text intimacyValueText;

    [SerializeField]
    private TMP_Text activityValueText;

    [SerializeField]
    private TMP_Text kindnessValueText;

    [SerializeField]
    private TMP_Text curiosityValueText;

    private void Awake()
    {
        // 슬라이더를 움직이면 숫자 갱신
        intimacySlider.onValueChanged.AddListener(OnSliderChanged);
        activitySlider.onValueChanged.AddListener(OnSliderChanged);
        kindnessSlider.onValueChanged.AddListener(OnSliderChanged);
        curiositySlider.onValueChanged.AddListener(OnSliderChanged);
    }

    private void OnEnable()
    {
        // 관리자 화면을 열 때 현재 상태 불러오기
        LoadCurrentStats();
    }

    private void OnDestroy()
    {
        intimacySlider.onValueChanged.RemoveListener(OnSliderChanged);
        activitySlider.onValueChanged.RemoveListener(OnSliderChanged);
        kindnessSlider.onValueChanged.RemoveListener(OnSliderChanged);
        curiositySlider.onValueChanged.RemoveListener(OnSliderChanged);
    }

    public void LoadCurrentStats()
    {
        if (petStateManager == null)
        {
            Debug.LogError("[Admin] PetStateManager 연결 필요");
            return;
        }

        levelInput.SetTextWithoutNotify(
            petStateManager.CurrentLevel.ToString()
        );

        coinInput.SetTextWithoutNotify(
            petStateManager.CurrentCoin.ToString()
        );

        intimacySlider.SetValueWithoutNotify(
            petStateManager.CurrentIntimacy
        );

        activitySlider.SetValueWithoutNotify(
            petStateManager.CurrentActivity
        );

        kindnessSlider.SetValueWithoutNotify(
            petStateManager.CurrentKindness
        );

        curiositySlider.SetValueWithoutNotify(
            petStateManager.CurrentCuriosity
        );

        RefreshSliderTexts();
    }

    private void OnSliderChanged(float value)
    {
        RefreshSliderTexts();
    }

    private void RefreshSliderTexts()
    {
        intimacyValueText.text =
            Mathf.RoundToInt(intimacySlider.value).ToString();

        activityValueText.text =
            Mathf.RoundToInt(activitySlider.value).ToString();

        kindnessValueText.text =
            Mathf.RoundToInt(kindnessSlider.value).ToString();

        curiosityValueText.text =
            Mathf.RoundToInt(curiositySlider.value).ToString();
    }

    public void ApplyChanges()
    {
        if (petStateManager == null)
        {
            Debug.LogError("[Admin] PetStateManager 없음");
            return;
        }

        if (!int.TryParse(levelInput.text, out int level) ||
            level < 1 ||
            !int.TryParse(coinInput.text, out int coin) ||
            coin < 0)
        {
            Debug.LogWarning(
                "[Admin] 레벨은 1 이상, 코인은 0 이상의 정수여야 합니다."
            );
            return;
        }

        petStateManager.SetAdminValues(
            level,
            coin,
            Mathf.RoundToInt(intimacySlider.value),
            Mathf.RoundToInt(activitySlider.value),
            Mathf.RoundToInt(kindnessSlider.value),
            Mathf.RoundToInt(curiositySlider.value)
        );

        Debug.Log("[Admin] 변경 적용 완료");

        LoadCurrentStats();
    }

    
    // 경험치 100 지급
        public void GiveTestExp()
        {
            if (petStateManager == null)
                return;

            petStateManager.AddExp(100);
            LoadCurrentStats();

            Debug.Log("[Admin] EXP +100 지급");
        }

        // 코인 50 지급
        public void GiveTestCoin()
        {
            if (petStateManager == null)
                return;

            petStateManager.AddReward(0, 50);
            LoadCurrentStats();

            Debug.Log("[Admin] 코인 +50 지급");
        }

        // 모든 퀘스트 목표 달성
        public void CompleteAllQuestGoals()
        {
            if (questPrototype == null)
            {
                Debug.LogError("[Admin] QuestPrototype 연결 필요");
                return;
            }

            questPrototype.AddWalkSteps(3000);
            questPrototype.AddFoodRecord();
            questPrototype.AddDialogue();

            for (int i = 0; i < 3; i++)
            {
                questPrototype.AddARInteraction();
            }

            Debug.Log("[Admin] 모든 퀘스트 목표 달성");
        }

        
    // ==========================================
    // 관리자 테스트 - 모든 아이템 해금
    // ==========================================
    public void AdminUnlockAllItems()
    {
        if (customizationPrototype == null)
        {
            Debug.LogError(
                "[Admin] CustomizationPrototype 연결 필요"
            );
            return;
        }

        customizationPrototype.UnlockAllItems();

        Debug.Log("[Admin] 모든 꾸미기 아이템 해금 완료");
    }

    
    // ==========================================
    // 관리자 테스트 - 퀘스트 초기화
    // ==========================================
    public void AdminResetQuests()
    {
        if (questPrototype == null)
        {
            Debug.LogError(
                "[Admin] QuestPrototype 연결 필요"
            );
            return;
        }

        questPrototype.ResetQuestsForTesting();

        Debug.Log("[Admin] 퀘스트 초기화 실행");
    }



}
