using TMPro;
using UnityEngine;

public class PetStateManager : MonoBehaviour
{
    private bool ServerAuthority => Healthmon.Common.CommonServerConnection.UsesServerAuthority;
    private Healthmon.Beta.PetState serverState;
    public bool HasVerifiedServerState => serverState != null;
    public int Level => level;
    public event System.Action<int> LevelChanged;

    [Header("Basic State")]
    [SerializeField] private string petName = "헬스몬";

    [SerializeField] private int level = 1;
    [SerializeField] private int currentExp = 20;
    [SerializeField] private int expToNextLevel = 100;

    [SerializeField] private int coin = 0;

    [System.Serializable]
    public class PetSaveData
    {
        public string petName;
        public int level;
        public int currentExp;
        public int expToNextLevel;
        public int coin;

        public int intimacy;
        public int activity;
        public int kindness;
        public int curiosity;

        public string growthStage;
    }

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
        if (ServerAuthority)
        {
            var state = Healthmon.Common.CommonServerConnection.Instance?.LatestState;
            if (state != null) ApplyServerState(state);
            else ClearServerState();
            return;
        }
        LoadPetData();
        RefreshAllUI();
    }

    public void AddReward(int expAmount, int coinAmount)
    {
        if (ServerAuthority) return;
        AddExp(expAmount);

        coin += coinAmount;

        Debug.Log(
            $"[PetState] EXP +{expAmount}, Coin +{coinAmount}"
        );

        RefreshAllUI();
        SavePetData();
    }

    public void AddExp(int amount)
    {
        if (ServerAuthority) return;
        currentExp += amount;

        while (currentExp >= expToNextLevel)
        {
            currentExp -= expToNextLevel;
            level++;
            LevelChanged?.Invoke(level);

            Debug.Log(
                $"[PetState] Level Up! 현재 레벨: {level}"
            );
        }

        RefreshAllUI();
        SavePetData();
    }

    public void AddIntimacy(int amount)
    {
        if (ServerAuthority) return;
        intimacy += amount;

        intimacy = Mathf.Clamp(intimacy, 0, 100);

        RefreshAllUI();
        SavePetData();
    }

    public void AddActivity(int amount)
    {
        if (ServerAuthority) return;
        activity += amount;

        activity = Mathf.Clamp(activity, 0, 100);

        RefreshAllUI();
        SavePetData();
    }

    public void AddKindness(int amount)
    {
        if (ServerAuthority) return;
        kindness += amount;

        kindness = Mathf.Clamp(kindness, 0, 100);

        RefreshAllUI();
        SavePetData();
    }

    public void AddCuriosity(int amount)
    {
        if (ServerAuthority) return;
        curiosity += amount;

        curiosity = Mathf.Clamp(curiosity, 0, 100);

        RefreshAllUI();
        SavePetData();
    }

    public void ApplyEvolutionStage(int stage)
    {
        if (ServerAuthority) return;
        int completedStage = Mathf.Clamp(stage, 0, 3);
        growthStage = new[] { "초기형", "1차 진화", "2차 진화", "3차 진화" }[completedStage];
        level = Mathf.Max(level, new[] { 1, 15, 30, 50 }[completedStage]);
        RefreshAllUI();
        SavePetData();
    }

    public void ClearServerState()
    {
        serverState = null;
        foreach (var label in new[] { homeLevelText, homeExpText, homeCoinText, homeIntimacyText,
            homeActivityText, statusLevelText, statusExpText, statusIntimacyText, statusActivityText,
            statusKindnessText, statusCuriosityText, growthStageText, evolutionConditionText })
            if (label != null) label.text = "서버 연결 대기";
    }

    public void ApplyServerState(Healthmon.Beta.PetState state)
    {
        if (!ServerAuthority || state == null || !state.IsValidCommonState(state.pet_id)) return;
        int previousLevel = level;
        serverState = state;
        if (state.settings != null && !string.IsNullOrWhiteSpace(state.settings.name)) petName = state.settings.name;
        level = state.level; currentExp = state.current_exp; expToNextLevel = state.required_exp;
        coin = state.coin; intimacy = Mathf.RoundToInt(state.affinity); activity = Mathf.RoundToInt(state.activity);
        growthStage = "목표 " + state.evolution_target_stage + " / 모델 " + state.published_model_stage + " (" + state.asset_status + ")";
        RefreshAllUI();
        if (previousLevel != level) LevelChanged?.Invoke(level);
    }

    public void RefreshAllUI()
    {
        if (ServerAuthority && serverState == null) { ClearServerState(); return; }
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
                ServerAuthority ? "공용 서버 상세 패널 참조" : kindness.ToString();

        if (statusCuriosityText != null)
            statusCuriosityText.text =
                ServerAuthority ? "공용 서버 상세 패널 참조" : curiosity.ToString();

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

    private const string SaveKey = "HealthMon_Pet_Save_v1";

    public void SavePetData()
    {
        if (ServerAuthority) return;
        PetSaveData data = new PetSaveData
        {
            petName = petName,
            level = level,
            currentExp = currentExp,
            expToNextLevel = expToNextLevel,
            coin = coin,

            intimacy = intimacy,
            activity = activity,
            kindness = kindness,
            curiosity = curiosity,

            growthStage = growthStage
        };

        string json = JsonUtility.ToJson(data);

        PlayerPrefs.SetString(SaveKey, json);
        PlayerPrefs.Save();

        Debug.Log("[PetState] LOCAL DEMO state saved.");
    }

    public void LoadPetData()
    {
        if (ServerAuthority) return;
        if (!PlayerPrefs.HasKey(SaveKey))
        {
            Debug.Log("[PetState] 기존 저장 데이터 없음");
            return;
        }

        string json = PlayerPrefs.GetString(SaveKey);

        try
        {
            PetSaveData data =
                JsonUtility.FromJson<PetSaveData>(json);

            if (data == null)
                return;

            petName = data.petName;
            level = Mathf.Max(1, data.level);
            currentExp = Mathf.Max(0, data.currentExp);
            expToNextLevel = Mathf.Max(1, data.expToNextLevel);
            coin = Mathf.Max(0, data.coin);

            intimacy = Mathf.Clamp(data.intimacy, 0, 100);
            activity = Mathf.Clamp(data.activity, 0, 100);
            kindness = Mathf.Clamp(data.kindness, 0, 100);
            curiosity = Mathf.Clamp(data.curiosity, 0, 100);

            growthStage = data.growthStage;

            RefreshAllUI();

            Debug.Log("[PetState] 불러오기 완료");
        }
        catch (System.Exception e)
        {
            Debug.LogError("[PetState] 불러오기 실패: " + e.Message);
        }
    }

    // ==========================================
    // 관리자 모드용 데이터 조회
    // ==========================================

    public int CurrentLevel => level;
    public int CurrentCoin => coin;

    public int CurrentIntimacy => intimacy;
    public int CurrentActivity => activity;
    public int CurrentKindness => kindness;
    public int CurrentCuriosity => curiosity;


    // ==========================================
    // 관리자 모드용 스탯 변경
    // ==========================================

    public void SetAdminValues(
        int newLevel,
        int newCoin,
        int newIntimacy,
        int newActivity,
        int newKindness,
        int newCuriosity)
    {
        if (ServerAuthority) return;
        level = Mathf.Max(1, newLevel);
        coin = Mathf.Max(0, newCoin);

        intimacy = Mathf.Clamp(newIntimacy, 0, 100);
        activity = Mathf.Clamp(newActivity, 0, 100);
        kindness = Mathf.Clamp(newKindness, 0, 100);
        curiosity = Mathf.Clamp(newCuriosity, 0, 100);

        LevelChanged?.Invoke(level);

        // 화면 갱신
        RefreshAllUI();

        // 데이터 저장 (이전 단계에서 구현한 함수)
        SavePetData();

        Debug.Log(
            $"[Admin] 스탯 변경 완료 | " +
            $"Lv.{level} | Coin:{coin} | " +
            $"친밀도:{intimacy} | 활동성:{activity} | " +
            $"다정함:{kindness} | 호기심:{curiosity}"
        );
    }

   

}
