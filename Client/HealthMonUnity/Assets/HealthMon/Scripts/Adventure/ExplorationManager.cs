
using TMPro;
using UnityEngine;

public enum ExplorationState
{
    Entrance,
    Exploring
}

public class ExplorationManager : MonoBehaviour
{
    [Header("Exploration Status")]
    [SerializeField] private int currentFloor = 0;
    [SerializeField] private ExplorationState state;

    [Header("Managers")]
    [SerializeField]
    private ExplorationEventManager eventManager;

    [Header("UI Panels")]
    [SerializeField] private GameObject entrancePanel;
    [SerializeField] private GameObject floorPanel;

    [Header("Floor UI")]
    [SerializeField] private TMP_Text floorText;
    [SerializeField] private TMP_Text eventText;
    [SerializeField] private TMP_Text eventLogText;

    public int CurrentFloor => currentFloor;
    public ExplorationState State => state;

    private void Start()
    {
        InitializeExploration();
    }

    private void InitializeExploration()
    {
        currentFloor = 0;
        state = ExplorationState.Entrance;

        if (eventLogText != null)
            eventLogText.text = "";

        UpdateUI();

        Debug.Log("[Exploration] 탐험 입구 진입");
    }

    // 입구에서 탐험 시작
    public void EnterExploration()
    {
        if (state != ExplorationState.Entrance)
            return;

        state = ExplorationState.Exploring;

        MoveToNextFloor();
    }

    // 다음 층으로 내려가기
    public void DescendFloor()
    {
        if (state != ExplorationState.Exploring)
            return;

        MoveToNextFloor();
    }

    // 공통 층 이동 처리
    private void MoveToNextFloor()
    {
        currentFloor++;

        UpdateUI();

        Debug.Log($"[Exploration] {currentFloor}층 진입");

        GenerateFloorEvent();
    }

    // 층별 이벤트 생성
    private void GenerateFloorEvent()
    {
        if (eventManager == null)
        {
            Debug.LogWarning(
                "[Exploration] EventManager가 연결되지 않았습니다."
            );
            return;
        }

        ExplorationEventType? eventType =
            eventManager.GenerateEvent();

        if (!eventType.HasValue)
        {
            if (eventText != null)
                eventText.text = "이벤트 없음";

            AddEventLog($"{currentFloor}층: 이벤트 없음");
            return;
        }

        string eventName = GetEventName(eventType.Value);

        if (eventText != null)
            eventText.text = eventName;

        AddEventLog(
            $"{currentFloor}층: {eventName} 발생"
        );
    }

    private string GetEventName(ExplorationEventType type)
    {
        switch (type)
        {
            case ExplorationEventType.Battle:
                return "전투";

            case ExplorationEventType.Reward:
                return "보상";

            case ExplorationEventType.Rest:
                return "휴식";

            case ExplorationEventType.Quiz:
                return "퀴즈";

            case ExplorationEventType.Special:
                return "특수 이벤트";

            default:
                return "알 수 없는 이벤트";
        }
    }

    // 로그 출력
    private void AddEventLog(string message)
    {
        Debug.Log("[Exploration] " + message);

        if (eventLogText != null)
        {
            eventLogText.text = message + "\n" + eventLogText.text;
        }
    }

    // 화면 갱신
    private void UpdateUI()
    {
        if (entrancePanel != null)
        {
            entrancePanel.SetActive(
                state == ExplorationState.Entrance
            );
        }

        if (floorPanel != null)
        {
            floorPanel.SetActive(
                state == ExplorationState.Exploring
            );
        }

        if (floorText != null)
        {
            floorText.text = currentFloor + "층";
        }
    }
}
