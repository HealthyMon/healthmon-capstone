using System;
using System.IO;
using UnityEngine;

namespace Healthmon.Common
{
    // Provisioned by the local launcher, never bundled into the APK or a scene.
    [Serializable]
    internal sealed class LocalConnectionProfile
    {
        public int schema_version;
        public string environment, api_base_url, bearer_token, pet_id, owner_id, server_instance_id;

        internal static bool TryRead(out LocalConnectionProfile profile)
        {
            profile = null;
            try
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                using (var player = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (var activity = player.GetStatic<AndroidJavaObject>("currentActivity"))
                using (var files = activity.Call<AndroidJavaObject>("getFilesDir"))
                    return TryReadFile(Path.Combine(files.Call<string>("getAbsolutePath"), "healthmon-connection.json"), out profile);
#elif UNITY_EDITOR
                string root = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
                return TryReadFile(Path.Combine(root, ".runtime/client-connection.json"), out profile);
#elif UNITY_STANDALONE_WIN
                var directory = new DirectoryInfo(Application.dataPath).Parent;
                for (int i = 0; directory != null && i < 6; i++, directory = directory.Parent)
                {
                    if (!File.Exists(Path.Combine(directory.FullName, "Start-HealthMon.cmd"))) continue;
                    return TryReadFile(Path.Combine(directory.FullName, ".runtime/client-connection.json"), out profile);
                }
#endif
            }
            catch (Exception) { /* A missing/incomplete handoff is retried later. */ }
            return false;
        }

        internal static bool TryReadFile(string path, out LocalConnectionProfile profile)
        {
            profile = null;
            try
            {
                var file = new FileInfo(path);
                if (!file.Exists || file.Length > 16384) return false;
                var value = JsonUtility.FromJson<LocalConnectionProfile>(File.ReadAllText(path));
                if (value == null || value.schema_version != 1 || value.environment != "test" ||
                    string.IsNullOrWhiteSpace(value.server_instance_id) || string.IsNullOrWhiteSpace(value.owner_id)) return false;
                value.api_base_url = CommonServerContract.NormalizeBaseUrl(value.api_base_url);
                if (!new Uri(value.api_base_url).IsLoopback) return false;
                value.bearer_token = CommonServerContract.NormalizeBearerToken(value.bearer_token);
                profile = value;
                return true;
            }
            catch (Exception) { return false; }
        }
    }
}
