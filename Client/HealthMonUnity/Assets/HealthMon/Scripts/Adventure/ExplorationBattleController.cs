using System;
using UnityEngine;

// Keep this component OUTSIDE BattleRoot so it stays enabled while BattleRoot is hidden.
public class ExplorationBattleController : MonoBehaviour
{
    [Header("Existing Battle")]
    [SerializeField] private BattleManager battleManager;
    [SerializeField] private GameObject battleRoot;

    [Header("Exploration Screen")]
    [SerializeField] private GameObject floorPanel;
    [SerializeField] private Camera explorationCamera;

    public event Action<bool> BattleFinished;
    public bool IsBattling { get; private set; }

    public void StartBattle(bool isElite)
    {
        if (IsBattling) return;
        if (battleManager == null || battleRoot == null)
        {
            Debug.LogError("[Exploration] BattleManager or BattleRoot not assigned.");
            return;
        }

        IsBattling = true;
        if (floorPanel != null) floorPanel.SetActive(false);
        if (explorationCamera != null) explorationCamera.enabled = false;
        battleRoot.SetActive(true);

        if (isElite) battleManager.StartEliteBattle();
        else battleManager.StartNormalBattle();
    }

    // Wire the result panel's Confirm/Continue button to this method.
    public void ConfirmBattleResult()
    {
        if (!IsBattling || battleManager == null) return;
        if (battleManager.currentState != BattleState.Finished ||
            !battleManager.LastBattleVictory.HasValue) return;

        bool victory = battleManager.LastBattleVictory.Value;
        IsBattling = false;
        battleRoot.SetActive(false);
        if (explorationCamera != null) explorationCamera.enabled = true;
        if (floorPanel != null) floorPanel.SetActive(true);

        Debug.Log(victory ? "[Exploration] Battle won" : "[Exploration] Battle lost");
        BattleFinished?.Invoke(victory);
    }
}
