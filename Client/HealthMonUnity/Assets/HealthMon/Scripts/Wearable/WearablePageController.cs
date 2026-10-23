using System.Collections;
using UnityEngine;

public class WearablePageController : MonoBehaviour
{
    [Header("Pages")]
    [SerializeField]
    private GameObject workoutHistoryPage;

    [SerializeField]
    private GameObject liveWorkoutPage;


    [Header("Controllers")]
    [SerializeField]
    private WorkoutHistoryController workoutHistoryController;

    [SerializeField]
    private LiveWorkoutPageUI liveWorkoutPageUI;


    [Header("Settings")]
    [SerializeField]
    private float pollingInterval = 1.0f;


    private long lastSequence = -1;

    private bool isWorkoutPageOpen = false;


    private void Start()
    {
        HealthMonAndroidBridge.Initialize();

        ShowHistoryPage();

        bool requested =
            HealthMonAndroidBridge.RequestLiveWorkoutState();

        Debug.Log(
            $"HealthMon live request = {requested}"
        );

        StartCoroutine(
            PollLiveWorkoutState()
        );
    }


    private IEnumerator PollLiveWorkoutState()
    {
        while (true)
        {
            CheckLiveWorkoutState();

            yield return new WaitForSecondsRealtime(
                pollingInterval
            );
        }
    }


    private void CheckLiveWorkoutState()
    {
        string json =
            HealthMonAndroidBridge
                .GetLatestLiveWorkoutState();

        if (string.IsNullOrEmpty(json))
        {
            return;
        }


        LiveWorkoutData data;

        try
        {
            data =
                JsonUtility.FromJson<LiveWorkoutData>(
                    json
                );
        }
        catch (System.Exception e)
        {
            Debug.LogError(
                $"Live workout JSON parse failed: {e}"
            );

            return;
        }


        if (data == null)
        {
            return;
        }


        // 같은 데이터라면 UI를 다시 갱신하지 않음
        if (data.sequence == lastSequence)
        {
            return;
        }

        lastSequence = data.sequence;


        Debug.Log(
            $"HealthMon Live: " +
            $"status={data.status}, " +
            $"duration={data.durationSeconds}, " +
            $"HR={data.heartRate}, " +
            $"sequence={data.sequence}"
        );


        switch (data.status)
        {
            case "STARTED":
            case "ACTIVE":

                ShowLiveWorkoutPage();

                liveWorkoutPageUI.UpdateUI(data);

                break;


            case "ENDED":

                StartCoroutine(
                    HandleWorkoutEnded()
                );

                break;
        }
    }


    private void ShowLiveWorkoutPage()
    {
        if (isWorkoutPageOpen)
        {
            return;
        }

        isWorkoutPageOpen = true;

        workoutHistoryPage.SetActive(false);
        liveWorkoutPage.SetActive(true);

        Debug.Log(
            "HealthMon → LiveWorkoutPage"
        );
    }


    private void ShowHistoryPage()
    {
        isWorkoutPageOpen = false;

        workoutHistoryPage.SetActive(true);
        liveWorkoutPage.SetActive(false);
    }


    private IEnumerator HandleWorkoutEnded()
    {
        ShowHistoryPage();

        // Phone Room 저장이 끝날 시간을 조금 기다림
        yield return new WaitForSecondsRealtime(0.5f);

        workoutHistoryController
            .RefreshWorkoutList();

        Debug.Log(
            "HealthMon → WorkoutHistoryPage"
        );
    }
}