#if UNITY_EDITOR
using System;
using Healthmon.Beta;
using Healthmon.Common;
using UnityEditor;
using UnityEngine;

// Headless editor verification entrypoint. Uses Unity's real JsonUtility and real scene
// component logic; no reflection into server internals or duplicate rule implementation.
public static class CommonServerVerification
{
    [MenuItem("HealthMon/Verification/Inspect pending authentication metadata")]
    public static void InspectPendingAuthentication()
    {
        var api = UnityEngine.Object.FindAnyObjectByType<HealthmonApiClient>(FindObjectsInactive.Include);
        if (api == null) { Debug.Log("HEALTHMON_PENDING_METADATA no_client=true"); return; }
        Debug.Log("HEALTHMON_PENDING_METADATA " + JsonUtility.ToJson(api.GetPendingDiagnostics()));
    }

    [MenuItem("HealthMon/Verification/Run native DTO and authority checks")]
    public static void Run()
    {
        int assertions = 0;
        Action<bool, string> check = (condition, message) =>
        { assertions++; if (!condition) throw new Exception("Common server verification: " + message); };
        check(PlayerSettings.insecureHttpOption == InsecureHttpOption.DevelopmentOnly, "HTTP permitted only in development builds; release requires HTTPS");
        var gate = new StateVersionGate();
        gate.Reset("server1", "owner1", "pet1"); int oldGeneration = gate.Generation;
        check(gate.Accept(oldGeneration, 15), "first state accepted");
        check(!gate.Accept(oldGeneration, 14), "delayed state cannot roll back version");
        check(gate.Accept(oldGeneration, 15), "same-version refresh is valid");
        gate.Reset("server1", "owner2", "pet1");
        check(!gate.Accept(oldGeneration, 90), "previous account callback rejected");
        check(gate.Accept(gate.Generation, 0), "new account can start at lower version");
        int accountGeneration = gate.Generation; gate.Reset("server2", "owner2", "pet1");
        check(!gate.Accept(accountGeneration, 1000), "old server callback rejected");
        check(CommonServerContract.NormalizeBaseUrl("http://127.0.0.1:8000/") == "http://127.0.0.1:8000", "URL normalization");
        foreach (var invalid in new[] { "file:///tmp/db", "https://token@localhost", "https://localhost/?token=x", "https://localhost/#secret" })
        {
            bool rejected = false; try { CommonServerContract.NormalizeBaseUrl(invalid); } catch (ArgumentException) { rejected = true; }
            check(rejected, "invalid credential-bearing/non-HTTP URL rejected");
        }
        const string json = "{\"pet_id\":\"pet1\",\"state_version\":7,\"rule_version\":\"healthmon.v2.2\",\"level\":1,\"current_exp\":0,\"required_exp\":100,\"total_exp\":0,\"coin\":0,\"upper_body\":50,\"lower_body\":50,\"nutrition\":50,\"energy_balance\":0,\"activity\":50,\"affinity\":50,\"initiative\":50,\"evolution_target_stage\":0,\"published_model_stage\":0,\"asset_status\":\"none\",\"model_reference\":null}";
        check(CommonServerContract.HasRequiredStateFields(json), "required zero values accepted");
        check(!CommonServerContract.HasRequiredStateFields(json.Replace("\"nutrition\":50", "\"nutrition\":null")), "unknown stat is not invented as zero");
        check(!CommonServerContract.HasRequiredStateFields(json.Replace("\"coin\":0,", "")), "missing coin rejected");
        var state = JsonUtility.FromJson<PetState>(json);
        check(state.IsValidCommonState("pet1"), "v2.2 DTO parsed by real JsonUtility");
        check(!state.IsValidCommonState("pet2"), "cross-pet response rejected");
        state.upper_body = float.NaN; check(!state.IsValidCommonState("pet1"), "NaN score rejected"); state.upper_body = 50;
        state.rule_version = "healthmon.rules.v2.1"; check(!state.IsValidCommonState("pet1"), "old rules contract rejected"); state.rule_version = CommonServerContract.RuleVersion;
        state.energy_balance = -100; check(state.IsValidCommonState("pet1"), "energy lower boundary valid");
        state.energy_balance = 101; check(!state.IsValidCommonState("pet1"), "energy outside range rejected"); state.energy_balance = 0;
        var go = new GameObject("Common server authority verification");
        try
        {
            var manager = go.AddComponent<PetStateManager>();
            manager.ApplyServerState(state);
            check(manager.HasVerifiedServerState && manager.CurrentLevel == 1 && manager.CurrentCoin == 0, "server snapshot applied");
            manager.AddReward(10000, 999); manager.AddExp(10000); manager.AddIntimacy(99); manager.AddActivity(99);
            manager.SetAdminValues(99, 999, 0, 0, 0, 0); manager.ApplyEvolutionStage(3);
            check(manager.CurrentLevel == 1 && manager.CurrentCoin == 0 && manager.CurrentIntimacy == 50 && manager.CurrentActivity == 50, "local rewards/admin/evolution cannot mutate common state");
            manager.ClearServerState(); check(!manager.HasVerifiedServerState, "connection change clears authority");
        }
        finally { UnityEngine.Object.DestroyImmediate(go); }
        Debug.Log("HEALTHMON_COMMON_SERVER_VERIFICATION_PASS assertions=" + assertions);
    }
}
#endif
