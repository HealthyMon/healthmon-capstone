using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>Connects the team's exploration scene to the existing game navigation.</summary>
public sealed class HealthMonAdventureNavigation : MonoBehaviour
{
    private bool loading;

    public void OpenAdventure() { Load("AdventureScene"); }
    public void ReturnHome() { Load("MainARScene"); }

    private void Load(string sceneName)
    {
        if (loading) return;
        if (!Application.CanStreamedLevelBeLoaded(sceneName))
        {
            Debug.LogError("[Navigation] Scene is missing from the build: " + sceneName);
            return;
        }
        loading = true;
        SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Single);
    }
}
