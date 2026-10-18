using System;

namespace Healthmon.Beta
{
    // Public fields and object wrappers keep this contract compatible with JsonUtility.
    [Serializable] public class PetSettings
    {
        public string name = "몽글이";
        public string profanity = "mild";
        public string speech_level = "casual";
        public string timezone = "Asia/Seoul";
    }
    [Serializable] public class CreatedPet { public string pet_id; public long state_version; }
    [Serializable] public class PetSummary { public string pet_id; public string name; public long state_version; }
    [Serializable] public class PetList { public PetSummary[] pets; }
    [Serializable] public class Traits
    {
        public float sociability, initiative, playfulness, courtesy, bluntness, roughness, bond;
    }
    [Serializable] public class Mood { public float valence, energy; }
    [Serializable] public class PetSnapshot
    {
        public Traits traits;
        public Mood mood;
        public string as_of, rules_version;
    }
    [Serializable] public class PetState
    {
        public long state_version;
        public PetSettings settings;
        public Traits traits;
        public Mood mood;
        public string as_of, rules_version;
    }
    [Serializable] public class ChatRequest
    {
        public string request_id;
        public string text;
        public long state_version;
    }
    [Serializable] public class PendingChatSnapshot { public string pet_id; public ChatRequest request; }
    [Serializable] public class ModelAction { public string type, target_id; }
    [Serializable] public class CharacterResponse
    {
        public string speech, emotion, animation;
        public ModelAction action;
        public string[] memory_ids;
        // personality_update is deliberately ignored: only server state is authoritative.
    }
    [Serializable] public class ServerExecution { public string offer_id, deleted_memory_id; }
    [Serializable] public class ResponseMetrics
    {
        public int attempts;
        public bool repaired, fallback;
        public float latency_seconds;
        public string handler;
        // raw_valid may be JSON null; it is not represented as a misleading bool.
    }
    [Serializable] public class ChatResult
    {
        public string schema_version, request_id, source_id;
        public CharacterResponse response;
        public long state_version;
        public PetSnapshot state_used, state_after;
        public ServerExecution execution;
        public ResponseMetrics metrics;
    }
    [Serializable] public class HistoryMessage
    {
        public string request_id, source_id, created_at, user, assistant;
        public int source_revision;
        public CharacterResponse response;
        public ServerExecution execution;
        public ResponseMetrics metrics;
    }
    [Serializable] public class MessageHistory
    {
        public string pet_id;
        public long state_version;
        public int limit;
        public bool has_more;
        public HistoryMessage[] messages;
    }
    [Serializable] public class QuestTemplate
    {
        public string id, kind, unit;
        public float target;
        public int reward;
    }
    [Serializable] public class QuestOffer
    {
        public string id, pet_id, status, created_at, expires_at, accepted_at;
        public long state_version;
        public QuestTemplate template;
        public float progress;
    }
    [Serializable] public class PendingActivitySuggestion { public string source_id; public int revision; }
    [Serializable] public class QuestList
    {
        public QuestOffer[] offers;
        public QuestTemplate[] candidates;
        public PendingActivitySuggestion[] pending_activity_suggestions;
        public int reward_balance;
    }
    [Serializable] public class QuestDecision { public string decision; }
    [Serializable] public class QuestDecisionResult
    {
        public string status;
        public bool duplicate;
        // Duplicate responses omit state_version. Always GET state after a decision.
    }
    public sealed class ApiFailure
    {
        public long StatusCode { get; private set; }
        public string Message { get; private set; }
        public bool Cancelled { get; private set; }
        public ApiFailure(long statusCode, string message, bool cancelled = false)
        { StatusCode = statusCode; Message = message; Cancelled = cancelled; }
    }
}
