using System;

[Serializable]
public class WorkoutRecordData
{
    public string id;
    public string exercise;

    public long startTime;
    public long endTime;

    public int durationSeconds;

    public double averageHeartRate;
    public double maxHeartRate;

    public double calories;
    public long steps;
    public double distanceKm;

    public string[] supportedMetrics;

    public string source;
    public long receivedAt;
}

[Serializable]
public class WorkoutRecordDataList
{
    public WorkoutRecordData[] items;
}