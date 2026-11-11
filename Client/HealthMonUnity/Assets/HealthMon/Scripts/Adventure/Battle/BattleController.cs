using System;
using UnityEngine;

// Keep this component OUTSIDE BattleRoot so it stays enabled while BattleRoot is hidden.
public class BattleController : MonoBehaviour
{
    [Header("Existing Battle")]
    [SerializeField] private BattleManager battleManager;
    [SerializeField] private GameObject battleRoot;

    [Header("Exploration Screen")]
    [SerializeField] private GameObject floorPanel;
    [SerializeField] private Camera explorationCamera;

    [Header("Enemy Spawner")]
    [SerializeField] private EnemySpawner enemySpawner;

    [Header("Battle Transition")]
    [SerializeField] private AdventureTransitionUI transitionUI;

    [Header("Adventure Stats")]
    [SerializeField]
    private AdventurePlayerStats adventurePlayerStats;

    public event Action<bool> BattleFinished;
    public bool IsBattling { get; private set; }



    public void StartBattle(bool isElite)
    {
        if (IsBattling) return;

        if (battleManager == null || battleRoot == null)
        {
            Debug.LogError("[Battle] BattleManager/BattleRoot 미연결");
            return;
        }

        if (enemySpawner == null)
        {
            Debug.LogError("[Battle] EnemySpawner 미연결");
            return;
        }

        IsBattling = true;

        if (transitionUI != null)
            transitionUI.PlayBattleIntro(
                isElite, () => BeginBattle(isElite));
        else
            BeginBattle(isElite);
    }

    private void BeginBattle(bool isElite)
    {
        if (floorPanel != null)
            floorPanel.SetActive(false);

        if (explorationCamera != null)
            explorationCamera.enabled = false;

        battleRoot.SetActive(true);

        bool spawned;

        // 일반/정예 몬스터 생성
        if (isElite)
            spawned = enemySpawner.SpawnEliteEnemy();
        else
            spawned = enemySpawner.SpawnNormalEnemy();

        if (!spawned)
        {
            Debug.LogError("[Battle] 몬스터 생성 실패");

            battleRoot.SetActive(false);

            if (explorationCamera != null)
                explorationCamera.enabled = true;

            if (floorPanel != null)
                floorPanel.SetActive(true);

            IsBattling = false;
            return;
        }

        // 기존 전투 시스템 시작
        if (isElite)
            battleManager.StartEliteBattle();
        else
            battleManager.StartNormalBattle();
    }



    // Wire the result panel's Confirm/Continue button to this method.

    public void ConfirmBattleResult()
    {
        if (!IsBattling || battleManager == null)
            return;

        if (battleManager.currentState != BattleState.Finished ||
            !battleManager.LastBattleVictory.HasValue)
            return;

        bool victory = battleManager.LastBattleVictory.Value;

        // 1. 전투 스탯 저장
        if (adventurePlayerStats != null)
        {
            adventurePlayerStats.CaptureFromBattleUnit(
                battleManager.player
            );
        }
        else
        {
            Debug.LogWarning(
                "[Battle] AdventurePlayerStats 미연결"
            );
        }

        // 2. 전투 종료
        IsBattling = false;

        // 3. 전투 화면 종료
        if (battleRoot != null)
            battleRoot.SetActive(false);

        // 4. 탐험 카메라 복구
        if (explorationCamera != null)
            explorationCamera.enabled = true;

        // 5. 탐험 UI 복구
        if (floorPanel != null)
            floorPanel.SetActive(true);

        // 6. 탐험 매니저에 결과 전달
        Debug.Log(
            victory
                ? "[Adventure] Battle won"
                : "[Adventure] Battle lost"
        );

        BattleFinished?.Invoke(victory);
    }

}
