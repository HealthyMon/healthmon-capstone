using UnityEditor;
using UnityEngine;

public static class HealthMonPortraitVerification
{
    public static void Rebuild()
    {
        var catalog = AssetDatabase.LoadAssetAtPath<HealthMonCharacterRosterAsset>("Assets/HealthMon/MultiCharacter/HealthMonCharacterRoster.asset");
        if (catalog == null) throw new System.InvalidOperationException("Character catalog missing");
        HealthMonCharacterPrefabPortraitBaker.Begin(catalog);
        EditorApplication.update += Finish;
    }
    private static void Finish()
    {
        if (HealthMonCharacterPrefabPortraitBaker.IsRunning) return;
        EditorApplication.update -= Finish;
        Debug.Log("Front portrait rendering complete; failed=" + HealthMonCharacterPrefabPortraitBaker.FailedCount);
        EditorApplication.Exit(HealthMonCharacterPrefabPortraitBaker.FailedCount == 0 ? 0 : 1);
    }
}
