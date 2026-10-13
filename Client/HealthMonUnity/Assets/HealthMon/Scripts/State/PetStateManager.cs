using TMPro;
using UnityEngine;

public class PetStateManager : MonoBehaviour
{
    [Header("Basic State")]
    [SerializeField] private string petName = "헬스몬";

    [SerializeField] private int level = 1;
    [SerializeField] private int currentExp = 20;
    [SerializeField] private int expToNextLevel = 100;

    [SerializeField] private int coin = 0;

    [Header("Character Stats")]
    [SerializeField] private int intimacy = 45;
    [SerializeField] private int activity = 32;
    [SerializeField] private int kindness = 40;
    [SerializeField] private int curiosity = 20;

    [Header("Growth")]
    [SerializeField] private string growthStage = "초기형";

    [Header("Home UI")]
    [SerializeField] private TMP_Text homeLevelText;
    [SerializeField] private TMP_Text homeNameText;
    [SerializeField] private TMP_Text homeExpText;
    [SerializeField] private TMP_Text homeCoinText;

    [Header("Home Status UI")]
    [SerializeField] private TMP_Text homeIntimacyText;
    [SerializeField] private TMP_Text homeActivityText;

    [Header("Status Panel UI")]
    [SerializeField] private TMP_Text statusLevelText;
    [SerializeField] private TMP_Text statusNameText;
    [SerializeField] private TMP_Text statusExpText;

    [SerializeField] private TMP_Text statusIntimacyText;
    [SerializeField] private TMP_Text statusActivityText;
    [SerializeField] private TMP_Text statusKindnessText;
    [SerializeField] private TMP_Text statusCuriosityText;

    [SerializeField] private TMP_Text growthStageText;
    [SerializeField] private TMP_Text evolutionConditionText;

    private void Start()
    {
        RefreshAllUI();
    }

    public void AddReward(int expAmount, int coinAmount)
    {
        AddExp(expAmount);

        coin += coinAmount;

        Debug.Log(
            $"[PetState] EXP +{expAmount}, Coin +{coinAmount}"
        );

        RefreshAllUI();
    }

    public void AddExp(int amount)
    {
        currentExp += amount;

        while (currentExp >= expToNextLevel)
        {
            currentExp -= expToNextLevel;
            level++;

            Debug.Log(
                $"[PetState] Level Up! 현재 레벨: {level}"
            );
        }

        RefreshAllUI();
    }

    public void AddIntimacy(int amount)
    {
        intimacy += amount;

        intimacy = Mathf.Clamp(intimacy, 0, 100);

        RefreshAllUI();
    }

    public void AddActivity(int amount)
    {
        activity += amount;

        activity = Mathf.Clamp(activity, 0, 100);

        RefreshAllUI();
    }

    public void AddKindness(int amount)
    {
        kindness += amount;

        kindness = Mathf.Clamp(kindness, 0, 100);

        RefreshAllUI();
    }

    public void AddCuriosity(int amount)
    {
        curiosity += amount;

        curiosity = Mathf.Clamp(curiosity, 0, 100);

        RefreshAllUI();
    }

    public void RefreshAllUI()
    {
        // Home
        if (homeLevelText != null)
            homeLevelText.text = $"Lv. {level}";

        if (homeNameText != null)
            homeNameText.text = petName;

        if (homeExpText != null)
            homeExpText.text =
                $"EXP {currentExp} / {expToNextLevel}";

        if (homeCoinText != null)
            homeCoinText.text = $"코인 {coin}";

        if (homeIntimacyText != null)
            homeIntimacyText.text =
                $"친밀도 {intimacy}";

        if (homeActivityText != null)
            homeActivityText.text =
                $"활동성 {activity}";


        // Status
        if (statusLevelText != null)
            statusLevelText.text = $"Lv. {level}";

        if (statusNameText != null)
            statusNameText.text = petName;

        if (statusExpText != null)
            statusExpText.text =
                $"EXP {currentExp} / {expToNextLevel}";

        if (statusIntimacyText != null)
            statusIntimacyText.text =
                intimacy.ToString();

        if (statusActivityText != null)
            statusActivityText.text =
                activity.ToString();

        if (statusKindnessText != null)
            statusKindnessText.text =
                kindness.ToString();

        if (statusCuriosityText != null)
            statusCuriosityText.text =
                curiosity.ToString();

        if (growthStageText != null)
            growthStageText.text =
                $"현재 단계 : {growthStage}";

        if (evolutionConditionText != null)
        {
            int remainExp =
                expToNextLevel - currentExp;

            evolutionConditionText.text =
                $"다음 성장까지 EXP {remainExp} 필요";
        }
    }
}