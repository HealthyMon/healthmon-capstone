
using System;
using UnityEngine;

// Keep this component OUTSIDE BattleRoot so it stays enabled
// while BattleRoot is hidden.
public class BattleController : MonoBehaviour
{
    [Header("Existing Battle")]
    [SerializeField] private BattleManager battleManager;
    [SerializeField] private GameObject battleRoot;

    [Header("Exploration Screen")]
    [SerializeField] private GameObject floorPanel;
    [SerializeField] private GameObject adventurePlayerStatusPanel;
    [SerializeField] private Camera explorationCamera;

    [Header("Enemy Spawner")]
    [SerializeField] private EnemySpawner enemySpawner;

    [Header("Battle Transition")]
    [SerializeField] private AdventureTransitionUI transitionUI;

    [Header("Adventure Stats")]
    [SerializeField] private AdventurePlayerStats adventurePlayerStats;

    public event Action<bool> BattleFinished;

    public bool IsBattling { get; private set; }


    // ==========================================
    // 전투 환경 관리
    // ==========================================

    // BattleRoot가 비활성화되어 있어도 호출 가능
    public void HideBattleEnvironment()
    {
        if (battleRoot == null)
            return;

        var environment =
            battleRoot.GetComponent<BattleEnvironmentSwitcher>();

        if (environment != null)
            environment.Hide();
    }


    // ==========================================
    // 전투 시작
    // ==========================================

    public void StartBattle(bool isElite)
    {
        if (IsBattling)
            return;

        if (battleManager == null || battleRoot == null)
        {
            Debug.LogError(
                "[Battle] BattleManager/BattleRoot 미연결"
            );
            return;
        }

        if (enemySpawner == null)
        {
            Debug.LogError(
                "[Battle] EnemySpawner 미연결"
            );
            return;
        }

        IsBattling = true;

        // 전투 시작 애니메이션
        if (transitionUI != null)
        {
            transitionUI.PlayBattleIntro(
                isElite,
                () => BeginBattle(isElite)
            );
        }
        else
        {
            BeginBattle(isElite);
        }
    }


    // ==========================================
    // 전투 화면 전환
    // ==========================================

    private void BeginBattle(bool isElite)
    {
        // 탐험 상태 UI 숨김
        if (adventurePlayerStatusPanel != null)
            adventurePlayerStatusPanel.SetActive(false);

        // 탐험 층 UI 숨김
        if (floorPanel != null)
            floorPanel.SetActive(false);

        // 탐험 카메라 및 AudioListener 비활성화
        if (explorationCamera != null)
        {
            explorationCamera.enabled = false;

            var listener =
                explorationCamera.GetComponent<AudioListener>();

            if (listener != null)
                listener.enabled = false;
        }

        // 일반/정예 전투 배경 설정
        var environment =
            battleRoot.GetComponent<BattleEnvironmentSwitcher>();

        if (environment != null)
            environment.SetMode(isElite);

        // 전투 화면 활성화
        battleRoot.SetActive(true);

        bool spawned;

        // 일반/정예 몬스터 생성
        if (isElite)
            spawned = enemySpawner.SpawnEliteEnemy();
        else
            spawned = enemySpawner.SpawnNormalEnemy();

        // 몬스터 생성 실패
        if (!spawned)
        {
            Debug.LogError(
                "[Battle] 몬스터 생성 실패"
            );

            // 전투 화면 종료
            battleRoot.SetActive(false);

            // 전투 배경 정리
            HideBattleEnvironment();

            // 탐험 카메라 복구
            RestoreExplorationCamera();

            // 탐험 UI 복구
            RestoreExplorationUI();

            IsBattling = false;

            return;
        }

        // 기존 전투 시스템 시작
        if (isElite)
            battleManager.StartEliteBattle();
        else
            battleManager.StartNormalBattle();
    }


    // ==========================================
    // 전투 결과 확정
    // ==========================================

    // Wire the result panel's Confirm/Continue
    // button to this method.
    public void ConfirmBattleResult()
    {
        if (!IsBattling || battleManager == null)
            return;

        // 전투가 실제로 종료되었는지 확인
        if (battleManager.currentState != BattleState.Finished ||
            !battleManager.LastBattleVictory.HasValue)
        {
            return;
        }

        bool victory = battleManager.LastBattleVictory.Value;


        // 1. 전투 결과 스탯 저장
        if (adventurePlayerStats != null &&
            battleManager.player != null)
        {
            adventurePlayerStats.CaptureFromBattleUnit(
                battleManager.player
            );

            // 승리 시 최대 ST의 20% 회복
            if (victory && adventurePlayerStats.IsInitialized)
            {
                adventurePlayerStats.RecoverST(
                    adventurePlayerStats.MaxST * 0.2f
                );
            }
        }
        else
        {
            Debug.LogWarning(
                "[Battle] AdventurePlayerStats 또는 BattleUnit 미연결"
            );
        }


        // 2. 전투 종료 상태 설정
        IsBattling = false;


        // 3. 전투 화면 종료
        if (battleRoot != null)
            battleRoot.SetActive(false);


        // 4. 탐험 카메라 복구
        RestoreExplorationCamera();


        // 5. 탐험 UI 복구
        RestoreExplorationUI();


        // 6. 탐험 매니저에 결과 전달
        Debug.Log(
            victory
                ? "[Adventure] Battle won"
                : "[Adventure] Battle lost"
        );

        BattleFinished?.Invoke(victory);
    }


    // ==========================================
    // 탐험 카메라 복구
    // ==========================================

    private void RestoreExplorationCamera()
    {
        if (explorationCamera == null)
            return;

        explorationCamera.enabled = true;

        var listener =
            explorationCamera.GetComponent<AudioListener>();

        if (listener != null)
            listener.enabled = true;
    }


    // ==========================================
    // 탐험 UI 복구
    // ==========================================

    private void RestoreExplorationUI()
    {
        if (floorPanel != null)
            floorPanel.SetActive(true);

        if (adventurePlayerStatusPanel != null)
            adventurePlayerStatusPanel.SetActive(true);
    }
}
