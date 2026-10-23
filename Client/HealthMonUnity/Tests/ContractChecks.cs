using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Healthmon.Beta;
using Healthmon.Common;

// Pure C# checks execute without a Unity license. Real editor-only component/JsonUtility
// checks are additionally available through CommonServerVerification.Run.
public static class ContractChecks
{
    private static int checks;
    private static void Check(bool valid, string name)
    { checks++; if (!valid) throw new Exception(name); }
    public static int Main()
    {
        var gate = new StateVersionGate();
        gate.Reset("server-A", "alice", "pet-A"); int alice = gate.Generation;
        Check(gate.Accept(alice, 5), "initial state");
        Check(!gate.Accept(alice, 4), "out-of-order state ignored");
        Check(gate.Accept(alice, 5), "same version allowed");
        Check(gate.Accept(alice, 6), "forward state allowed");
        Check(!gate.Accept(alice, -1), "negative version rejected");
        gate.Reset("server-A", "bob", "pet-A"); int bob = gate.Generation;
        Check(!gate.Accept(alice, 100), "late alice response ignored after login switch");
        Check(gate.Accept(bob, 0), "bob initial state independent of alice version");
        gate.Reset("server-B", "bob", "pet-A");
        Check(!gate.Accept(bob, 1000), "late previous server response ignored");
        int serverB = gate.Generation; gate.Reset("server-B", "bob", "pet-B");
        Check(!gate.Accept(serverB, 5000), "late previous pet response ignored");
        Check(gate.Accept(gate.Generation, 1), "new pet state accepted");
        Check(CommonServerContract.NormalizeBaseUrl("http://127.0.0.1:1234/") == "http://127.0.0.1:1234", "base normalization");
        Check(CommonServerContract.NormalizeBearerToken("  fixture-token  ") == "fixture-token", "copied token uses the same normalized credential for every transport");
        Check(CommonServerContract.NormalizeBearerToken("\t fixture-token \t") == "fixture-token", "outer copied whitespace is removed");
        Check(CommonServerContract.NormalizeBearerToken(null) == "" && CommonServerContract.NormalizeBearerToken("  ") == "", "missing token remains empty");
        foreach (var value in new[] { "fixture-token\r", "fixture-token\n", "fixture\ttoken", "fixture\0token" })
        {
            bool rejected = false;
            try { CommonServerContract.NormalizeBearerToken(value); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "invalid header control characters are rejected without exposing the credential");
        }
        var phoneQueue = new PhoneSyncConfigurationQueue();
        var releaseOldSetup = new TaskCompletionSource<bool>();
        var writes = new List<string>();
        int setupGeneration = 1;
        Task firstSetup = phoneQueue.Enqueue(() => true, async () => { writes.Add("old-start"); await releaseOldSetup.Task; writes.Add("old-end"); });
        Task staleSetup = phoneQueue.Enqueue(() => setupGeneration == 1, () => { writes.Add("stale-write"); return Task.CompletedTask; });
        setupGeneration = 2;
        Task latestSetup = phoneQueue.Enqueue(() => setupGeneration == 2, () => { writes.Add("latest-write"); return Task.CompletedTask; });
        Check(writes.Count == 1 && !latestSetup.IsCompleted, "a newer phone setup waits for the previous native write");
        releaseOldSetup.SetResult(true);
        latestSetup.GetAwaiter().GetResult();
        Check(firstSetup.IsCompleted && staleSetup.IsCompleted && string.Join(",", writes) == "old-start,old-end,latest-write",
            "obsolete queued setup is skipped and latest credential is written last");
        Task failedSetup = phoneQueue.Enqueue(() => true, () => Task.FromException(new InvalidOperationException("fixture setup failure")));
        bool failureObserved = false;
        try { failedSetup.GetAwaiter().GetResult(); } catch (InvalidOperationException) { failureObserved = true; }
        phoneQueue.Enqueue(() => true, () => { writes.Add("recovered-write"); return Task.CompletedTask; }).GetAwaiter().GetResult();
        Check(failureObserved && writes[writes.Count - 1] == "recovered-write", "failed phone setup remains observable and does not block recovery");
        foreach (var value in new[] { "file:///tmp/file", "https://token@host", "https://host/?token=x", "https://host/#x", "not a URL" })
        {
            bool rejected = false;
            try { CommonServerContract.NormalizeBaseUrl(value); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "reject unsafe base URL " + value);
        }
        Check(CommonServerContract.ResolveApiUrl("https://team.example/healthmon", "/pets/p/assets/job") ==
            "https://team.example/healthmon/pets/p/assets/job", "leading slash means API root below configured proxy prefix");
        Check(CommonServerContract.ResolveApiUrl("https://team.example/healthmon/", "pets/p/evolutions/job") ==
            "https://team.example/healthmon/pets/p/evolutions/job", "relative route retains configured API prefix");
        Check(CommonServerContract.ResolveApiUrl("https://team.example", "/pets/p/state") ==
            "https://team.example/pets/p/state", "plain origin retains existing endpoint behavior");
        Check(CommonServerContract.ResolveApiUrl("https://team.example/healthmon", "https://team.example/healthmon/pets/p/assets/job") ==
            "https://team.example/healthmon/pets/p/assets/job", "same origin absolute reference within API prefix");
        foreach (var value in new[] { "https://foreign.example/healthmon/pets/p/assets/j", "http://team.example/healthmon/pets/p/assets/j",
            "https://team.example:9443/healthmon/pets/p/assets/j", "https://team.example/other/pets/p/assets/j", "//foreign.example/path",
            "../admin", "/pets/../admin", "/pets/%2e%2e/admin", "/pets/%252e%252e/admin", "/pets/..%2fadmin",
            "/pets/..\\admin", "/pets/%5cadmin", "/pets/p/assets/j?token=x", "/pets/p/assets/j#fragment" })
        {
            bool rejected = false;
            try { CommonServerContract.ResolveApiUrl("https://team.example/healthmon", value); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "reject escaping API reference " + value);
        }
        const string json = "{\"pet_id\":\"p\",\"rule_version\":\"healthmon.v2.2\",\"asset_status\":\"none\",\"state_version\":0,\"level\":1,\"current_exp\":0,\"required_exp\":100,\"total_exp\":0,\"coin\":0,\"upper_body\":50,\"lower_body\":50,\"nutrition\":50,\"energy_balance\":0,\"activity\":50,\"affinity\":50,\"initiative\":50,\"evolution_target_stage\":0,\"published_model_stage\":0}";
        Check(CommonServerContract.HasRequiredStateFields(json), "zero is a valid measured state");
        foreach (var key in new[] { "upper_body", "lower_body", "nutrition", "activity", "affinity", "initiative" })
            Check(!CommonServerContract.HasRequiredStateFields(json.Replace("\"" + key + "\":50", "\"" + key + "\":null")), "unknown " + key + " cannot become a fabricated zero");
        Check(!CommonServerContract.HasRequiredStateFields(json.Replace("\"coin\":0,", "")), "missing fields rejected");
        var state = new PetState { pet_id = "p", rule_version = CommonServerContract.RuleVersion, asset_status = "none",
            level = 1, required_exp = 100, upper_body = 50, lower_body = 50, nutrition = 50, activity = 50, affinity = 50, initiative = 50 };
        Check(state.IsValidCommonState("p"), "initial DTO");
        Check(!state.IsValidCommonState("another-pet"), "cross-pet state rejected");
        foreach (var number in new[] { -1f, 101f, float.NaN, float.PositiveInfinity })
        { state.upper_body = number; Check(!state.IsValidCommonState("p"), "invalid stat " + number); }
        state.upper_body = 50;
        foreach (var number in new[] { -100f, 0f, 100f })
        { state.energy_balance = number; Check(state.IsValidCommonState("p"), "energy boundary " + number); }
        state.energy_balance = 100.1f; Check(!state.IsValidCommonState("p"), "energy range enforcement"); state.energy_balance = 0;
        state.published_model_stage = 1; Check(!state.IsValidCommonState("p"), "published cannot exceed authorized target"); state.published_model_stage = 0;
        state.rule_version = "healthmon.v2.1"; Check(!state.IsValidCommonState("p"), "old rules response rejected");
        var displays = new ProposalDisplayGate();
        displays.Observe("proposal-A");
        Check(displays.NextToAcknowledge() == null, "unbound scope cannot acknowledge a display");
        displays.Reset("server-A", "alice", "pet-A");
        Check(displays.NextToAcknowledge() == null, "fetching a quest does not observe its display");
        Check(!displays.TryBegin(null) && !displays.Acknowledged(null) && !displays.Failed(null), "missing proposal IDs stay unacknowledged");
        for (int repaint = 0; repaint < 100; repaint++) displays.Observe("proposal-A");
        Check(displays.NextToAcknowledge() == "proposal-A", "a painted offer is queued once despite repaint repetition");
        int displayedScope = displays.Generation;
        Check(displays.TryBegin("proposal-A") && !displays.TryBegin("proposal-A"), "only one display ACK may be in flight");
        displays.Observe("proposal-A");
        Check(displays.NextToAcknowledge() == null, "repainting an in-flight ACK does not send another request");
        Check(!displays.Complete(displayedScope - 1, "proposal-A", true), "stale scope ACK cannot confirm an offer");
        Check(displays.Complete(displayedScope, "proposal-A", false) && displays.Failed("proposal-A") && !displays.Acknowledged("proposal-A"),
            "failed ACK leaves accept and reject locked");
        displays.Observe("proposal-A");
        Check(displays.NextToAcknowledge() == null, "repaint does not silently retry a failed ACK");
        displays.Retry("proposal-A");
        Check(displays.TryBegin("proposal-A") && displays.Complete(displayedScope, "proposal-A", true) && displays.Acknowledged("proposal-A"),
            "explicit retry confirms the same proposal");
        displays.Observe("proposal-A");
        Check(displays.NextToAcknowledge() == null && !displays.Complete(displayedScope, "proposal-A", true), "successful ACK is not repeated");
        foreach (var identity in new[] { new[] { "server-B", "alice", "pet-A" }, new[] { "server-B", "bob", "pet-A" }, new[] { "server-B", "bob", "pet-B" } })
        {
            int priorScope = displays.Generation;
            displays.Reset(identity[0], identity[1], identity[2]);
            Check(!displays.Acknowledged("proposal-A") && displays.NextToAcknowledge() == null, "new server/account/pet clears prior display evidence");
            displays.Observe("proposal-A"); displays.TryBegin("proposal-A");
            Check(!displays.Complete(priorScope, "proposal-A", true) && !displays.Acknowledged("proposal-A"), "late prior-scope ACK cannot unlock same-ID offer");
        }
        displays.Reset("server-B", "bob", "pet-B");
        displays.Observe("proposal-A", serverAlreadyAcknowledged: true);
        Check(displays.Acknowledged("proposal-A") && displays.NextToAcknowledge() == null, "authenticated server shown evidence avoids duplicate ACK on reconnect");
        var proposal = new QuestOffer { id = "proposal-A", is_proposal = true, status = "offered" };
        Check(proposal.IsPendingProposal, "new offered proposal requires a display acknowledgement");
        proposal.status = "active"; proposal.shown_at = "2026-10-22T03:00:00Z";
        Check(proposal.IsPendingProposal, "acknowledged active proposal remains available for accept/reject");
        proposal.accepted_at = "2026-10-22T03:01:00Z";
        Check(!proposal.IsPendingProposal, "accepted proposal is not offered again"); proposal.accepted_at = null;
        proposal.cancelled_at = "2026-10-22T03:01:00Z";
        Check(!proposal.IsPendingProposal, "cancelled proposal has no decision UI"); proposal.cancelled_at = null;
        proposal.excluded = true; Check(!proposal.IsPendingProposal, "excluded proposal has no decision UI"); proposal.excluded = false;
        proposal.is_proposal = false; Check(!proposal.IsPendingProposal, "basic quest cannot generate proposal display evidence");
        var pendingScope = new PendingChatSnapshot { base_url = "https://team.example/healthmon", server_instance_id = "server-A", owner_id = "alice", pet_id = "pet-A" };
        Check(CommonServerContract.MatchesPendingScope(pendingScope, "https://team.example/healthmon/", "server-A", "alice", "pet-A"), "same pending identity accepts URL normalization");
        foreach (var changed in new[] {
            new[] { "https://foreign.example/healthmon", "server-A", "alice", "pet-A" },
            new[] { "https://team.example/other", "server-A", "alice", "pet-A" },
            new[] { "https://team.example/healthmon", "server-B", "alice", "pet-A" },
            new[] { "https://team.example/healthmon", "server-A", "bob", "pet-A" },
            new[] { "https://team.example/healthmon", "server-A", "alice", "pet-B" },
            new[] { "https://token@team.example/healthmon", "server-A", "alice", "pet-A" } })
            Check(!CommonServerContract.MatchesPendingScope(pendingScope, changed[0], changed[1], changed[2], changed[3]), "pending authentication rejects changed URL/server/account/pet");
        Check(!CommonServerContract.MatchesPendingScope(null, "https://team.example/healthmon", "server-A", "alice", "pet-A"), "unknown pending identity is never adopted");
        pendingScope.owner_id = "unverified";
        Check(!CommonServerContract.MatchesPendingScope(pendingScope, pendingScope.base_url, "server-A", "unverified", "pet-A"), "unverified owner cannot reauthenticate a pending request");
        Check(CommonServerContract.IsEmptyPendingPlaceholder(new ChatRequest(), null, null), "fully empty inline-reload placeholder is recognizable");
        Check(CommonServerContract.IsEmptyPendingPlaceholder(new ChatRequest(), null, new PendingChatSnapshot { request = new ChatRequest() }), "nested empty inline placeholders contain no actual request");
        foreach (var real in new[] { new ChatRequest { request_id = "retained-request" }, new ChatRequest { text = "retained text" },
            new ChatRequest { state_version = 5 }, new ChatRequest { request_id = " " } })
            Check(!CommonServerContract.IsEmptyPendingPlaceholder(real, null, null), "any request evidence prevents automatic pending removal");
        Check(!CommonServerContract.IsEmptyPendingPlaceholder(new ChatRequest(), "pet-A", null), "pending pet evidence prevents automatic removal");
        Check(!CommonServerContract.IsEmptyPendingPlaceholder(new ChatRequest(), null, pendingScope), "frozen scope evidence prevents automatic removal");
        Check(!CommonServerContract.IsEmptyPendingPlaceholder(null, null, null), "ordinary null is not counted as a normalized phantom");
        var unknownFood = CommonServerContract.FoodConfirmationPayload("analysis", 0, null, null, "snack");
        Check(unknownFood.GetType().GetField("grams") == null && unknownFood.GetType().GetField("vegetable_fruit_g") == null,
            "unknown consumption quantities cannot silently serialize fabricated zero values");
        Check(!unknownFood.synthetic && !unknownFood.kcal_reconfirmed, "real consumption and calorie reconfirmation are opt-in flags");
        Check(unknownFood.revision == 1 && CommonServerContract.FoodConfirmationPayload("analysis", 0, 100, null, "breakfast", revision: 2).revision == 2,
            "food correction carries an explicit next revision without creating another meal");
        bool invalidRevisionRejected = false;
        try { CommonServerContract.FoodConfirmationPayload("analysis", 0, 100, null, "breakfast", revision: 0); }
        catch (ArgumentException) { invalidRevisionRejected = true; }
        Check(invalidRevisionRejected, "invalid food revision is rejected before transport");
        var knownFood = CommonServerContract.FoodConfirmationPayload("analysis", 2, 120, 0, "lunch", true, true);
        Check(knownFood is FoodConfirmationWithVegetables && ((FoodConfirmationWithVegetables)knownFood).grams == 120 &&
            ((FoodConfirmationWithVegetables)knownFood).vegetable_fruit_g == 0 && knownFood.synthetic && knownFood.kcal_reconfirmed && knownFood.meal_type == "lunch",
            "explicit zero produce is preserved separately from unknown produce");
        Check(CommonServerContract.FoodConfirmationPayload("analysis", 0, null, 80, "dinner") is FoodConfirmationWithoutQuantityWithVegetables,
            "known produce never fabricates total meal grams");
        Check(CommonServerContract.FoodConfirmationPayload("analysis", 0, 100, null, "breakfast").GetType() == typeof(FoodConfirmation),
            "known meal grams never fabricate unknown produce");
        foreach (var invalid in new float[] { -1, 0, 10001, float.NaN, float.PositiveInfinity })
        {
            bool rejected = false;
            try { CommonServerContract.FoodConfirmationPayload("analysis", 0, invalid, null, "snack"); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "invalid food consumption amount rejected");
        }
        foreach (var invalid in new float[] { -1, 10001, float.NaN, float.NegativeInfinity })
        {
            bool rejected = false;
            try { CommonServerContract.FoodConfirmationPayload("analysis", 0, 100, invalid, "snack"); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "invalid explicitly confirmed produce rejected");
        }
        var food = new FoodAnalysis { schema_version = "healthmon.food.v1", analysis_id = "analysis", backend = "remote", provenance = "real",
            candidates = new[] { new FoodCandidate { candidate_id = 0, food = "fixture", confidence = .8f,
                has_estimated_grams = true, estimated_grams = 250, per_100g = new FoodNutrients { vegetable_fruit_g = new NutrientValue { available = false } } } } };
        Check(CommonServerContract.ValidFoodAnalysis(food) && !food.IsSynthetic && !food.consumption_confirmed,
            "real analysis with unknown produce is distinct from confirmed consumption");
        food.provenance = "synthetic"; food.synthetic = true;
        Check(CommonServerContract.ValidFoodAnalysis(food) && food.IsSynthetic, "remote synthetic analysis retains visible synthetic provenance");
        food.synthetic = false; Check(!CommonServerContract.ValidFoodAnalysis(food), "contradictory analysis provenance rejected");
        food.provenance = "real"; food.backend = "mock";
        Check(!CommonServerContract.ValidFoodAnalysis(food), "mock analysis cannot masquerade as real");
        food.backend = "remote"; food.consumption_confirmed = true;
        Check(!CommonServerContract.ValidFoodAnalysis(food), "photo analysis cannot confirm consumption");
        food.consumption_confirmed = false; food.candidates[0].confidence = float.NaN;
        Check(!CommonServerContract.ValidFoodAnalysis(food), "invalid confidence rejected");
        food.candidates[0].confidence = .8f; food.candidates[0].per_100g.vegetable_fruit_g.available = true;
        food.candidates[0].per_100g.vegetable_fruit_g.value = float.NaN;
        Check(!CommonServerContract.ValidFoodAnalysis(food), "known nutrients must be finite");
        Console.WriteLine("HEALTHMON_CLIENT_CONTRACT_PASS checks=" + checks);
        return 0;
    }
}
