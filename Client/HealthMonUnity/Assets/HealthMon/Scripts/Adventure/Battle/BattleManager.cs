
using System.Collections;
using UnityEngine;

public enum BattleMode
{
    Normal,
    Elite
}

public class BattleManager : MonoBehaviour
{
    [Header("전투 유닛")]
    public BattleUnit player;
    public BattleUnit enemy;

    [Header("몬스터 AI")]
    public EnemyAI enemyAI;

    [Header("UI")]
    public BattleUI battleUI;

    [Header("행동 ST 비용")]
    public float attackCost = 2f;
    public float skillCost = 5f;
    public float itemCost = .5f;

    [Header("행동 효과")]
    public float skillDamageMultiplier = 2f;
    public int itemHealAmount = 10;

    [Header("전투 상태")]
    public BattleState currentState = BattleState.Ready;
    [SerializeField] private AdventurePlayerStats adventurePlayerStats;

    [Header("전투 연출")]
    [SerializeField]
    private BattleVisualController battleVisual;

    [Header("전투 시각 요소")]
    [SerializeField] private GameObject playerVisual;

    [Header("피해량 UI")]
    [SerializeField] private DamagePopupController damagePopup;

    [Header("Elite Battle")]
    [SerializeField] private EliteMoveController eliteMove;
    [SerializeField] private EliteGridManager eliteGrid;
    [SerializeField] private GameObject eliteArena;
    [SerializeField] private GameObject normalBattleCamera;
    [SerializeField] private GameObject eliteBattleCamera;

    [Header("Elite Enemy AI")]
    [SerializeField] private EliteEnemyAI eliteEnemyAI;

    [Header("Elite Attack Settings")]
    [SerializeField] private float eliteSpecialMultiplier = 1.5f;

    [Header("Controller")]
    [SerializeField] private EliteCameraController eliteCameraController;
    [SerializeField] private BattleController battleController;

    private BattleMode battleMode = BattleMode.Normal;

    // Exploration integration: result remains visible until confirmed.
    public bool? LastBattleVictory { get; private set; }

    public bool IsEliteBattle => battleMode == BattleMode.Elite;

    // 탐험에서 전투가 시작될 때만 UI를 열도록 Start() 자동 선택 화면 제거.

    private void Update()
    {
        if (currentState != BattleState.Running) return;

        float deltaTime = Time.deltaTime;

        player.UpdateBattleTime(deltaTime);
        enemy.UpdateBattleTime(deltaTime);

        // 두 캐릭터가 동시에 행동 가능하면 SPD 우선
        if (player.IsActionReady && enemy.IsActionReady)
        {
            if (player.SPD >= enemy.SPD)
                StartPlayerTurn();
            else
                ExecuteCurrentEnemyTurn();
        }
        else if (player.IsActionReady)
        {
            StartPlayerTurn();
        }
        else if (enemy.IsActionReady)
        {
            ExecuteCurrentEnemyTurn();
        }

        battleUI.RefreshUI();
    }

    private void InitializePlayerForBattle()
    {
        if (adventurePlayerStats != null &&
            adventurePlayerStats.IsInitialized)
        {
            adventurePlayerStats.ApplyToBattleUnit(player);
        }
        else
        {
            // 기존 단독 전투 테스트 호환
            player.Initialize();
        }
    }
    public void StartNormalBattle()
    {
        LastBattleVictory = null;

        battleMode = BattleMode.Normal;

        eliteArena.SetActive(false);
        normalBattleCamera.SetActive(true);
        eliteBattleCamera.SetActive(false);

        InitializePlayerForBattle();
        enemy.Initialize();
        enemyAI.Initialize();

        SetPlayerVisualVisible(false);
        if (battleVisual != null)
            battleVisual.ResetVisuals();

        currentState = BattleState.Running;

        battleUI.SetBattleModeUI(false);
        battleUI.ShowBattlePanel();
        battleUI.AddLog("일반 전투가 시작되었습니다.");
        battleUI.RefreshUI();
    }
    public void StartEliteBattle()
    {
        LastBattleVictory = null;

        battleMode = BattleMode.Elite;

        InitializePlayerForBattle();
        enemy.Initialize();
        enemyAI.Initialize();
        eliteEnemyAI.Initialize();
        eliteGrid.ClearWarnings();

        SetPlayerVisualVisible(true);
        // 이전 전투의 시각 상태 초기화
        if (battleVisual != null)
            battleVisual.ResetVisuals();

        eliteArena.SetActive(true);
        normalBattleCamera.SetActive(false);
        eliteBattleCamera.SetActive(true);

        eliteMove.ResetMovement();

        currentState = BattleState.Running;

        battleUI.SetBattleModeUI(true);
        battleUI.ShowBattlePanel();
        battleUI.AddLog("정예 전투가 시작되었습니다.");
        battleUI.RefreshUI();

        eliteBattleCamera.SetActive(true);

        if (eliteCameraController != null)
        {
            eliteCameraController.SetupCamera();
        }
    }

    private void StartPlayerTurn()
    {
        currentState = BattleState.PlayerSelecting;

        battleUI.SetActionButtons(true);
        battleUI.AddLog("헬스몬의 행동 차례입니다.");
        battleUI.RefreshUI();
    }
    public void ExecutePlayerAction(BattleActionType action)
    {
        if (currentState != BattleState.PlayerSelecting)
            return;

        bool success = false;

        switch (action)
        {
            case BattleActionType.Attack:
                success = PlayerAttack();
                break;

            case BattleActionType.Skill:
                success = PlayerSkill();
                break;

            case BattleActionType.Item:
                success = PlayerItem();
                break;

            case BattleActionType.Wait:
                success = PlayerWait();
                break;
        }

        if (!success)
        {
            battleUI.AddLog("행동을 실행할 수 없습니다.");
            battleUI.RefreshUI();
            return;
        }

        player.FinishAction();

        if (CheckBattleEnd())
            return;

        currentState = BattleState.Running;
        battleUI.SetActionButtons(false);
        battleUI.RefreshUI();
    }
    private bool PlayerAttack()
    {
        if (!player.SpendST(attackCost))
            return false;

        int damage = CalculatePhysicalDamage(
            player.ATK,
            enemy.DEF
        );

        enemy.TakeDamage(damage);

        if (battleVisual != null)
            battleVisual.PlayEnemyHit(false);

        if (damagePopup != null)
            damagePopup.ShowEnemyDamage(damage);

        battleUI.AddLog(
            $"헬스몬의 기본 공격! {damage} 피해"
        );

        return true;
    }
    private bool PlayerSkill()
    {
        if (!player.SpendST(skillCost))
            return false;

        int skillAttack = Mathf.RoundToInt(
            player.ATK * skillDamageMultiplier
        );

        int damage = CalculatePhysicalDamage(
            skillAttack,
            enemy.DEF
        );

        enemy.TakeDamage(damage);

        if (battleVisual != null)
            battleVisual.PlayEnemyHit(true);

        if (damagePopup != null)
            damagePopup.ShowEnemyDamage(damage);

        battleUI.AddLog(
            $"헬스몬의 강력한 스킬! {damage} 피해"
        );

        return true;
    }
    private bool PlayerItem()
    {
        if (!player.SpendST(itemCost))
            return false;

        player.Heal(itemHealAmount);

        battleUI.AddLog(
            $"회복 아이템 사용! HP {itemHealAmount} 회복"
        );

        return true;
    }
    private bool PlayerWait()
    {
        player.RecoverST(player.waitRecoveryBonus);

        battleUI.AddLog(
            "헬스몬이 대기하여 ST를 회복했습니다."
        );

        return true;
    }


    private void ExecuteCurrentEnemyTurn()
    {
        if (battleMode == BattleMode.Elite)
        {
            ExecuteEliteEnemyTurn();
        }
        else
        {
            ExecuteEnemyAction();
        }
    }
    private void ExecuteEnemyAction()
    {
        currentState = BattleState.ResolvingAction;

        int damage = 0;

        switch (enemyAI.nextAction)
        {
            case EnemyActionType.PhysicalAttack:

                damage = CalculatePhysicalDamage(
                    enemy.ATK,
                    player.DEF
                );

                battleUI.AddLog(
                    $"몬스터의 기본 공격! {damage} 피해"
                );
                break;

            case EnemyActionType.MagicAttack:

                damage = CalculateMagicDamage(
                    enemy.ATK,
                    player.RES
                );

                battleUI.AddLog(
                    $"몬스터의 마법 공격! {damage} 피해"
                );
                break;
        }

        player.TakeDamage(damage);

        if (battleVisual != null)
            battleVisual.PlayPlayerHit();

        if (damagePopup != null)
            damagePopup.ShowPlayerDamage(damage);

        enemy.FinishAction();

        if (CheckBattleEnd())
            return;

        // 다음 쿨타임 동안 사용할 행동 미리 결정
        enemyAI.SelectNextAction();

        currentState = BattleState.Running;
        battleUI.RefreshUI();
    }
    private void ExecuteEliteEnemyTurn()
    {
        currentState = BattleState.ResolvingAction;

        // 특수 공격을 이미 준비했다면 이번 보스 턴에 실행
        if (eliteEnemyAI.phase == EliteAttackPhase.Preparing)
        {
            ExecutePreparedEliteAttack();

            eliteGrid.ClearWarnings();
            eliteEnemyAI.FinishPreparedAttack();
        }
        else
        {
            switch (eliteEnemyAI.nextAttack)
            {
                case EliteAttackType.Normal:
                    ExecuteEliteNormalAttack();
                    eliteEnemyAI.SelectNextAttack();
                    break;

                case EliteAttackType.Horizontal:
                case EliteAttackType.Vertical:
                    PrepareEliteSpecialAttack();
                    break;
            }
        }

        // 일반 공격 / 특수 준비 / 특수 실행 모두
        // 보스의 행동 한 번을 소비
        enemy.FinishAction();

        if (CheckBattleEnd())
            return;

        currentState = BattleState.Running;
        battleUI.RefreshUI();
    }
    private void ExecuteEliteNormalAttack()
    {
        int damage = CalculatePhysicalDamage(
            enemy.ATK,
            player.DEF
        );

        player.TakeDamage(damage);

        if (damagePopup != null)
            damagePopup.ShowPlayerDamage(damage);

        battleUI.AddLog(
            $"정예 몬스터의 일반 공격! {damage} 피해"
        );
    }
    private void PrepareEliteSpecialAttack()
    {
        eliteEnemyAI.PrepareSpecialAttack(eliteGrid.PlayerCell);

        int index = eliteEnemyAI.targetIndex;

        switch (eliteEnemyAI.nextAttack)
        {
            case EliteAttackType.Horizontal:
                eliteGrid.ShowRowWarning(index);

                battleUI.AddLog(
                    $"정예 몬스터가 가로 " +
                    $"{EliteEnemyAI.GetRowName(index)} 3칸 공격을 준비한다!"
                );
                break;

            case EliteAttackType.Vertical:
                eliteGrid.ShowColumnWarning(index);

                battleUI.AddLog(
                    $"정예 몬스터가 세로 " +
                    $"{EliteEnemyAI.GetColumnName(index)} 3칸 공격을 준비한다!"
                );
                break;
        }
    }
    private void ExecutePreparedEliteAttack()
    {
        Vector2Int playerCell = eliteGrid.PlayerCell;

        bool isHit = eliteGrid.IsCellDangerous(playerCell);

        if (!isHit)
        {
            battleUI.AddLog(
                "정예 몬스터의 특수 공격! 헬스몬이 회피했다!"
            );

            return;
        }

        int specialAttack = Mathf.RoundToInt(
            enemy.ATK * eliteSpecialMultiplier
        );

        int damage = CalculatePhysicalDamage(
            specialAttack,
            player.DEF
        );

        player.TakeDamage(damage);

        if (damagePopup != null)
            damagePopup.ShowPlayerDamage(damage);

        string attackName =
            eliteEnemyAI.nextAttack == EliteAttackType.Horizontal
            ? "가로 특수 공격"
            : "세로 특수 공격";

        battleUI.AddLog(
            $"정예 몬스터의 {attackName}! {damage} 피해"
        );
    }


    private int CalculatePhysicalDamage(int attack, int defense)
    {
        return Mathf.Max(1, attack - defense);
    }
    private int CalculateMagicDamage(int attack, int resistance)
    {
        return Mathf.Max(1, attack - resistance);
    }

    private bool CheckBattleEnd()
    {
        if (!enemy.IsAlive)
        {
            EndBattle(true);
            return true;
        }

        if (!player.IsAlive)
        {
            EndBattle(false);
            return true;
        }

        return false;
    }

    private void EndBattle(bool playerWon)
    {
        LastBattleVictory = playerWon;
        currentState = BattleState.Finished;

        StartCoroutine(EndBattleRoutine(playerWon));
    }
    private IEnumerator EndBattleRoutine(bool playerWon)
    {
        // 마지막 공격 연출을 보여줄 시간
        yield return new WaitForSeconds(0.6f);

        battleUI.RefreshUI();
        if (playerWon && battleVisual != null)
            battleVisual.HideEnemy();

        yield return new WaitForSeconds(0.4f);

        ReturnToMenu();
    }

    public void ReturnToMenu()
    {
        currentState = BattleState.Finished;
        battleController.ConfirmBattleResult();
    }

    private void SetPlayerVisualVisible(bool visible)
    {
        if (playerVisual != null)
        {
            playerVisual.SetActive(visible);
        }
    }

    public bool CanSelectEliteMove()
    {
        return battleMode == BattleMode.Elite
            && currentState == BattleState.PlayerSelecting
            && player.IsAlive;
    }

    public bool CanAffordEliteMove(float cost)
    {
        return CanSelectEliteMove()
            && player.CanSpendST(cost);
    }

    public bool CompleteEliteMove(float cost)
    {
        if (!CanAffordEliteMove(cost))
            return false;

        if (!player.SpendST(cost))
            return false;

        player.FinishAction();

        currentState = BattleState.Running;

        battleUI.SetActionButtons(false);
        battleUI.AddLog($"헬스몬이 이동했다. ST -{cost:0.#}");
        battleUI.RefreshUI();

        return true;
    }
    public string GetEnemyNextActionName()
    {
        if (battleMode == BattleMode.Elite)
            return eliteEnemyAI.GetNextActionName();

        return enemyAI.GetNextActionName();
    }

}
