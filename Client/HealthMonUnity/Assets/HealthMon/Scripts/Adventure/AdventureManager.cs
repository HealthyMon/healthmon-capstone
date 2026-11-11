using TMPro;
using UnityEngine;
using UnityEngine.UI;

public enum ExplorationState
{
    Entrance,
    Exploring,
    Failed
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

    [Header("Dialogue")]
    [SerializeField]
    private AdventureDialogueManager dialogueManager;

    private bool isMoving;

    private bool isEventCompleted;
    public int CurrentFloor => currentFloor;
    public ExplorationState State => state;

    private void OnEnable()
    {
        if (battleController != null) battleController.BattleFinished += OnBattleFinished;
    }
    private void OnDisable()
    {
        if (battleController != null) battleController.BattleFinished -= OnBattleFinished;
    }
    private void Start() => InitializeExploration();

    private void InitializeExploration()
    {
        currentFloor = 0;
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

        StartFloorTransition();
    }
    public void DescendFloor()
    {
        if (state != ExplorationState.Exploring || !isEventCompleted || isMoving)
            return;

        StartFloorTransition();
    }
    private void StartFloorTransition()
    {
        isMoving = true;

        // 입구에서 시작했다면 입구 덮개를 먼저 숨김
        if (state == ExplorationState.Entrance &&
            entrancePanel != null)
        {
            entrancePanel.SetActive(false);
        }

        if (descendButton != null)
            descendButton.interactable = false;

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

            CompleteEvent();
            return;
        }

        AdventureEventType type = evt.Value;

        // 전투 이벤트
        if (type == AdventureEventType.Battle ||
            type == AdventureEventType.EliteBattle)
        {
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



    private void OnBattleFinished(bool victory)
    {
        if (state != ExplorationState.Exploring)
            return;

        if (victory)
        {
            AddLog("전투 승리");

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
            state = ExplorationState.Failed;

            AddLog("전투 패배: 탐험 실패");

            if (dialogueManager != null)
            {
                dialogueManager.ShowDialogue(
                    AdventureDialogueType.Defeat
                );
            }

            UpdateUI();
        }
    }

    private void CompleteEvent()
    {
        isEventCompleted = true;
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
            descendButton.interactable = state == ExplorationState.Exploring
                                            && isEventCompleted
                                             && !isMoving;
        }
    }
}
