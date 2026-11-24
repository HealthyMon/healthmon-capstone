
using System;
using System.Collections;
using UnityEngine;

public class WearablePageController : MonoBehaviour
{
    [Header("Pages")]
    [SerializeField] private GameObject workoutHistoryPage;
    [SerializeField] private GameObject liveWorkoutPage;

    [Header("Controllers")]
    [SerializeField] private WorkoutHistoryController workoutHistoryController;
    [SerializeField] private LiveWorkoutPageUI liveWorkoutPageUI;

    [Header("Settings")]
    [SerializeField, Min(0.1f)]
    private float pollingInterval = 1.0f;

    [Tooltip("No new active workout data for this many seconds returns to history. Set to 0 to disable.")]
    [SerializeField, Min(0f)]
    private float liveDataTimeout = 15.0f;

    private string lastSessionId;
    private long lastSequence = -1;
    private float lastLiveUpdateTime;
    private bool isLiveWorkoutVisible;
    private Coroutine endRoutine;

    private void Awake()
    {
        // 처음에는 운동 기록 화면만 표시
        ShowHistoryPage();
    }

    private void Start()
    {
        HealthMonAndroidBridge.Initialize();

        workoutHistoryController?.RefreshWorkoutList();

        // 워치에 현재 운동 상태 요청
        bool requested =
            HealthMonAndroidBridge.RequestLiveWorkoutState();

        Debug.Log($"HealthMon live request = {requested}");

        StartCoroutine(PollLiveWorkoutState());
    }

    private IEnumerator PollLiveWorkoutState()
    {
        while (true)
        {
            CheckLiveWorkoutState();

            // 일정 시간 새 데이터가 없으면 기록 화면으로 복귀
            if (isLiveWorkoutVisible &&
                liveDataTimeout > 0f &&
                Time.realtimeSinceStartup - lastLiveUpdateTime
                    > liveDataTimeout)
            {
                ShowHistoryPage();
            }

            yield return new WaitForSecondsRealtime(
                Mathf.Max(0.1f, pollingInterval)
            );
        }
    }

    private void CheckLiveWorkoutState()
    {
        string json =
            HealthMonAndroidBridge.GetLatestLiveWorkoutState();

        if (string.IsNullOrEmpty(json))
            return;

        LiveWorkoutData data;

        try
        {
            data = JsonUtility.FromJson<LiveWorkoutData>(json);
        }
        catch (Exception e)
        {
            Debug.LogError(
                $"Live workout JSON parse failed: {e.Message}"
            );
            return;
        }

        if (data == null)
            return;

        string sessionId = data.sessionId ?? string.Empty;

        // 동일한 운동 세션의 동일 데이터 중복 처리 방지
        if (sessionId == lastSessionId &&
            data.sequence == lastSequence)
        {
            return;
        }

        lastSessionId = sessionId;
        lastSequence = data.sequence;

        switch ((data.status ?? string.Empty).ToUpperInvariant())
        {
            case "STARTED":
            case "ACTIVE":

                if (endRoutine != null)
                {
                    StopCoroutine(endRoutine);
                    endRoutine = null;
                }

                lastLiveUpdateTime = Time.realtimeSinceStartup;

                ShowLiveWorkoutPage();

                liveWorkoutPageUI?.UpdateUI(data);
                break;

            case "ENDED":

                ShowHistoryPage();

                if (endRoutine != null)
                    StopCoroutine(endRoutine);

                endRoutine =
                    StartCoroutine(HandleWorkoutEnded());
                break;
        }
    }

    private void ShowLiveWorkoutPage()
    {
        if (workoutHistoryPage != null)
            workoutHistoryPage.SetActive(false);

        if (liveWorkoutPage != null)
            liveWorkoutPage.SetActive(true);

        isLiveWorkoutVisible = true;
    }

    private void ShowHistoryPage()
    {
        if (liveWorkoutPage != null)
            liveWorkoutPage.SetActive(false);

        if (workoutHistoryPage != null)
            workoutHistoryPage.SetActive(true);

        isLiveWorkoutVisible = false;
    }

    private IEnumerator HandleWorkoutEnded()
    {
        // 모바일 Room 저장 완료 대기
        yield return new WaitForSecondsRealtime(0.5f);

        workoutHistoryController?.RefreshWorkoutList();

        Healthmon.Common.CommonServerConnection.Instance
            ?.RefreshPhoneStatus();

        Healthmon.Common.CommonServerConnection.Instance
            ?.RefreshState();

        endRoutine = null;
    }
}
