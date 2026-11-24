using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Healthmon.Common;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class HealthMonAcceptanceVerification
{
    static HealthMonAcceptanceVerification()
    {
        EditorApplication.playModeStateChanged += state => {
            if (state != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool("HM.Acceptance", false)) return;
            SessionState.SetBool("HM.Acceptance", false);
            new GameObject("Portable acceptance").AddComponent<HealthMonAcceptanceRunner>();
        };
    }

    public static void Run()
    {
        if (Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP") != "1")
            throw new InvalidOperationException("Exact preference backup required");
        PlayerPrefs.SetInt("HealthMon_Offline_Mode_v1", 0);
        PlayerPrefs.Save();
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        var game = EditorWindow.GetWindow(typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView"));
        game.Show(); game.Focus();
        SessionState.SetBool("HM.Acceptance", true);
        EditorApplication.isPlaying = true;
    }

    public static void Finish(int code)
    {
        HealthMonAspectVerification.Finish(code);
    }
}

public class HealthMonAcceptanceRunner : MonoBehaviour
{
    async void Start()
    {
        string output = Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");
        try
        {
            Application.runInBackground = true;
            string configPath = Environment.GetEnvironmentVariable("HEALTHMON_NATIVE_E2E_CONFIG");
            var config = JsonUtility.FromJson<NativeE2EConfig>(File.ReadAllText(configPath));
            float deadline = Time.realtimeSinceStartup + 60;
            while (CommonServerConnection.Instance == null || !CommonServerConnection.Instance.IsConnected)
            {
                if (Time.realtimeSinceStartup > deadline) throw new Exception("Launcher auto-connection timeout");
                await Task.Delay(100);
            }
            var connection = CommonServerConnection.Instance;
            if (connection.ServerInstanceId != config.expected_server_instance_id || connection.OwnerId != config.expected_owner_id)
                throw new Exception("Automatic connection selected another installation");
            File.WriteAllText(Path.Combine(output, "auto-connection.txt"), "PASS: launcher credentials discovered without UI input");
            await Task.Delay(1500);
            ScreenCapture.CaptureScreenshot(Path.Combine(output, "auto-connected-home.png"));
            string root = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Temp/NativeE2E");
            Directory.CreateDirectory(root);
            var before = Directory.GetDirectories(root).ToHashSet();
            var runner = new GameObject("Native production UI acceptance").AddComponent<CommonServerNativeE2ERunner>();
            runner.ConfigPath = configPath;
            string result = null;
            deadline = Time.realtimeSinceStartup + config.timeout_seconds * config.cases.Length + 30;
            while (result == null)
            {
                result = Directory.GetDirectories(root).Where(p => !before.Contains(p)).Select(p => Path.Combine(p,"result.json")).FirstOrDefault(File.Exists);
                if (Time.realtimeSinceStartup > deadline) throw new Exception("Native UI acceptance timeout");
                await Task.Delay(200);
            }
            foreach (string source in Directory.GetFiles(Path.GetDirectoryName(result)))
                File.Copy(source, Path.Combine(output, Path.GetFileName(source)), true);
            var report = JsonUtility.FromJson<NativeE2EReport>(File.ReadAllText(result));
            if (report.status != "passed") throw new Exception(report.error_code);
            HealthMonAcceptanceVerification.Finish(0);
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(output,"failure.txt"), error.ToString());
            ScreenCapture.CaptureScreenshot(Path.Combine(output,"failure.png"));
            await Task.Delay(500);
            HealthMonAcceptanceVerification.Finish(1);
        }
    }
}
