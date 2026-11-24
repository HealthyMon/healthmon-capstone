using System;
using System.Collections.Generic;
using System.IO;
using Healthmon.Beta;
using Healthmon.Common;
using UnityEngine;

namespace Healthmon.Common
{
    [Serializable] public sealed class PoseWorkoutSubmission
    {
        public string event_id, occurred_at, started_at, workout_type;
        public int revision = 1, actual, duration_seconds;
        public string unit = "repetitions", source = "sensor";
        public bool synthetic;
    }
    [Serializable] public sealed class WorkoutSubmissionResult
    {
        public string event_id, evaluation_status;
        public bool duplicate;
        public PetState state;
    }
}

// Persist a session's exact payload and account binding before sending it. A lost
// response can then be retried without awarding a second workout or another pet.
public sealed class HealthMonPoseWorkoutSync : MonoBehaviour
{
    [Serializable] public sealed class Entry
    {
        public string server, owner, pet;
        public PoseWorkoutSubmission request;
    }
    [Serializable] sealed class Queue { public List<Entry> entries = new List<Entry>(); }
    public static HealthMonPoseWorkoutSync Instance { get; private set; }
    public event Action<string, WorkoutSubmissionResult> Recorded;
    public event Action<string> Deferred;
    Queue queue;
    bool sending;
    float nextAttempt;
    public int PendingCount => queue?.entries.Count ?? 0;
    string QueuePath
    {
        get
        {
#if UNITY_EDITOR
            var testPath = Environment.GetEnvironmentVariable("HEALTHMON_POSE_QUEUE_TEST_PATH");
            if (!string.IsNullOrEmpty(testPath) && Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP") == "1") return testPath;
#endif
            return Path.Combine(Application.persistentDataPath, "pose-pending-workouts.json");
        }
    }
    void Awake()
    {
        Instance = this;
        try { queue = File.Exists(QueuePath) ? JsonUtility.FromJson<Queue>(File.ReadAllText(QueuePath)) : new Queue(); }
        catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is ArgumentException)
        { Debug.LogWarning("Pose workout queue could not be read; existing file preserved."); }
        if (queue != null && queue.entries == null) queue.entries = new List<Entry>();
    }
    public static Entry BindCurrentAccount(string startedAt)
    {
        var c = CommonServerConnection.Instance;
        if (!CommonServerConnection.UsesServerAuthority || c == null || !c.IsConnected || string.IsNullOrEmpty(c.Api.PetId)) return null;
        return new Entry { server = c.ServerInstanceId, owner = c.OwnerId, pet = c.Api.PetId,
            request = new PoseWorkoutSubmission { started_at = startedAt } };
    }
    public static bool Matches(Entry entry, CommonServerConnection c) => entry != null && c != null && c.IsConnected &&
        entry.server == c.ServerInstanceId && entry.owner == c.OwnerId && entry.pet == c.Api.PetId;

    public bool Enqueue(Entry entry)
    {
        if (queue == null || entry?.request == null || string.IsNullOrEmpty(entry.request.event_id) ||
            string.IsNullOrEmpty(entry.server) || string.IsNullOrEmpty(entry.owner) || string.IsNullOrEmpty(entry.pet)) return false;
        if (queue.entries.Exists(e => e.server == entry.server && e.owner == entry.owner && e.pet == entry.pet && e.request.event_id == entry.request.event_id)) return true;
        queue.entries.Add(entry);
        if (!Save()) { queue.entries.Remove(entry); return false; }
        nextAttempt = 0;
        return true;
    }
    bool Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(QueuePath));
            File.WriteAllText(QueuePath + ".tmp", JsonUtility.ToJson(queue, true));
            if (File.Exists(QueuePath)) File.Replace(QueuePath + ".tmp", QueuePath, null);
            else File.Move(QueuePath + ".tmp", QueuePath);
            return true;
        }
        catch (Exception e) when (e is IOException || e is UnauthorizedAccessException || e is ArgumentException) { return false; }
    }
    void Update()
    {
        var c = CommonServerConnection.Instance;
        if (sending || queue == null || Time.unscaledTime < nextAttempt || !CommonServerConnection.UsesServerAuthority || c == null || !c.IsConnected || c.Api.IsBusy || c.Api.HasPendingChat) return;
        var entry = queue.entries.Find(e => Matches(e, c));
        if (entry == null) return;
        sending = true; nextAttempt = Time.unscaledTime + 10;
        c.Api.SubmitPoseWorkout(entry.request, result => {
            sending = false;
            queue.entries.Remove(entry);
            if (!Save()) queue.entries.Add(entry); // Persisted retry remains safe after a crash.
            Recorded?.Invoke(entry.request.event_id, result);
        }, error => { sending = false; Deferred?.Invoke(entry.request.event_id); });
    }
    void OnDestroy() { if (Instance == this) Instance = null; }
}
