using TMPro;
using UnityEngine;

public class LiveWorkoutPageUI : MonoBehaviour
{
    [Header("Workout")]
    [SerializeField]
    private TMP_Text exerciseText;

    [SerializeField]
    private TMP_Text durationText;


    [Header("Heart Rate")]
    [SerializeField]
    private TMP_Text heartRateText;

    [SerializeField]
    private TMP_Text averageHeartRateText;

    [SerializeField]
    private TMP_Text maxHeartRateText;


    [Header("Activity")]
    [SerializeField]
    private TMP_Text caloriesText;

    [SerializeField]
    private TMP_Text stepsText;

    [SerializeField]
    private TMP_Text distanceText;


    public void UpdateUI(LiveWorkoutData data)
    {
        exerciseText.text =
            $"운동 종목: {GetExerciseName(data.exercise)}";

        durationText.text =
            $"운동 시간: {FormatDuration(data.durationSeconds)}";

        heartRateText.text =
            data.heartRate > 0
                ? $"현재 심박수: {data.heartRate:F0} bpm"
                : "현재 심박수: --- bpm";

        averageHeartRateText.text =
            data.averageHeartRate > 0
                ? $"평균 심박수: {data.averageHeartRate:F1} bpm"
                : "평균 심박수: --- bpm";

        maxHeartRateText.text =
            data.maxHeartRate > 0
                ? $"최대 심박수: {data.maxHeartRate:F0} bpm"
                : "최대 심박수: --- bpm";

        caloriesText.text =
            $"소모 칼로리: {data.calories:F2} kcal";

        stepsText.text =
            $"걸음 수: {data.steps}";

        distanceText.text =
            $"거리: {data.distanceKm:F2} km";
    }


    private string FormatDuration(int seconds)
    {
        int hour = seconds / 3600;
        int minute = (seconds % 3600) / 60;
        int second = seconds % 60;

        if (hour > 0)
        {
            return $"{hour:00}:{minute:00}:{second:00}";
        }

        return $"{minute:00}:{second:00}";
    }


    private string GetExerciseName(string exercise)
    {
        return exercise switch
        {
            "WALKING" => "걷기",
            "RUNNING" => "달리기",
            "CYCLING" => "자전거",
            "SQUAT" => "스쿼트",
            "STRETCHING" => "스트레칭",

            _ => exercise
        };
    }
}