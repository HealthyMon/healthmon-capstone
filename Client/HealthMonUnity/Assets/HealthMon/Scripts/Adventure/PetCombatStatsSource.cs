using Healthmon.Common;
using UnityEngine;

/// <summary>Read online authority or carry the selected offline character across a scene load.</summary>
public static class PetCombatStatsSource
{
    private static PetCombatStats? offlineSnapshot;
    private static string offlineScope;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset() { offlineSnapshot = null; offlineScope = null; }

    public static bool TryGetCurrent(out PetCombatStats stats, out string scope)
    {
        stats = default; scope = null;
        if (CommonServerConnection.UsesServerAuthority)
        {
            var connection = CommonServerConnection.Instance;
            var state = connection?.LatestState;
            // A retained verified snapshot is usable during a temporary network outage.
            // Reconnect/account changes clear LatestState in CommonServerConnection.
            if (state == null || !state.IsValidCommonState(connection.Api.PetId) || state.level > 30) return false;
            stats = PetCombatStats.FromState(state);
            scope = connection.BaseUrl + "|" + connection.ServerInstanceId + "|" + connection.OwnerId + "|" + state.pet_id;
            return true;
        }

        var pet = Object.FindAnyObjectByType<PetStateManager>(FindObjectsInactive.Include);
        if (pet != null)
        {
            var rules = HealthMonGameRules.Instance;
            string selected = rules != null && !string.IsNullOrEmpty(rules.CharacterId) ? rules.CharacterId :
                PlayerPrefs.GetString("HealthMon_Roster_Selected_v1", "pet_starter");
            var profile = rules != null ? rules.ForId(selected) : null;
            stats = PetCombatStats.Calculate(pet.CurrentLevel, profile?.upperBody ?? 50, profile?.lowerBody ?? 50,
                50, 0, pet.CurrentActivity, pet.CurrentIntimacy, profile?.initiative ?? pet.CurrentCuriosity);
            scope = "offline|" + selected;
            return true;
        }
        stats = offlineSnapshot ?? PetCombatStats.Calculate(1, 50, 50, 50, 0, 50, 50, 50);
        scope = offlineScope ?? "offline|standalone";
        return true;
    }

    public static void CaptureForAdventure()
    {
        offlineSnapshot = null; offlineScope = null;
        if (!CommonServerConnection.UsesServerAuthority && TryGetCurrent(out var stats, out var scope))
        { offlineSnapshot = stats; offlineScope = scope; }
    }
}
