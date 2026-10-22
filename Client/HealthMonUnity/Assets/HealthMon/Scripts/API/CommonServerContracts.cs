using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Healthmon.Common
{
    [Serializable] public sealed class ServerInfo { public string server_instance_id, environment; }
    [Serializable] public sealed class ServerIdentity { public string owner_id; }
    [Serializable] public sealed class CommonEvolutionRequest { public string request_id; }
    [Serializable] public sealed class CommonEvolutionJob
    {
        public string job_id, request_id, status, model_reference, model_url, model_sha256, error;
        public int stage;
        public long state_version;
    }
    [Serializable] public sealed class WorkoutUploadStatus { public string workout_id, status; public long synced_at; public int last_http_status; }
    [Serializable] public sealed class UnboundWorkout { public string id, exercise; public long start_time, end_time; }
    [Serializable] public sealed class PhoneSyncStatus
    {
        public string status, server_instance_id, owner_id, pet_id, environment;
        public int unbound_count;
        public UnboundWorkout[] unbound;
        public WorkoutUploadStatus[] uploads;
    }

    // No Unity APIs: exercised by the command-line contract test as well as the editor tests.
    public sealed class StateVersionGate
    {
        public int Generation { get; private set; }
        public long Version { get; private set; } = -1;
        public string Scope { get; private set; }
        public void Reset(string server, string owner, string pet)
        {
            Scope = server + "\n" + owner + "\n" + pet;
            Version = -1;
            Generation++;
        }
        public bool Accept(int generation, long version)
        {
            if (generation != Generation || version < 0 || version < Version) return false;
            Version = version;
            return true;
        }
    }

    // A proposal is acknowledged only after the panel observes its actual row.
    // Repaint repetition, retries and stale account/server/pet callbacks cannot
    // manufacture extra display acknowledgements or unlock a new scope's offer.
    public sealed class ProposalDisplayGate
    {
        private enum DisplayState { Observed, Sending, Acknowledged, Failed }
        private readonly Dictionary<string, DisplayState> offers = new Dictionary<string, DisplayState>();
        private bool bound;
        public int Generation { get; private set; }
        public string Scope { get; private set; }
        public void Reset(string server, string owner, string pet)
        {
            Scope = server + "\n" + owner + "\n" + pet;
            bound = !string.IsNullOrWhiteSpace(server) && !string.IsNullOrWhiteSpace(owner) && !string.IsNullOrWhiteSpace(pet);
            offers.Clear(); Generation++;
        }
        public void Observe(string id, bool serverAlreadyAcknowledged = false)
        {
            if (!bound || string.IsNullOrWhiteSpace(id)) return;
            if (serverAlreadyAcknowledged) offers[id] = DisplayState.Acknowledged;
            else if (!offers.ContainsKey(id)) offers.Add(id, DisplayState.Observed);
        }
        public string NextToAcknowledge()
        {
            foreach (var offer in offers) if (offer.Value == DisplayState.Observed) return offer.Key;
            return null;
        }
        public bool TryBegin(string id)
        {
            if (!bound || string.IsNullOrWhiteSpace(id) || !offers.TryGetValue(id, out var state) || state != DisplayState.Observed) return false;
            offers[id] = DisplayState.Sending; return true;
        }
        public bool Complete(int generation, string id, bool success)
        {
            if (generation != Generation || string.IsNullOrWhiteSpace(id) || !offers.TryGetValue(id, out var state) || state != DisplayState.Sending) return false;
            offers[id] = success ? DisplayState.Acknowledged : DisplayState.Failed; return true;
        }
        public bool Acknowledged(string id)
        { return !string.IsNullOrWhiteSpace(id) && offers.TryGetValue(id, out var state) && state == DisplayState.Acknowledged; }
        public bool Failed(string id)
        { return !string.IsNullOrWhiteSpace(id) && offers.TryGetValue(id, out var state) && state == DisplayState.Failed; }
        public void Retry(string id)
        { if (Failed(id)) offers[id] = DisplayState.Observed; }
    }

    // Keep Android configuration writes ordered: an earlier network completion
    // cannot overwrite a more recently verified credential. The caller owns
    // failure reporting and supplies its current connection-generation check.
    public sealed class PhoneSyncConfigurationQueue
    {
        private Task tail = Task.CompletedTask;
        public Task Enqueue(Func<bool> stillCurrent, Func<Task> configure)
        { return tail = RunAfter(tail, stillCurrent, configure); }
        private static async Task RunAfter(Task previous, Func<bool> stillCurrent, Func<Task> configure)
        {
            try { await previous; } catch (Exception) { /* A failed setup must not block the latest setup. */ }
            if (stillCurrent()) await configure();
        }
    }

    public static class CommonServerContract
    {
        public const string RuleVersion = "healthmon.v2.2";
        public static Healthmon.Beta.FoodConfirmationWithoutQuantity FoodConfirmationPayload(string analysisId, int candidate,
            float? grams, float? vegetableFruitGrams, string mealType, bool kcalReconfirmed = false, bool synthetic = false)
        {
            if (string.IsNullOrWhiteSpace(analysisId) || candidate < 0 || candidate > 2 ||
                (grams.HasValue && (!Bounded(grams.Value, 0, 10000) || grams.Value == 0)) ||
                (vegetableFruitGrams.HasValue && !Bounded(vegetableFruitGrams.Value, 0, 10000)) ||
                (mealType != "breakfast" && mealType != "lunch" && mealType != "dinner" && mealType != "snack"))
                throw new ArgumentException("Use the selected analysis and explicitly confirmed food quantities.");
            Healthmon.Beta.FoodConfirmationWithoutQuantity payload;
            if (grams.HasValue)
                payload = vegetableFruitGrams.HasValue
                    ? (Healthmon.Beta.FoodConfirmation)new Healthmon.Beta.FoodConfirmationWithVegetables { grams = grams.Value, vegetable_fruit_g = vegetableFruitGrams.Value }
                    : new Healthmon.Beta.FoodConfirmation { grams = grams.Value };
            else payload = vegetableFruitGrams.HasValue
                    ? new Healthmon.Beta.FoodConfirmationWithoutQuantityWithVegetables { vegetable_fruit_g = vegetableFruitGrams.Value }
                    : new Healthmon.Beta.FoodConfirmationWithoutQuantity();
            payload.analysis_id = analysisId; payload.candidate_id = candidate; payload.meal_type = mealType;
            payload.kcal_reconfirmed = kcalReconfirmed; payload.synthetic = synthetic;
            return payload;
        }
        public static bool ValidFoodAnalysis(Healthmon.Beta.FoodAnalysis analysis)
        {
            if (analysis == null || analysis.schema_version != "healthmon.food.v1" || string.IsNullOrWhiteSpace(analysis.analysis_id) ||
                (analysis.backend != "remote" && analysis.backend != "mock") ||
                (analysis.provenance != "real" && analysis.provenance != "synthetic") ||
                (analysis.backend == "mock" && analysis.provenance != "synthetic") ||
                analysis.synthetic != (analysis.provenance == "synthetic") || analysis.consumption_confirmed ||
                analysis.candidates == null || analysis.candidates.Length < 1 || analysis.candidates.Length > 3) return false;
            var ids = new HashSet<int>();
            foreach (var candidate in analysis.candidates)
            {
                if (candidate == null || candidate.candidate_id < 0 || !ids.Add(candidate.candidate_id) || string.IsNullOrWhiteSpace(candidate.food) ||
                    !Bounded(candidate.confidence, 0, 1) || candidate.per_100g == null ||
                    (candidate.has_estimated_grams && (!Bounded(candidate.estimated_grams, 0, 10000) || candidate.estimated_grams == 0))) return false;
                var nutrients = candidate.per_100g;
                foreach (var nutrient in new[] { nutrients.energy_kcal, nutrients.carbohydrate_g, nutrients.protein_g, nutrients.fat_g, nutrients.vegetable_fruit_g })
                    if (nutrient != null && nutrient.available && (!Bounded(nutrient.value, 0, float.MaxValue))) return false;
            }
            return true;
        }
        public static string NormalizeBearerToken(string token)
        {
            if (token != null && (token.IndexOf('\r') >= 0 || token.IndexOf('\n') >= 0))
                throw new ArgumentException("Bearer token must be one line.");
            string normalized = token == null ? "" : token.Trim();
            foreach (char value in normalized)
                if (char.IsControl(value)) throw new ArgumentException("Bearer token contains an invalid control character.");
            return normalized;
        }
        public static bool IsEmptyPendingPlaceholder(Healthmon.Beta.ChatRequest request, string pet, Healthmon.Beta.PendingChatSnapshot scope)
        {
            return request != null && string.IsNullOrEmpty(request.request_id) && string.IsNullOrEmpty(request.text) &&
                request.state_version == 0 && string.IsNullOrEmpty(pet) && (scope == null ||
                (string.IsNullOrEmpty(scope.base_url) && string.IsNullOrEmpty(scope.server_instance_id) &&
                 string.IsNullOrEmpty(scope.owner_id) && string.IsNullOrEmpty(scope.pet_id) &&
                 (scope.request == null || (string.IsNullOrEmpty(scope.request.request_id) && string.IsNullOrEmpty(scope.request.text) && scope.request.state_version == 0))));
        }
        public static bool MatchesPendingScope(Healthmon.Beta.PendingChatSnapshot scope, string url, string server, string owner, string pet)
        {
            if (scope == null || string.IsNullOrWhiteSpace(scope.server_instance_id) || scope.server_instance_id == "unverified" ||
                string.IsNullOrWhiteSpace(scope.owner_id) || scope.owner_id == "unverified" || string.IsNullOrWhiteSpace(scope.pet_id)) return false;
            try
            {
                return NormalizeBaseUrl(scope.base_url) == NormalizeBaseUrl(url) && scope.server_instance_id == server &&
                    scope.owner_id == owner && scope.pet_id == pet;
            }
            catch (ArgumentException) { return false; }
        }
        // JsonUtility defaults missing/null numbers to zero. Reject missing and null required
        // state fields before decoding; zero must never be invented as a measured value.
        private static readonly string[] RequiredNumbers = {
            "state_version", "level", "current_exp", "required_exp", "total_exp", "coin",
            "upper_body", "lower_body", "nutrition", "energy_balance", "activity", "affinity",
            "initiative", "evolution_target_stage", "published_model_stage"
        };
        public static string NormalizeBaseUrl(string url)
        {
            Uri address;
            if (!Uri.TryCreate(url, UriKind.Absolute, out address) ||
                (address.Scheme != "http" && address.Scheme != "https") ||
                !string.IsNullOrEmpty(address.UserInfo) || !string.IsNullOrEmpty(address.Query) ||
                !string.IsNullOrEmpty(address.Fragment))
                throw new ArgumentException("Use an HTTP(S) base URL without credentials, query or fragment.");
            return address.AbsoluteUri.TrimEnd('/');
        }
        public static bool HasRequiredStateFields(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return false;
            foreach (var key in RequiredNumbers)
                if (!Regex.IsMatch(json, "\"" + key + "\"\\s*:\\s*-?[0-9]+(?:\\.[0-9]+)?(?=\\s*[,}])")) return false;
            foreach (var key in new[] { "pet_id", "rule_version", "asset_status" })
                if (!Regex.IsMatch(json, "\"" + key + "\"\\s*:\\s*\"[^\"]+\"")) return false;
            return true;
        }
        public static string ResolveApiUrl(string baseUrl, string reference)
        {
            var origin = new Uri(NormalizeBaseUrl(baseUrl) + "/");
            if (string.IsNullOrWhiteSpace(reference) || reference.Length > 2048 ||
                reference.StartsWith("//", StringComparison.Ordinal) || reference.IndexOf('?') >= 0 ||
                reference.IndexOf('#') >= 0 || reference.IndexOf("%25", StringComparison.OrdinalIgnoreCase) >= 0)
                throw new ArgumentException("Invalid common API reference.");
            string decoded = Uri.UnescapeDataString(reference);
            foreach (char value in decoded)
                if (char.IsControl(value) || value == '\\') throw new ArgumentException("Invalid common API reference.");
            foreach (string segment in decoded.Split('/'))
                if (segment == "." || segment == "..") throw new ArgumentException("API path traversal is forbidden.");
            Uri address;
            if (!reference.StartsWith("/", StringComparison.Ordinal) && Uri.TryCreate(reference, UriKind.Absolute, out address)) { }
            else address = new Uri(origin, reference.TrimStart('/'));
            if (address.Scheme != origin.Scheme || address.Host != origin.Host || address.Port != origin.Port ||
                !string.IsNullOrEmpty(address.UserInfo) || !string.IsNullOrEmpty(address.Query) ||
                !string.IsNullOrEmpty(address.Fragment) || !address.AbsolutePath.StartsWith(origin.AbsolutePath, StringComparison.Ordinal))
                throw new ArgumentException("API reference must remain within the configured server and API prefix.");
            return address.AbsoluteUri;
        }
        public static bool Bounded(float value, float min, float max)
        { return !float.IsNaN(value) && !float.IsInfinity(value) && value >= min && value <= max; }
    }
}
