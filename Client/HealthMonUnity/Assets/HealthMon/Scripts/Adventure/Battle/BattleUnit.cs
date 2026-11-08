
using UnityEngine;

public class BattleUnit : MonoBehaviour
{
    [Header("기본 정보")]
    public string unitName = "Unit";

    [Header("전투 스탯")]
    public int maxHP = 100;
    public float maxST = 20f;

    public int ATK = 10;
    public int DEF = 5;
    public int RES = 5;
    public int SPD = 5;
    public int LUK = 5;

    [Header("스태미나")]
    public float staminaRecoveryRate = .025f;
    public float waitRecoveryBonus = .05f;

    [Header("행동 게이지")]
    public float actionGauge = 0f;
    public float actionGaugeMax = 100f;

    [Header("현재 상태")]
    public int currentHP;
    public float currentST;

    public bool IsAlive => currentHP > 0;

    public bool IsActionReady => actionGauge >= actionGaugeMax;

    public void Initialize()
    {
        currentHP = maxHP;
        currentST = maxST * .5f;
        actionGauge = 0f;
    }

    public void UpdateBattleTime(float deltaTime)
    {
        if (!IsAlive) return;

        // SPD에 따른 행동 게이지 충전
        float gaugeSpeed = 20f + SPD * 3f;

        actionGauge = Mathf.Min(actionGaugeMax, actionGauge + gaugeSpeed * deltaTime);

        // 시간에 따른 스태미나 회복
        RecoverST(staminaRecoveryRate * deltaTime);
    }

    public void RecoverST(float amount)
    {
        currentST = Mathf.Min(maxST, currentST + amount * .5f);
    }

    public bool CanSpendST(float amount)
    {
        return currentST >= amount;
    }
    public bool SpendST(float amount)
    {
        if (!CanSpendST(amount)) return false;

        currentST -= amount;
        return true;
    }

    public void TakeDamage(int damage)
    {
        currentHP = Mathf.Max(0, currentHP - Mathf.Max(0, damage));
    }

    public void Heal(int amount)
    {
        currentHP = Mathf.Min(maxHP, currentHP + Mathf.Max(0, amount));
    }

    public void FinishAction()
    {
        actionGauge = 0f;
    }
}
