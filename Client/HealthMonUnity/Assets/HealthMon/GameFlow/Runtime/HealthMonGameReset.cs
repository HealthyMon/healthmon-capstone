using UnityEngine;

/// <summary>
/// Two-phase reset: existing MonoBehaviours may save again during OnApplicationQuit.
/// The one-time reset marker makes the next launch repeat the same scoped deletion
/// BEFORE normal Awake/Start, without touching any online account or app preferences.
/// </summary>
public static class HealthMonGameReset
{
    private const string Pending = "HealthMon_GameFlow_ResetPending_v1";
    public static bool IsResetPending => PlayerPrefs.GetInt(Pending, 0) == 1;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void FinishResetAtNextLaunch()
    {
        if (!IsResetPending) return;
        ClearOnlyGameKeys();
        PlayerPrefs.DeleteKey(Pending);
        PlayerPrefs.Save();
        Debug.Log("[GameFlow] Local reset finalized at launch; server/account settings preserved.");
    }

    public static void MarkAndReset()
    {
        PlayerPrefs.SetInt(Pending, 1);
        ClearOnlyGameKeys();
        PlayerPrefs.Save();
    }

    private static void ClearOnlyGameKeys()
    {
        string[] keys = {
            "HM_PLAYER_NICKNAME", "HM_PLAYER_CHARACTER_INDEX", "HM_PLAYER_SETUP_DONE",
            "HealthMon_Pet_Save_v1", "HealthMon_Quest_Save_v1",
            "HealthMon_Customization_Jewelry_v3", "HealthMon_Customization_Jewelry_v2",
            "HealthMon_Customization_Save_v1", "HealthMon_3D_Jewelry_LocalPositions_v1",
            "HealthMon_Offline_Actions_v1", "HealthMon_Offline_WorkoutRecords_v1",
            "HealthMon_Offline_StarterGranted_v1", "HealthMon_Offline_GrowthStage_v1",
            "HealthMonShop_StandaloneCoins_v1", "HealthMonShop_OfflineOwned_v1",
            "HealthMonShop_OfflineSelectedPet_v1",
            "HealthMon_Roster_Selected_v1", HealthMonGameRules.SaveKey
        };
        foreach (var key in keys) PlayerPrefs.DeleteKey(key);
        DeleteCharacter("pet_starter");
        for (char series = 'n'; series <= 's'; series++)
            for (int index = 1; index <= 6; index++)
                DeleteCharacter("slot_" + series + index);
        // Offline mode preference is intentionally NOT deleted: new play stays offline.
        // Active server sessions, credentials, remote model jobs and unrelated prefs are untouched.
        PlayerPrefs.Save();
    }
    private static void DeleteCharacter(string id)
    {
        PlayerPrefs.DeleteKey("HealthMon_Roster_Data_v1_" + id);
        PlayerPrefs.DeleteKey("HealthMon_Roster_Jewelry_v1_" + id);
        PlayerPrefs.DeleteKey("HealthMon_Roster_JewelryPlacement_v1_" + id);
    }
}
