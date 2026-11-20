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
                    // Repair only the obsolete local default, and only for the same credential.
                    // Keep deliberately selected remote servers/accounts untouched.
                    if (Uri.TryCreate(url, UriKind.Absolute, out var savedOrigin) && savedOrigin.IsLoopback && savedOrigin.Port == 8000)
                    {
                        string project = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
                        string runtimeDir = Path.Combine(project, ".runtime") + Path.DirectorySeparatorChar;
                        string profileFile = Path.Combine(runtimeDir, "unity-server.json");
                        if (File.Exists(profileFile))
                        {
                            var current = JsonUtility.FromJson<NativeProfile>(File.ReadAllText(profileFile));
                            string sessionFile = Path.GetFullPath(Path.Combine(project, current.session));
                            if (sessionFile.StartsWith(runtimeDir, StringComparison.OrdinalIgnoreCase) && File.Exists(sessionFile))
                            {
                                var session = JsonUtility.FromJson<NativeSession>(File.ReadAllText(sessionFile));
                                if (session.bearer_token == token && Uri.TryCreate(current.base_url, UriKind.Absolute, out var origin) && origin.IsLoopback &&
                                    CommonServerContract.NormalizeBaseUrl(session.api_base_url) == CommonServerContract.NormalizeBaseUrl(current.base_url))
                                { url = current.base_url; Remember(url, token, pet); }
                            }
                        }
                    }
                }
                else
                {
                    string root = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.."));
                    string runtime = Path.Combine(root, ".runtime") + Path.DirectorySeparatorChar;
                    string profilePath = Path.Combine(runtime, "unity-server.json");
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
