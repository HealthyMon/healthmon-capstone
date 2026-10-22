using System;
using System.Reflection;
using System.Runtime.Serialization;

// Executes the compiled production mutation methods without a native Unity runtime.
// A native-less instance intentionally bypasses MonoBehaviour construction. Any accidental
// PlayerPrefs/UI/native work before the authority guard fails this managed verification.
// This complements, and does not replace, CommonServerVerification.Run in the editor.
public static class AuthorityGuardChecks
{
    public static int Main()
    {
        var state = (PetStateManager)FormatterServices.GetUninitializedObject(typeof(PetStateManager));
        Action<string, int> set = (name, value) => typeof(PetStateManager).GetField(name,
            BindingFlags.NonPublic | BindingFlags.Instance).SetValue(state, value);
        set("level", 1); set("coin", 0); set("intimacy", 50); set("activity", 50);
        state.AddReward(10000, 9999); state.AddExp(10000);
        state.AddIntimacy(99); state.AddActivity(99); state.AddKindness(99); state.AddCuriosity(99);
        state.SetAdminValues(99, 999, 99, 99, 99, 99); state.ApplyEvolutionStage(3);
        state.SavePetData(); state.LoadPetData();
        if (state.CurrentLevel != 1 || state.CurrentCoin != 0 || state.CurrentIntimacy != 50 || state.CurrentActivity != 50)
            throw new Exception("Local mutation changed server-authoritative state.");
        Console.WriteLine("HEALTHMON_MANAGED_AUTHORITY_GUARDS_PASS methods=10");
        foreach (string name in new[] { "CommonServerNativeE2ERunner", "CommonServerNativeVerification", "NativeE2EConfig", "NativeE2ECase", "NativeE2EReport", "NativeRenderStabilityGate", "NativeDialogueViewportEvidence", "NativeDialogueRaycastProbe", "NativeInputActionEvidence" })
            if (typeof(PetStateManager).Assembly.GetType(name, false) != null)
                throw new Exception("Editor-only native verification leaked into Android assembly: " + name);
        Console.WriteLine("HEALTHMON_ANDROID_NATIVE_VERIFIER_EXCLUSION_PASS types=9");
        foreach (var field in new[] {
            typeof(Healthmon.Beta.HealthmonApiClient).GetField("bearerToken", BindingFlags.Instance | BindingFlags.NonPublic),
            typeof(Healthmon.Common.CommonServerConnection).GetField("runtimeToken", BindingFlags.Instance | BindingFlags.NonPublic),
            typeof(Healthmon.Common.CommonServerConnection).GetField("tokenInput", BindingFlags.Instance | BindingFlags.NonPublic),
            typeof(DialoguePrototype).GetField("bearerToken", BindingFlags.Instance | BindingFlags.NonPublic),
            typeof(Healthmon.Evolution.EvolutionClient).GetField("bearerToken", BindingFlags.Instance | BindingFlags.NonPublic) })
            if (field == null || !field.IsNotSerialized) throw new Exception("A runtime credential permits hot-reload serialization.");
        var client = (Healthmon.Beta.HealthmonApiClient)FormatterServices.GetUninitializedObject(typeof(Healthmon.Beta.HealthmonApiClient));
        var pending = typeof(Healthmon.Beta.HealthmonApiClient).GetField("pendingChat", BindingFlags.Instance | BindingFlags.NonPublic);
        if (!pending.IsDefined(typeof(UnityEngine.SerializeReference), false)) throw new Exception("Pending null lacks reference serialization.");
        pending.SetValue(client, new Healthmon.Beta.ChatRequest());
        if (client.HasPendingChat || client.GetPendingDiagnostics().empty_placeholder_normalizations != 1)
            throw new Exception("A completely empty inline placeholder still blocks connection.");
        if (client.HasPendingChat || client.GetPendingDiagnostics().empty_placeholder_normalizations != 1)
            throw new Exception("Repeated status reads normalize the same empty object repeatedly.");
        var real = new Healthmon.Beta.ChatRequest { request_id = "same-request", text = "retained test message", state_version = 17 };
        pending.SetValue(client, real);
        if (!client.HasPendingChat || client.PendingRequestId != real.request_id || real.text != "retained test message" || real.state_version != 17)
            throw new Exception("Real pending request was changed or discarded by diagnostics.");
        var diagnostics = client.GetPendingDiagnostics();
        if (!diagnostics.has_request_id || !diagnostics.has_text || diagnostics.credential_available)
            throw new Exception("Pending metadata did not identify the retained request without credentials.");
        Console.WriteLine("HEALTHMON_PENDING_CREDENTIAL_GUARDS_PASS credential_fields=5 pending_checks=5");
        if (typeof(FoodScanPrototype).GetMethod("EnableSyntheticConsumptionFixture") != null)
            throw new Exception("Editor-only synthetic food fixture entrypoint leaked into Android.");
        foreach (string name in new[] { "syntheticFixture", "syntheticFixtureScope" })
            if (!typeof(FoodScanPrototype).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).IsNotSerialized)
                throw new Exception("Synthetic food fixture state permits hot-reload serialization.");
        Console.WriteLine("HEALTHMON_FOOD_FIXTURE_GUARDS_PASS editor_entrypoint_excluded=1 runtime_flags=2");
        return 0;
    }
}
