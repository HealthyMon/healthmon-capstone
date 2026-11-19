using System;
using System.IO;
using UnityEngine;

public static class AdventureSaveSystem
{
    public static string SavePath => Path.Combine(Application.persistentDataPath, "adventure_checkpoint.json");

    public static bool TrySave(AdventureSaveData data)
    {
        string temp = SavePath + ".tmp";
        try
        {
            if (data == null || !data.IsValid())
                throw new InvalidDataException("Invalid checkpoint data.");
            Directory.CreateDirectory(Application.persistentDataPath);
            File.WriteAllText(temp, JsonUtility.ToJson(data, true));
            if (File.Exists(SavePath))
            {
                // Keep the last good save if replacement fails.
                File.Replace(temp, SavePath, null);
            }
            else File.Move(temp, SavePath);
            Debug.Log("[AdventureSave] Saved: " + SavePath);
            return true;
        }
        catch (Exception ex)
        {
            Debug.LogError("[AdventureSave] Save failed: " + ex.Message);
            return false;
        }
    }

    public static bool TryLoad(out AdventureSaveData data)
    {
        data = null;
        try
        {
            if (!File.Exists(SavePath)) return false;
            var candidate = JsonUtility.FromJson<AdventureSaveData>(File.ReadAllText(SavePath));
            if (candidate == null || !candidate.IsValid())
                throw new InvalidDataException("Invalid checkpoint data.");
            data = candidate;
            return true;
        }
        catch (Exception ex)
        {
            Debug.LogError("[AdventureSave] Load failed: " + ex.Message);
            return false;
        }
    }
}
