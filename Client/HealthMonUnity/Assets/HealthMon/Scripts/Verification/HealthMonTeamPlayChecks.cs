#if UNITY_EDITOR
using System;
using System.Collections;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

[InitializeOnLoad]
public static class HealthMonTeamPlayChecks
{
    static HealthMonTeamPlayChecks()
    {
        EditorApplication.playModeStateChanged += state =>
        {
            if (state == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool("HealthMonTeamChecks", false))
            {
                SessionState.SetBool("HealthMonTeamChecks", false);
                var go = new GameObject("Team integration verification");
                UnityEngine.Object.DontDestroyOnLoad(go);
                go.AddComponent<HealthMonTeamPlayRunner>();
            }
        };
    }

    public static void Run()
    {
        if (Environment.GetEnvironmentVariable("HEALTHMON_TEAM_PREFS_BACKUP") != "1")
            throw new InvalidOperationException("Launch through the isolated PlayerPrefs verification wrapper.");
        EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
        SessionState.SetBool("HealthMonTeamChecks", true);
        EditorApplication.isPlaying = true;
    }
}

public sealed class HealthMonTeamPlayRunner : MonoBehaviour
{
    private int checks, exceptions;
    private string output;
    private void Start()
    {
        output = Environment.GetEnvironmentVariable("HEALTHMON_TEAM_OUTPUT");
        Directory.CreateDirectory(output);
        Application.logMessageReceived += Observe;
        StartCoroutine(Guard(ExerciseScreens()));
    }
    private void Observe(string message, string trace, LogType type)
    {
        if (type == LogType.Exception || type == LogType.Error) exceptions++;
    }
    private IEnumerator Guard(IEnumerator routine)
    {
        while (true)
        {
            object item;
            try { if (!routine.MoveNext()) break; item = routine.Current; }
            catch (Exception error) { Finish(error.ToString()); yield break; }
            yield return item;
        }
        Finish(exceptions == 0 ? null : exceptions + " runtime errors");
    }
    private void Finish(string error)
    {
        File.WriteAllText(Path.Combine(output, "play-checks.json"), JsonUtility.ToJson(new Result {
            passed = error == null, checks = checks, runtime_errors = exceptions, error = error
        }, true));
        Application.logMessageReceived -= Observe;
        EditorApplication.Exit(error == null ? 0 : 1);
    }
    [Serializable] private sealed class Result { public bool passed; public int checks, runtime_errors; public string error; }
    private void Check(bool condition, string message)
    { checks++; if (!condition) throw new InvalidOperationException(message); }

    private IEnumerator ExerciseScreens()
    {
        yield return new WaitForSecondsRealtime(3);
        Check(SceneManager.GetActiveScene().name == "MainARScene", "Main scene opens");
        yield return Capture("01-home");
        var roster = FindAnyObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        roster.Open();
        yield return null;
        Check(roster.overlay.activeSelf && roster.listPage.activeSelf, "Character roster opens");
        yield return Capture("02-characters");
        roster.Close();
        var pose = FindAnyObjectByType<HealthMonPoseScreen>(FindObjectsInactive.Include);
        pose.Open();
        yield return null;
        Check(pose.view.selection.activeSelf, "Pose exercise selection retained");
        yield return Capture("03-training");
        pose.Close();
        GameObject.Find("UI/Canvas/BottomNavV2/BottomRow/AdventureButton").GetComponent<Button>().onClick.Invoke();
        float deadline = Time.realtimeSinceStartup + 25;
        while (SceneManager.GetActiveScene().name != "AdventureScene" && Time.realtimeSinceStartup < deadline) yield return null;
        Check(SceneManager.GetActiveScene().name == "AdventureScene", "Navigation loads exploration");
        yield return new WaitForSecondsRealtime(2);
        var entranceHome = Array.Find(FindObjectsByType<Button>(FindObjectsInactive.Include), b => b.name == "HomeButton");
        Check(entranceHome != null && entranceHome.gameObject.activeInHierarchy, "Home is reachable from the entrance");
        yield return Capture("04-exploration");
        var adventure = FindAnyObjectByType<AdventureManager>();
        var battleController = FindAnyObjectByType<BattleController>();
        adventure.EnterExploration();
        deadline = Time.realtimeSinceStartup + 15;
        BattleManager battle = null;
        while (Time.realtimeSinceStartup < deadline)
        {
            battle = FindAnyObjectByType<BattleManager>(FindObjectsInactive.Include);
            if (battleController.IsBattling && battle != null && battle.currentState == BattleState.PlayerSelecting) break;
            yield return null;
        }
        Check(adventure.CurrentFloor == 1 && battleController.IsBattling, "First floor starts a battle");
        Check(battle != null && battle.currentState == BattleState.PlayerSelecting, "Battle reaches player turn");
        Check(battle.battleUI.enemyNameText != null && battle.battleUI.enemyNameText.text == battle.enemy.unitName, "Enemy label is populated");
        yield return Capture("05-battle");
        // Only this unsaved runtime enemy is reduced to one HP, to verify the actual
        // attack/result/continue path quickly without changing the team's balancing.
        battle.enemy.currentHP = 1;
        battle.ExecutePlayerAction(BattleActionType.Attack);
        yield return new WaitForSecondsRealtime(2);
        Check(battle.LastBattleVictory == true && battle.currentState == BattleState.Finished, "Attack reaches victory");
        battleController.ConfirmBattleResult();
        Check(!battleController.IsBattling && adventure.State == ExplorationState.Exploring, "Victory returns to exploration");
        adventure.DescendFloor();
        deadline = Time.realtimeSinceStartup + 10;
        while (adventure.CurrentFloor < 2 && Time.realtimeSinceStartup < deadline) yield return null;
        Check(adventure.CurrentFloor == 2, "Next floor is playable");
        var home = Array.Find(FindObjectsByType<Button>(FindObjectsInactive.Include), b => b.name == "HomeButton");
        home.onClick.Invoke();
        deadline = Time.realtimeSinceStartup + 25;
        while (SceneManager.GetActiveScene().name != "MainARScene" && Time.realtimeSinceStartup < deadline) yield return null;
        Check(SceneManager.GetActiveScene().name == "MainARScene", "Return home works");
        yield return new WaitForSecondsRealtime(2);
        Check(FindAnyObjectByType<HealthMonPoseScreen>(FindObjectsInactive.Include) != null, "Pose training survives return");
        yield return Capture("06-home-return");
    }

    private IEnumerator Capture(string name)
    {
        yield return new WaitForEndOfFrame();
        ScreenCapture.CaptureScreenshot(Path.Combine(output, name + ".png"));
        yield return new WaitForSecondsRealtime(.25f);
    }
}
#endif
