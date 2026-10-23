using System;

[Serializable]
public class LiveWorkoutData
{
    public string sessionId;
    public string exercise;
    public string status;

    public int durationSeconds;

    public double heartRate;
    public double averageHeartRate;
    public double maxHeartRate;

    public double calories;
    public long steps;
    public double distanceKm;

    public long timestamp;
    public long sequence;
}