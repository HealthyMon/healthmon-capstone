
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class BattleUI : MonoBehaviour
{
    [Header("참조")]
    public BattleManager battleManager;

    [Header("패널")]
    public GameObject selectionPanel;
    public GameObject battlePanel;
    public GameObject resultPanel;

    [Header("플레이어 UI")]
    public Slider playerHPBar;
    public Slider playerSTBar;
    public Slider playerGaugeBar;

    [Header("몬스터 UI")]
    public Slider enemyHPBar;
    public Slider enemyGaugeBar;
    public TMP_Text enemyNextActionText;

    [Header("행동 버튼")]
    public Button attackButton;
    public Button skillButton;
    public Button itemButton;
    public Button waitButton;
    public Button moveButton;

    [Header("텍스트")]
    public TMP_Text battleLogText;
    public TMP_Text resultText;

    [Header("상태 텍스트")]
    public TMP_Text playerHPText;
    public TMP_Text playerSTText;
    public TMP_Text playerATBText;
    public TMP_Text enemyHPText;

    private void Awake()
    {
        attackButton.onClick.AddListener(
            () => battleManager.ExecutePlayerAction(
                BattleActionType.Attack
            )
        );

        skillButton.onClick.AddListener(
            () => battleManager.ExecutePlayerAction(
                BattleActionType.Skill
            )
        );

        itemButton.onClick.AddListener(
            () => battleManager.ExecutePlayerAction(
                BattleActionType.Item
            )
        );

        waitButton.onClick.AddListener(
            () => battleManager.ExecutePlayerAction(
                BattleActionType.Wait
            )
        );
    }

    public void ShowSelectionPanel()
    {
        selectionPanel.SetActive(true);
        battlePanel.SetActive(false);
        resultPanel.SetActive(false);
    }

    public void ShowBattlePanel()
    {
        selectionPanel.SetActive(false);
        battlePanel.SetActive(true);
        resultPanel.SetActive(false);

        battleLogText.text = "";

        SetActionButtons(false);
    }

    public void ShowResultPanel(bool playerWon)
    {
        selectionPanel.SetActive(false);
        battlePanel.SetActive(false);
        resultPanel.SetActive(true);

        resultText.text = playerWon
            ? "전투 승리!"
            : "전투 패배!";
    }

    public void SetActionButtons(bool enabled)
    {
        attackButton.interactable = enabled;
        skillButton.interactable = enabled;
        itemButton.interactable = enabled;
        waitButton.interactable = enabled;
        moveButton.interactable = enabled && battleManager.IsEliteBattle;
    }

    public void RefreshUI()
    {
        BattleUnit player = battleManager.player;
        BattleUnit enemy = battleManager.enemy;

        playerHPBar.maxValue = player.maxHP;
        playerHPBar.value = player.currentHP;

        playerSTBar.maxValue = player.maxST;
        playerSTBar.value = player.currentST;

        playerGaugeBar.maxValue = player.actionGaugeMax;
        playerGaugeBar.value = player.actionGauge;

        enemyHPBar.maxValue = enemy.maxHP;
        enemyHPBar.value = enemy.currentHP;

        enemyGaugeBar.maxValue = enemy.actionGaugeMax;
        enemyGaugeBar.value = enemy.actionGauge;

        enemyNextActionText.text = "Next Action: " + battleManager.GetEnemyNextActionName();

        if (battleManager.currentState == BattleState.PlayerSelecting)
        {
            attackButton.interactable =
                player.CanSpendST(battleManager.attackCost);

            skillButton.interactable =
                player.CanSpendST(battleManager.skillCost);

            itemButton.interactable =
                player.CanSpendST(battleManager.itemCost);

            waitButton.interactable = true;
        }

        playerHPText.text = $"{player.currentHP} / {player.maxHP}";

        playerSTText.text = $"ST {player.currentST:0} / {player.maxST:0}";

        playerATBText.text = $"ATB {player.actionGauge / player.actionGaugeMax * 100f:0}%";

        enemyHPText.text = $"{enemy.currentHP} / {enemy.maxHP}";
    }

    public void AddLog(string message)
    {
        battleLogText.text = message;
    }

    public void SetBattleModeUI(bool isElite)
    {
        moveButton.gameObject.SetActive(isElite);
        itemButton.gameObject.SetActive(!isElite);
    }
}
