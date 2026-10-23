using System;

namespace Healthmon.Beta
{
    [Serializable] public class ConversationIntent { public string session_id; public bool active; }
    [Serializable] public class ConversationStatus { public bool active, ready; public string policy; public int heartbeat_timeout_seconds; }
    [Serializable] public class NutrientValue { public bool available; public float value; }
    [Serializable] public class FoodNutrients
    {
        public NutrientValue energy_kcal, carbohydrate_g, protein_g, fat_g, vegetable_fruit_g, sugar_g, fiber_g, sodium_mg;
    }
    [Serializable] public class FoodCandidate
    {
        public int candidate_id;
        public string food, weight_warning;
        public float confidence, estimated_grams;
        public bool has_estimated_grams;
        public FoodNutrients per_100g;
    }
    [Serializable] public class FoodAnalysis
    {
        public string schema_version, analysis_id, backend, provenance;
        public bool consumption_confirmed, synthetic;
        public FoodCandidate[] candidates;
        public bool IsSynthetic { get { return synthetic || provenance == "synthetic" || backend == "mock"; } }
    }
    [Serializable] public class FoodConfirmationWithoutQuantity
    {
        public string analysis_id;
        public int candidate_id;
        public string meal_type = "snack";
        public bool kcal_reconfirmed, synthetic;
    }
    // JsonUtility cannot express nullable numbers. Omitting grams means quantity is unknown.
    [Serializable] public class FoodConfirmation : FoodConfirmationWithoutQuantity { public float grams; }
    [Serializable] public class FoodConfirmationWithVegetables : FoodConfirmation { public float vegetable_fruit_g; }
    [Serializable] public class FoodConfirmationWithoutQuantityWithVegetables : FoodConfirmationWithoutQuantity { public float vegetable_fruit_g; }
    [Serializable] public class FoodRecord { public string food, analysis_id, quantity_source; public FoodNutrients nutrition; }
    [Serializable] public class FoodConfirmationResult
    {
        public string analysis_id, source_id;
        public bool duplicate, stored;
        public int revision;
        public long state_version;
        public PetState state;
        public string evaluation_status;
        public FoodRecord record;
    }
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
        public string pet_id, rule_version, asset_status, model_reference, evaluation_status;
        public int level, current_exp, required_exp, total_exp, coin;
        public float upper_body, lower_body, nutrition, energy_balance, activity, affinity, initiative;
        public int evolution_target_stage, published_model_stage;
        public long state_version;
        public PetSettings settings;
        public Traits traits;
        public Mood mood;
        public string as_of, rules_version;

        public bool IsValidCommonState(string expectedPet)
        {
            if (pet_id != expectedPet || rule_version != Healthmon.Common.CommonServerContract.RuleVersion ||
                state_version < 0 || level < 1 || current_exp < 0 || required_exp <= 0 ||
                current_exp >= required_exp || total_exp < current_exp || coin < 0 ||
                evolution_target_stage < 0 || evolution_target_stage > 3 ||
                published_model_stage < 0 || published_model_stage > evolution_target_stage ||
                string.IsNullOrWhiteSpace(asset_status)) return false;
            foreach (var value in new[] { upper_body, lower_body, nutrition, activity, affinity, initiative })
                if (!Healthmon.Common.CommonServerContract.Bounded(value, 0, 100)) return false;
            return Healthmon.Common.CommonServerContract.Bounded(energy_balance, -100, 100);
        }
    }
    [Serializable] public class ChatRequest
    {
        public string request_id;
        public string text;
        public long state_version;
    }
    [Serializable] public class PendingChatSnapshot
    { public string pet_id, server_instance_id, owner_id, base_url; public ChatRequest request; }
    [Serializable] public class PendingChatDiagnostics
    {
        public bool has_pending_object, has_request_id, has_text, has_pending_pet, has_frozen_scope, credential_available;
        public int empty_placeholder_normalizations;
    }
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
        public bool synthetic;
        public string backend;
        // raw_valid may be JSON null; it is not represented as a misleading bool.
    }
    [Serializable] public class ChatResult
    {
        public string schema_version, request_id, source_id, provenance;
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
        public string id, kind, unit, candidate;
        public float target;
        public int reward;
        public int exp, coin;
    }
    [Serializable] public class QuestOffer
    {
        public string id, pet_id, status, created_at, expires_at, accepted_at, rejected_at, shown_at, cancelled_at, slot, period_start;
        public bool is_proposal, excluded;
        public long state_version;
        public QuestTemplate template;
        public float progress;
        public bool IsPendingProposal
        {
            get { return !string.IsNullOrWhiteSpace(id) && is_proposal && !excluded && string.IsNullOrEmpty(cancelled_at) &&
                string.IsNullOrEmpty(accepted_at) && string.IsNullOrEmpty(rejected_at) &&
                (status == "offered" || status == "active"); }
        }
    }
    [Serializable] public class PendingActivitySuggestion { public string source_id; public int revision; }
    [Serializable] public class QuestList
    {
        public string current_day, current_week_start;
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
