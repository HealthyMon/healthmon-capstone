#if UNITY_EDITOR
using System;
using System.IO;
using UnityEngine;

namespace Healthmon.Common
{
    // Editor-session memory only: credentials never enter a scene or PlayerPrefs.
    internal static class EditorConnectionSession
    {
        [Serializable] private sealed class Connection { public string url, token, pet; }
        [Serializable] private sealed class NativeProfile { public string base_url, session, pet_id; }
        [Serializable] private sealed class NativeSession { public string api_base_url, bearer_token; }
        private static string Key => "HealthMon.Connection." + Application.dataPath;

        internal static void Remember(string url, string token, string pet)
        {
            UnityEditor.SessionState.SetString(Key, JsonUtility.ToJson(new Connection { url = url, token = token, pet = pet }));
        }

        internal static bool TryRead(out string url, out string token, out string pet)
        {
            url = token = pet = null;
            try
            {
                var saved = UnityEditor.SessionState.GetString(Key, "");
                if (!string.IsNullOrEmpty(saved))
                {
                    var connection = JsonUtility.FromJson<Connection>(saved);
                    url = connection.url; token = connection.token; pet = connection.pet;
                }
                else
                {
                    string root = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
                    string runtime = Path.Combine(root, ".runtime") + Path.DirectorySeparatorChar;
                    // A UI worktree can reuse an existing server without declaring a second server installation.
                    string profilePath = Path.Combine(runtime, "editor-connection.json");
                    if (!File.Exists(profilePath)) profilePath = Path.Combine(runtime, "native-server.json");
                    if (!File.Exists(profilePath)) return false;
                    var profile = JsonUtility.FromJson<NativeProfile>(File.ReadAllText(profilePath));
                    var origin = new Uri(profile.base_url);
                    if (!origin.IsLoopback || (origin.Scheme != "http" && origin.Scheme != "https")) return false;
                    string sessionPath = Path.GetFullPath(Path.Combine(root, profile.session));
                    if (!sessionPath.StartsWith(runtime, StringComparison.OrdinalIgnoreCase) || !File.Exists(sessionPath)) return false;
                    var session = JsonUtility.FromJson<NativeSession>(File.ReadAllText(sessionPath));
                    if (CommonServerContract.NormalizeBaseUrl(session.api_base_url) != CommonServerContract.NormalizeBaseUrl(profile.base_url)) return false;
                    url = profile.base_url; token = session.bearer_token; pet = profile.pet_id;
                }
                url = CommonServerContract.NormalizeBaseUrl(url);
                token = CommonServerContract.NormalizeBearerToken(token);
                return !string.IsNullOrWhiteSpace(pet);
            }
            catch (Exception)
            {
                url = token = pet = null;
                return false;
            }
        }
    }
}
#endif
