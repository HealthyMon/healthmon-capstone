using System;
using System.Globalization;
using Healthmon.Beta;
using TMPro;
using UnityEngine;

public class WorkoutRecordItemUI : MonoBehaviour
{
    [SerializeField] private TMP_Text dateText;
    [SerializeField] private TMP_Text exerciseText;
    [SerializeField] private TMP_Text durationText;
    [SerializeField] private TMP_Text averageHeartRateText;
    [SerializeField] private TMP_Text maxHeartRateText;
    [SerializeField] private TMP_Text caloriesText;
    [SerializeField] private TMP_Text stepsText;
    [SerializeField] private TMP_Text distanceText;

    // Used by the server-backed wearable history page.
    public void SetServerData(ServerWorkoutEntry entry, int index)
    {
        var data = entry.record;
        string timestamp = !string.IsNullOrEmpty(data.started_at)
            ? data.started_at : entry.occurred_at;
        string displayedDate = timestamp;
        if (DateTimeOffset.TryParse(timestamp, CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal, out var date))
            displayedDate = date.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");
        dateText.text = $"{index}. {displayedDate}";
        exerciseText.text = $"운동 종목: {GetExerciseName(data.exercise_type)}";

        // Legacy server events predate detail-metric storage. JsonUtility reads
        // missing/null numeric fields as zero. Do not label all-empty legacy records
        // as actual zero-value measurements.
        bool hasDetails = data.duration_seconds > 0 || data.average_heart_rate_bpm > 0 ||
            data.max_heart_rate_bpm > 0 || data.calories_kcal > 0 ||
            data.steps > 0 || data.distance_km > 0;
        durationText.text = hasDetails
            ? $"운동 시간: {FormatDuration(data.duration_seconds)}" : "운동 시간: 측정 정보 없음";
        averageHeartRateText.text = hasDetails && data.average_heart_rate_bpm > 0
            ? $"평균 심박수: {data.average_heart_rate_bpm:F1} bpm" : "평균 심박수: 측정 정보 없음";
        maxHeartRateText.text = hasDetails && data.max_heart_rate_bpm > 0
            ? $"최대 심박수: {data.max_heart_rate_bpm:F0} bpm" : "최대 심박수: 측정 정보 없음";
        caloriesText.text = hasDetails
            ? $"소모 칼로리: {data.calories_kcal:F2} kcal" : "소모 칼로리: 측정 정보 없음";
        stepsText.text = hasDetails ? $"걸음 수: {data.steps}" : "걸음 수: 측정 정보 없음";
        distanceText.text = hasDetails
            ? $"거리: {data.distance_km:F2} km" : "거리: 측정 정보 없음";
    }

    // Retained so other existing users of the Room-backed item won't break.
    public void SetData(WorkoutRecordData data, int index)
    {
        DateTimeOffset startDate = DateTimeOffset.FromUnixTimeMilliseconds(data.startTime).ToLocalTime();
        dateText.text = $"{index}. {startDate:yyyy-MM-dd HH:mm:ss}";
        exerciseText.text = $"운동 종목: {GetExerciseName(data.exercise)}";
        durationText.text = $"운동 시간: {FormatDuration(data.durationSeconds)}";
        averageHeartRateText.text = $"평균 심박수: {data.averageHeartRate:F1} bpm";
        maxHeartRateText.text = $"최대 심박수: {data.maxHeartRate:F0} bpm";
        caloriesText.text = $"소모 칼로리: {data.calories:F2} kcal";
        stepsText.text = $"걸음 수: {data.steps}";
        distanceText.text = $"거리: {data.distanceKm:F2} km";
    }

    private static string FormatDuration(int seconds)
    {
        int hour = seconds / 3600;
        int minute = (seconds % 3600) / 60;
        int second = seconds % 60;
        return hour > 0 ? $"{hour:00}:{minute:00}:{second:00}" : $"{minute:00}:{second:00}";
    }

    private static string GetExerciseName(string exercise)
    {
        switch ((exercise ?? "").ToLowerInvariant())
        {
            case "walking": case "walk": return "걷기";
            case "running": case "run": return "달리기";
            case "cycling": case "cycle": return "자전거";
            case "squat": return "스쿼트";
            case "gymnastics": return "체조";
            case "stretching": return "스트레칭";
            case "pushup": return "푸시업";
            case "lunge": return "런지";
            default: return string.IsNullOrEmpty(exercise) ? "알 수 없음" : exercise;
        }
    }
}
