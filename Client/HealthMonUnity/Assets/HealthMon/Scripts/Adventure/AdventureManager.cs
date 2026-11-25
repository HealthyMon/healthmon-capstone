using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public enum ExplorationState
{
    Entrance,
    Exploring,
    Failed,
    Resting,
    Ended
}

public class AdventureManager : MonoBehaviour
{
    [Header("탐험 상태")]
    [SerializeField] private int currentFloor;
    [SerializeField] private ExplorationState state;

    [Header("매니저")]
    [SerializeField] private AdventureEventManager eventManager;
    [SerializeField] private BattleController battleController;

    [Header("화면")]
    [SerializeField] private GameObject entrancePanel;
    [SerializeField] private GameObject floorPanel;

    [Header("층 UI")]
    [SerializeField] private TMP_Text floorText;
    [SerializeField] private TMP_Text eventText;
    [SerializeField] private TMP_Text eventLogText;
    [SerializeField] private Button descendButton;
    [SerializeField] private AdventureTransitionUI transitionUI;

    [Header("이벤트 배경 이미지")]
    [SerializeField] private AdventureEventBackgroundUI eventBackgroundUI;

    [Header("Dialogue")]
    [SerializeField]
    private AdventureDialogueManager dialogueManager;

    [Header("정예 전투 후 휴식")]
    [SerializeField, Range(0f, 1f)] private float hpRecoveryRate = 0.3f;
    [SerializeField, Range(0f, 1f)] private float stRecoveryRate = 0.5f;

    [Header("탐험 시작 방식")]
    [SerializeField] private bool startAtCheckpoint;

    [Header("보상 이벤트")]
    [SerializeField] private AdventureRewardEventUI rewardEventUI;

    [Header("일반층 휴식 이벤트")]
    [SerializeField] private AdventureRestEventUI restEventUI;
    [SerializeField, Range(0f, 1f)] private float eventHpRecoveryRate = 0.3f;
    [SerializeField, Range(0f, 1f)] private float eventStRecoveryRate = 0.3f;

    [Header("퀴즈 이벤트")]
    [SerializeField] private AdventureQuizDatabase quizDatabase;
    [SerializeField] private AdventureQuizEventUI quizEventUI;
    [SerializeField] private string[] quizRewardItemIds = { "potion_hp_01", "potion_st_01", "potion_all_01" };
    [SerializeField] private int quizAtkBonus = 3;
    [SerializeField] private int quizOtherStatBonus = 2;
    private AdventureQuizQuestion activeQuiz;
    private AdventureStatType quizRewardStat;
    private float quizRewardAmount;
    private string quizRewardItemId;

    [Header("특별 이벤트")]
    [SerializeField] private AdventureSpecialDatabase specialDatabase;
    [SerializeField] private AdventureSpecialEventUI specialEventUI;
    private AdventureSpecialEvent activeSpecial;

    private AdventureStatType pendingRestStat;
    private float pendingRestAmount;

    [Header("탐험 종료")]
    [SerializeField] private Button endAdventureButton;

    public AdventureResultData LastResult { get; private set; }
    public event System.Action<AdventureResultData> AdventureEnded;

    private float startedAt;
    private int startFloor, startClearedFloors, startEnemies, startBosses, startEvents;
    private AdventurePlayerStats playerStats;

    public void SetStartAtCheckpoint(bool value)
    {
        if (state == ExplorationState.Entrance && !isMoving)
            startAtCheckpoint = value;
    }

    private void Awake()
    {
        playerStats = GetComponent<AdventurePlayerStats>();
        inventory = GetComponent<AdventureInventory>();
    }

    private int clearedFloors;
    private int defeatedEnemies;
    private int defeatedBosses;
    private int completedEvents;
    private AdventureInventory inventory;
    private bool isMoving;

    private bool isEventCompleted;
    public int CurrentFloor => currentFloor;
    public ExplorationState State => state;
    // Do not use during movement or combat (including battle intro / result).
    public bool CanUseExplorationItem => !isMoving && isEventCompleted &&
        (state == ExplorationState.Exploring || state == ExplorationState.Resting) &&
        (battleController == null || !battleController.IsBattling);
    public AdventureInventory Inventory => inventory;

    private void OnEnable()
    {
        if (battleController != null) battleController.BattleFinished += OnBattleFinished;
    }
    private void OnDisable()
    {
        if (battleController != null) battleController.BattleFinished -= OnBattleFinished;
    }
    private void Start()
    {
        InitializeExploration();

        // 메인에서 시작 방식을 선택해도 탐험 입구 화면에서 대기한다.
        // 입구의 기존 탐험 시작 버튼이 눌리면 새 탐험/체크포인트를 구분한다.
        if (AdventureLaunchSettings.HasPendingLaunch)
        {
            startAtCheckpoint = AdventureLaunchSettings.SelectedRegion == AdventureLaunchSettings.Region.Checkpoint;
            AdventureLaunchSettings.ConsumeLaunch();
        }
    }

    private void InitializeExploration()
    {
        if (battleController != null) battleController.HideBattleEnvironment();
        if (eventBackgroundUI != null) eventBackgroundUI.Hide();
        LastResult = null;
        startFloor = startClearedFloors = startEnemies = startBosses = startEvents = 0;
        currentFloor = 0;
        clearedFloors = defeatedEnemies = defeatedBosses = completedEvents = 0;
        if (inventory != null) inventory.Clear();
        state = ExplorationState.Entrance;
        isEventCompleted = false;
        if (eventLogText != null) eventLogText.text = "";
        UpdateUI();
        Debug.Log("[Exploration] 입구 진입");

        if (dialogueManager != null)
        {
            dialogueManager.ShowDialogue(
                AdventureDialogueType.Entrance
            );
        }
    }

    public void EnterExploration()
    {
        if (state != ExplorationState.Entrance || isMoving)
            return;

        if (playerStats == null || !playerStats.RefreshGrowthStats())
        {
            AddLog("캐릭터 스탯을 불러온 뒤 탐험을 시작해 주세요.");
            return;
        }

        startedAt = Time.realtimeSinceStartup;
        if (startAtCheckpoint)
        {
            if (!TryRestoreCheckpoint())
            {
                AddLog("저장된 체크포인트 복원 실패: 탐험 입구에 머무릅니다.");
                return;
            }
            return;
        }

        StartFloorTransition();
    }
    public void DescendFloor()
    {
        if ((state != ExplorationState.Exploring &&
             state != ExplorationState.Resting) ||
            !isEventCompleted || isMoving)
            return;

        StartFloorTransition();
    }
    private void StartFloorTransition()
    {
        if (battleController != null) battleController.HideBattleEnvironment();
        if (eventBackgroundUI != null) eventBackgroundUI.Hide();
        isMoving = true;

        // 입구에서 시작했다면 입구 덮개를 먼저 숨김
        if (state == ExplorationState.Entrance &&
            entrancePanel != null)
        {
            entrancePanel.SetActive(false);
        }

        if (descendButton != null)
            descendButton.interactable = false;
        if (endAdventureButton != null)
        {
            endAdventureButton.interactable = false;
            endAdventureButton.gameObject.SetActive(false);
        }

        if (transitionUI != null)
            transitionUI.PlayDescend(FinishFloorTransition);
        else
            FinishFloorTransition();
    }
    private void FinishFloorTransition()
    {
        isMoving = false;
        state = ExplorationState.Exploring;

        MoveToNextFloor();
    }
    private void MoveToNextFloor()
    {
        currentFloor++;
        isEventCompleted = false;
        if (eventText != null) eventText.text = "";
        UpdateUI();
        AddLog($"{currentFloor}층 진입");
        GenerateFloorEvent();
    }


    private void GenerateFloorEvent()
    {
        if (eventManager == null)
        {
            AddLog("오류: AdventureEventManager 미연결");
            return;
        }

        AdventureEventType? evt =
            eventManager.GenerateEvent(currentFloor);

        if (!evt.HasValue)
        {
            if (dialogueManager != null)
            {
                dialogueManager.ShowDialogue(
                    AdventureDialogueType.NoEvent
                );
            }

            CompleteEvent(false);
            return;
        }

        AdventureEventType type = evt.Value;

        // 전투 이벤트
        if (type == AdventureEventType.Battle ||
            type == AdventureEventType.EliteBattle)
        {
            if (eventBackgroundUI != null) eventBackgroundUI.Hide();
            bool elite =
                type == AdventureEventType.EliteBattle;

            string label = elite ? "정예 전투" : "일반 전투";

            AddLog($"{label} 발생");

            if (battleController == null)
            {
                AddLog("오류: BattleController 미연결");
                return;
            }

            // 대사는 AdventureTransitionUI에서 표시
            // 연출 완료 후 실제 전투가 시작됨
            if (dialogueManager != null &&
                transitionUI == null)
            {
                dialogueManager.ShowDialogue(
                    elite
                        ? AdventureDialogueType.EliteBattle
                        : AdventureDialogueType.Battle
                );
            }

            battleController.StartBattle(elite);
            return;
        }

        // 보상 이벤트: 플레이어가 수령하기 전까지 층 완료를 보류한다.
        if (type == AdventureEventType.Reward)
        {
            if (rewardEventUI != null && rewardEventUI.BeginReward(inventory, ClaimReward))
            {
                if (eventBackgroundUI != null) eventBackgroundUI.Show(AdventureEventType.Reward);
                if (eventText != null) eventText.text = "보상 이벤트";
                if (dialogueManager != null)
                    dialogueManager.SetDialogue("전투에 도움이 되는 물품을 발견했다.\n아이템을 수령하자.");
                AddLog("보상 이벤트 발생: 아이템 수령 대기");
                return;
            }
            // DB 또는 지급 가능한 아이템이 없다면 다음 층 진행을 막지 않는다.
            Debug.LogWarning("[Exploration] 보상 이벤트 UI/아이템 데이터가 없어 보상을 건너뜁니다.");
            if (dialogueManager != null)
                dialogueManager.SetDialogue("아이템을 찾지 못했다. 다음 층으로 이동하자.");
            CompleteEvent(false);
            return;
        }

        // 일반층 휴식 이벤트: 플레이어가 선택할 때까지 층 완료를 보류한다.
        // 정예 전투 후 체크포인트 휴식(EnterRestArea)과 분리한다.
        if (type == AdventureEventType.Rest)
        {
            BeginRandomRestEvent();
            return;
        }

        if (type == AdventureEventType.Quiz)
        {
            BeginQuizEvent();
            return;
        }

        if (type == AdventureEventType.Special)
        {
            BeginSpecialEvent();
            return;
        }

        // 일반 이벤트
        AdventureDialogueType dialogueType;

        switch (type)
        {
            case AdventureEventType.Reward:
                dialogueType = AdventureDialogueType.Reward;
                break;

            case AdventureEventType.Rest:
                dialogueType = AdventureDialogueType.Rest;
                break;

            case AdventureEventType.Quiz:
                dialogueType = AdventureDialogueType.Quiz;
                break;

            case AdventureEventType.Special:
                dialogueType = AdventureDialogueType.Special;
                break;

            default:
                dialogueType = AdventureDialogueType.NoEvent;
                break;
        }

        if (dialogueManager != null)
            dialogueManager.ShowDialogue(dialogueType);

        AddLog($"{type} 이벤트 발생");

        // 아직 구현되지 않은 이벤트는 즉시 완료
        CompleteEvent();
    }



    private bool CanResolveSpecial() => state == ExplorationState.Exploring &&
        !isMoving && !isEventCompleted &&
        (battleController == null || !battleController.IsBattling);

    private void BeginSpecialEvent()
    {
        if (specialDatabase == null || specialEventUI == null ||
            playerStats == null || !playerStats.IsInitialized ||
            !specialDatabase.TryRandom(out activeSpecial))
        {
            Debug.LogWarning("[Exploration] 특별 이벤트 데이터/UI 미설정. 이벤트를 건너뜁니다.");
            CompleteEvent(false);
            return;
        }

        if (!specialEventUI.Begin(currentFloor, activeSpecial, ResolveSpecialChoice))
        {
            activeSpecial = null;
            Debug.LogWarning("[Exploration] 특별 이벤트 UI를 열지 못했습니다.");
            CompleteEvent(false);
            return;
        }
        if (eventBackgroundUI != null) eventBackgroundUI.ShowSpecial(activeSpecial.title);
        if (eventText != null) eventText.text = "특별 이벤트";
        if (dialogueManager != null)
            dialogueManager.SetDialogue(activeSpecial.description + "\n선택의 결과는 알 수 없다.");
        AddLog($"{currentFloor}층 특별 이벤트 발생: 선택 대기");
    }

    private void ResolveSpecialChoice(int index)
    {
        if (!CanResolveSpecial() || activeSpecial == null || specialEventUI == null) return;
        if (index < 0) // 그냥 지나가기
        {
            ShowSpecialResult("아무것도 하지 않고 지나갔다.");
            return;
        }
        if (activeSpecial.choices == null || index >= activeSpecial.choices.Count) return;

        var choice = activeSpecial.choices[index];
        if (choice == null || !choice.TryRoll(out var outcome))
        {
            ShowSpecialResult("아무 일도 일어나지 않았다.");
            return;
        }
        string detail;
        switch (outcome.kind)
        {
            case AdventureSpecialOutcomeKind.StatChange:
                // 이벤트 피해로는 HP가 0이 되지 않도록 최소 1을 보장한다.
                // 전투의 피해 및 패배 판정은 기존 BattleManager가 담당한다.
                float amount = outcome.amount;
                if (outcome.stat == AdventureStatType.HP && amount < 0f)
                {
                    amount = Mathf.Max(amount, 1f - playerStats.CurrentHP);
                }
                float changed = playerStats.ModifyStat(outcome.stat, amount);
                detail = $"{outcome.stat} {(changed >= 0 ? "+" : "")}{changed:0.##}";
                break;
            case AdventureSpecialOutcomeKind.Item:
                if (inventory != null && !string.IsNullOrWhiteSpace(outcome.itemId) &&
                    inventory.AddItem(outcome.itemId, Mathf.Max(1, outcome.count)))
                {
                    var definition = inventory.Database != null ? inventory.Database.Find(outcome.itemId) : null;
                    string itemName = definition != null && !string.IsNullOrWhiteSpace(definition.itemName)
                        ? definition.itemName : outcome.itemId;
                    detail = $"{itemName} ×{Mathf.Max(1, outcome.count)} 획득";
                }
                else detail = "아이템을 획득하지 못했다. (데이터베이스 연결 확인)";
                break;
            default:
                detail = "변화 없음";
                break;
        }
        string description = string.IsNullOrWhiteSpace(outcome.resultText) ? "선택의 결과가 나타났다." : outcome.resultText;
        string result = description + "\n" + detail;
        AddLog("특별 이벤트 결과: " + result.Replace("\n", " / "));
        ShowSpecialResult(result);
    }

    private void ShowSpecialResult(string result)
    {
        if (specialEventUI != null) specialEventUI.ShowResult(result, FinishSpecialEvent);
    }

    private void FinishSpecialEvent()
    {
        if (!CanResolveSpecial()) return;
        if (dialogueManager != null)
            dialogueManager.SetDialogue("특별 이벤트 종료.\n다음 층으로 이동할 수 있다.");
        CompleteEvent();
        activeSpecial = null;
        if (specialEventUI != null) specialEventUI.Close();
    }

    private void BeginQuizEvent()
    {
        if (quizDatabase == null || quizEventUI == null ||
            playerStats == null || !playerStats.IsInitialized ||
            !quizDatabase.TryRandom(out activeQuiz))
        {
            Debug.LogWarning("[Exploration] 퀴즈 데이터/UI 미설정. 퀴즈 이벤트를 건너뜁니다.");
            CompleteEvent(false);
            return;
        }
        AdventureStatType[] stats = {
            AdventureStatType.ATK, AdventureStatType.DEF, AdventureStatType.RES,
            AdventureStatType.SPD, AdventureStatType.LUK
        };
        quizRewardStat = stats[Random.Range(0, stats.Length)];
        quizRewardAmount = quizRewardStat == AdventureStatType.ATK ? quizAtkBonus : quizOtherStatBonus;
        quizRewardItemId = null;
        if (inventory != null && inventory.Database != null && quizRewardItemIds != null)
        {
            var candidates = new List<string>();
            foreach (var id in quizRewardItemIds)
                if (!string.IsNullOrEmpty(id) && inventory.Database.Find(id) != null &&
                    !candidates.Contains(id)) candidates.Add(id);
            if (candidates.Count > 0) quizRewardItemId = candidates[Random.Range(0, candidates.Count)];
        }
        if (!quizEventUI.Begin(currentFloor, activeQuiz, AnswerQuiz))
        {
            Debug.LogWarning("[Exploration] 퀴즈 UI 시작 실패");
            CompleteEvent(false);
            return;
        }
        if (eventBackgroundUI != null) eventBackgroundUI.Show(AdventureEventType.Quiz);
        if (eventText != null) eventText.text = "퀴즈 이벤트";
        if (dialogueManager != null) dialogueManager.SetDialogue("건강 상식 퀴즈를 풀어 보자.");
        AddLog($"{currentFloor}층 퀴즈 시작");
    }

    private bool CanResolveQuiz() => state == ExplorationState.Exploring && !isMoving &&
        !isEventCompleted && (battleController == null || !battleController.IsBattling);

    private void AnswerQuiz(int index)
    {
        if (!CanResolveQuiz() || activeQuiz == null) return;
        string explanation = activeQuiz.explanation ?? "";
        if (index != activeQuiz.correctIndex)
        {
            quizEventUI.ShowIncorrect(explanation, FinishQuizWithoutReward);
            AddLog("퀴즈 오답");
            return;
        }
        string itemLabel = "아이템 보상 없음";
        if (!string.IsNullOrEmpty(quizRewardItemId))
        {
            var item = inventory.Database.Find(quizRewardItemId);
            itemLabel = "아이템: " + (string.IsNullOrEmpty(item.itemName) ? item.itemId : item.itemName) + " ×1";
        }
        float previous = playerStats.GetStatValue(quizRewardStat);
        string statLabel = $"{quizRewardStat} +{quizRewardAmount:0.##} ({previous:0.##} → {previous + quizRewardAmount:0.##})";
        quizEventUI.ShowCorrect(explanation, itemLabel, statLabel,
            !string.IsNullOrEmpty(quizRewardItemId), ApplyQuizReward);
        AddLog("퀴즈 정답: 보상 선택 대기");
    }

    private void ApplyQuizReward(bool chooseItem)
    {
        if (!CanResolveQuiz()) return;
        string message;
        if (chooseItem)
        {
            if (string.IsNullOrEmpty(quizRewardItemId) || inventory == null ||
                !inventory.AddItem(quizRewardItemId, 1)) return;
            var item = inventory.Database.Find(quizRewardItemId);
            message = "퀴즈 보상 아이템: " + (string.IsNullOrEmpty(item.itemName) ? item.itemId : item.itemName);
        }
        else
        {
            float gained = playerStats.ModifyStat(quizRewardStat, quizRewardAmount);
            message = $"퀴즈 스탯 강화: {quizRewardStat} +{gained:0.##}";
        }
        FinishQuizEvent(message);
    }

    private void FinishQuizWithoutReward()
    {
        if (CanResolveQuiz()) FinishQuizEvent("퀴즈 오답: 보상 없음");
    }

    private void FinishQuizEvent(string message)
    {
        if (dialogueManager != null) dialogueManager.SetDialogue(message + "\n다음 층으로 이동할 수 있다.");
        AddLog(message);
        CompleteEvent();
        activeQuiz = null;
        if (quizEventUI != null) quizEventUI.Close();
    }

    private void BeginRandomRestEvent()
    {
        if (playerStats == null || !playerStats.IsInitialized || restEventUI == null)
        {
            Debug.LogWarning("[Exploration] 일반층 휴식 UI 또는 플레이어 스탯이 없어 이벤트를 건너뜁니다.");
            if (dialogueManager != null)
                dialogueManager.SetDialogue("휴식 장소를 발견했지만 이용할 수 없다.");
            CompleteEvent(false);
            return;
        }

        // 이벤트마다 강화할 스탯과 증가량을 미리 확정한다.
        // 강화 대상은 현재 HP/ST가 아닌 전투 기본 능력치 5종이다.
        AdventureStatType[] choices = {
            AdventureStatType.ATK, AdventureStatType.DEF, AdventureStatType.RES,
            AdventureStatType.SPD, AdventureStatType.LUK
        };
        pendingRestStat = choices[Random.Range(0, choices.Length)];
        switch (pendingRestStat)
        {
            case AdventureStatType.ATK: pendingRestAmount = 3f; break;
            case AdventureStatType.DEF: pendingRestAmount = 2f; break;
            case AdventureStatType.RES: pendingRestAmount = 2f; break;
            case AdventureStatType.SPD: pendingRestAmount = 2f; break;
            default: pendingRestAmount = 2f; break;
        }

        int hpGain = Mathf.Min(
            Mathf.Max(0, playerStats.MaxHP - playerStats.CurrentHP),
            Mathf.RoundToInt(playerStats.MaxHP * eventHpRecoveryRate));
        float stGain = Mathf.Min(
            Mathf.Max(0f, playerStats.MaxST - playerStats.CurrentST),
            playerStats.MaxST * eventStRecoveryRate);

        string recoveryPreview = $"HP +{hpGain} / ST +{stGain:0.##}";
        float current = playerStats.GetStatValue(pendingRestStat);
        string buffPreview = $"{pendingRestStat} +{pendingRestAmount:0}  ({current:0.##} → {current + pendingRestAmount:0.##})";

        if (!restEventUI.BeginRest(currentFloor, recoveryPreview, buffPreview, ApplyRandomRestChoice))
        {
            Debug.LogWarning("[Exploration] 일반층 휴식 UI를 열지 못했습니다.");
            CompleteEvent(false);
            return;
        }
        if (eventBackgroundUI != null) eventBackgroundUI.Show(AdventureEventType.Rest);

        if (eventText != null) eventText.text = "휴식 이벤트";
        if (dialogueManager != null)
            dialogueManager.SetDialogue("안전한 휴식 장소를 찾았다.\n회복하거나 능력치를 강화할 수 있다.");
        AddLog($"{currentFloor}층 휴식 이벤트 발생: 선택 대기");
    }

    private void ApplyRandomRestChoice(bool recover)
    {
        if (state != ExplorationState.Exploring || isMoving || isEventCompleted ||
            (battleController != null && battleController.IsBattling) ||
            playerStats == null || !playerStats.IsInitialized)
            return;

        string message;
        if (recover)
        {
            float hp = playerStats.ModifyStat(
                AdventureStatType.HP, Mathf.RoundToInt(playerStats.MaxHP * eventHpRecoveryRate));
            float st = playerStats.ModifyStat(
                AdventureStatType.ST, playerStats.MaxST * eventStRecoveryRate);
            message = $"휴식을 취했다. HP +{hp:0}, ST +{st:0.##}";
        }
        else
        {
            float applied = playerStats.ModifyStat(pendingRestStat, pendingRestAmount);
            message = $"능력치 강화: {pendingRestStat} +{applied:0.##}";
        }

        if (dialogueManager != null)
            dialogueManager.SetDialogue(message + "\n다음 층으로 이동할 수 있다.");
        AddLog(message);
        CompleteEvent();
        if (restEventUI != null) restEventUI.FinishRest();
    }

    private void ClaimReward(string itemId)
    {
        if (state != ExplorationState.Exploring || isMoving || isEventCompleted ||
            inventory == null || inventory.Database == null ||
            inventory.Database.Find(itemId) == null)
            return;

        if (!inventory.AddItem(itemId, 1))
        {
            Debug.LogWarning("[Exploration] 아이템 지급 실패: " + itemId);
            return;
        }
        var item = inventory.Database.Find(itemId);
        string displayName = string.IsNullOrEmpty(item.itemName) ? itemId : item.itemName;
        if (dialogueManager != null)
            dialogueManager.SetDialogue(displayName + " 1개를 획득했다!\n가방에서 확인할 수 있다.");
        AddLog("아이템 획득: " + displayName + " x1");
        CompleteEvent();
        if (rewardEventUI != null) rewardEventUI.FinishReward();
    }

    private void OnBattleFinished(bool victory)
    {
        if (state != ExplorationState.Exploring || isEventCompleted)
            return;

        if (victory)
        {
            AddLog("전투 승리");
            if (currentFloor > 0 && currentFloor % 10 == 0)
                defeatedBosses++;
            else
                defeatedEnemies++;

            if (currentFloor > 0 && currentFloor % 10 == 0)
            {
                EnterRestArea();
                return;
            }

            if (dialogueManager != null)
            {
                dialogueManager.ShowDialogue(
                    AdventureDialogueType.Victory
                );
            }

            CompleteEvent();
        }
        else
        {
            EndAdventure(AdventureEndReason.Defeat);
        }
    }

    private void EnterRestArea()
    {
        if (state != ExplorationState.Exploring || isEventCompleted)
            return;

        // 같은 층에서 휴식: 정예 전투 및 회복 중복 실행 방지
        state = ExplorationState.Resting;

        int recoveredHP = 0;
        float recoveredST = 0f;
        bool canRecover = playerStats != null && playerStats.IsInitialized;

        if (canRecover)
        {
            int previousHP = playerStats.CurrentHP;
            float previousST = playerStats.CurrentST;

            playerStats.Heal(Mathf.RoundToInt(
                playerStats.MaxHP * hpRecoveryRate));
            playerStats.RecoverST(
                playerStats.MaxST * stRecoveryRate);

            recoveredHP = playerStats.CurrentHP - previousHP;
            recoveredST = playerStats.CurrentST - previousST;
        }
        else
        {
            Debug.LogError("[Exploration] AdventurePlayerStats 미연결 또는 초기화 실패");
        }

        if (eventText != null)
            eventText.text = "휴식 공간";

        if (dialogueManager != null)
        {
            string restDialogue = dialogueManager.GetDialogue(
                AdventureDialogueType.Rest);

            string recoveryText = canRecover
                ? $"HP +{recoveredHP}, ST +{recoveredST:0.##}"
                : "회복 데이터를 불러올 수 없다.";

            dialogueManager.SetDialogue(
                "정예 몬스터를 처치했다!\n" +
                restDialogue + "\n" + recoveryText);
        }

        AddLog($"{currentFloor}층 휴식 공간 진입");
        if (canRecover)
            AddLog($"휴식 회복: HP +{recoveredHP}, ST +{recoveredST:0.##}");

        CompleteEvent();
        SaveCheckpoint();
    }

    private void SaveCheckpoint()
    {
        if (state != ExplorationState.Resting || !isEventCompleted ||
            inventory == null || inventory.Database == null || playerStats == null || !playerStats.IsInitialized || !playerStats.IsAlive)
            return;

        var data = new AdventureSaveData
        {
            checkpointFloor = currentFloor,
            clearedFloors = clearedFloors,
            defeatedEnemies = defeatedEnemies,
            defeatedBosses = defeatedBosses,
            completedEvents = completedEvents,
            playerStats = playerStats.CreateSnapshot(),
            items = inventory != null ? inventory.CreateSnapshot() : new List<AdventureItemData>(),
            savedAt = System.DateTime.UtcNow.ToString("o")
        };

        AddLog(AdventureSaveSystem.TrySave(data)
            ? "체크포인트 저장 완료" : "체크포인트 저장 실패");
    }

    private bool TryRestoreCheckpoint()
    {
        if (!AdventureSaveSystem.TryLoad(out var data))
            return false;

        if (inventory == null || inventory.Database == null ||
            data.items == null ||
            data.items.Exists(x => x == null || x.count <= 0 ||
                                inventory.Database.Find(x.itemId) == null) ||
            playerStats == null || !playerStats.RestoreSnapshot(data.playerStats))
        {
            Debug.LogError("[Exploration] 체크포인트 스탯/아이템 검증 실패");
            return false;
        }

        currentFloor = data.checkpointFloor;
        clearedFloors = data.clearedFloors;
        defeatedEnemies = data.defeatedEnemies;
        defeatedBosses = data.defeatedBosses;
        completedEvents = data.completedEvents;
        if (inventory == null || !inventory.RestoreSnapshot(data.items))
        {
            Debug.LogError("[Exploration] 체크포인트 인벤토리 복원 실패");
            return false;
        }
        startFloor = currentFloor;
        startClearedFloors = clearedFloors;
        startEnemies = defeatedEnemies;
        startBosses = defeatedBosses;
        startEvents = completedEvents;
        state = ExplorationState.Resting;
        isMoving = false;
        isEventCompleted = true;

        if (eventText != null) eventText.text = "휴식 공간";
        if (dialogueManager != null)
            dialogueManager.SetDialogue("저장된 휴식 공간으로 돌아왔다.\n다음 층으로 이동할 수 있다.");

        AddLog($"{currentFloor}층 체크포인트 불러오기 완료");
        UpdateUI();
        return true;
    }

    // Connect the existing/new exit button OnClick to this method.
    public void RequestEndAdventure()
    {
        if (!CanEndVoluntarily()) return;
        EndAdventure(AdventureEndReason.Voluntary);
    }

    private bool CanEndVoluntarily()
    {
        return state == ExplorationState.Resting
            && isEventCompleted && !isMoving
            && (battleController == null ||
                !battleController.IsBattling);
    }

    private void EndAdventure(AdventureEndReason reason)
    {
        if (LastResult != null || state == ExplorationState.Entrance ||
            state == ExplorationState.Ended || state == ExplorationState.Failed || isMoving ||
            (battleController != null && battleController.IsBattling)) return;

        state = reason == AdventureEndReason.Defeat
            ? ExplorationState.Failed : ExplorationState.Ended;
        if (battleController != null) battleController.HideBattleEnvironment();
        if (eventBackgroundUI != null) eventBackgroundUI.Hide();

        var result = new AdventureResultData
        {
            endReason = reason,
            startFloor = startFloor,
            reachedFloor = currentFloor,
            clearedFloors = clearedFloors,
            defeatedEnemies = defeatedEnemies,
            defeatedBosses = defeatedBosses,
            completedEvents = completedEvents,
            sessionClearedFloors = clearedFloors - startClearedFloors,
            sessionDefeatedEnemies = defeatedEnemies - startEnemies,
            sessionDefeatedBosses = defeatedBosses - startBosses,
            sessionCompletedEvents = completedEvents - startEvents,
            elapsedSeconds = Mathf.Max(0f, Time.realtimeSinceStartup - startedAt),
            playerStats = playerStats != null && playerStats.IsInitialized
                ? playerStats.CreateSnapshot() : null
        };
        if (inventory != null) result.items = inventory.CreateSnapshot();

        LastResult = result;
        isEventCompleted = false;
        UpdateUI();

        string reasonText = reason == AdventureEndReason.Defeat ? "전투 패배" : "자발적 종료";
        if (eventText != null) eventText.text = "탐험 결과";
        if (dialogueManager != null)
            dialogueManager.SetDialogue($"{reasonText} | 도달 {result.reachedFloor}층\n" +
                $"완료 {result.clearedFloors}층 | 일반 {result.defeatedEnemies} / 정예 {result.defeatedBosses}\n" +
                $"완료 이벤트 {result.completedEvents}개");
        AddLog($"탐험 종료: {reasonText}");
        AddLog($"이번 탐험: 완료 {result.sessionClearedFloors}층, 일반 {result.sessionDefeatedEnemies}, 정예 {result.sessionDefeatedBosses}");
        AdventureEnded?.Invoke(result);
    }

    private void CompleteEvent(bool countEvent = true)
    {
        if (isEventCompleted) return;
        isEventCompleted = true;
        clearedFloors = currentFloor;
        if (countEvent) completedEvents++;
        AddLog($"{currentFloor}층 완료");
        UpdateUI();
    }
    private void AddLog(string msg)
    {
        Debug.Log("[Exploration] " + msg);
        if (eventLogText != null) eventLogText.text = msg + "\n" + eventLogText.text;
    }
    private void UpdateUI()
    {
        if (entrancePanel != null) entrancePanel.SetActive(state == ExplorationState.Entrance);
        if (floorPanel != null) floorPanel.SetActive(state != ExplorationState.Entrance);
        if (floorText != null) floorText.text = currentFloor + "층";
        if (descendButton != null)
        {
            descendButton.interactable =
                (state == ExplorationState.Exploring ||
                 state == ExplorationState.Resting) &&
                isEventCompleted && !isMoving;
        }
        if (endAdventureButton != null)
        {
            bool canEnd = CanEndVoluntarily();

            endAdventureButton.gameObject.SetActive(canEnd);
            endAdventureButton.interactable = canEnd;
        }
    }


}
