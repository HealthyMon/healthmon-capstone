
using System;
using UnityEngine;

public class AdventurePlayerStats : MonoBehaviour
{
    [Header("Initial Player")]
    [SerializeField] private BattleUnit initialPlayer;

    [Header("Current Stats")]
    [SerializeField] private int maxHP;
    [SerializeField] private int currentHP;

    [SerializeField] private float maxST;
    [SerializeField] private float currentST;

    [Header("Battle Stats")]
    [SerializeField] private int ATK;
    [SerializeField] private int DEF;
    [SerializeField] private int RES;
    [SerializeField] private int SPD;
    [SerializeField] private int LUK;

    private bool initialized;

    public int CurrentHP => currentHP;
    public int MaxHP => maxHP;
    public float CurrentST => currentST;
    public float MaxST => maxST;

    public bool IsInitialized => initialized;
    public bool IsAlive => currentHP > 0;

    public event Action OnStatsChanged;

    private void Awake()
    {
        if (initialPlayer != null)
            InitializeExploration();
    }

    // 새로운 탐험 시작 시 한 번만 실행
    public void InitializeExploration()
    {
        if (initialPlayer == null)
        {
            Debug.LogError(
                "[AdventureStats] Initial Player 미연결"
            );
            return;
        }

        maxHP = initialPlayer.maxHP;
        maxST = initialPlayer.maxST;

        ATK = initialPlayer.ATK;
        DEF = initialPlayer.DEF;
        RES = initialPlayer.RES;
        SPD = initialPlayer.SPD;
        LUK = initialPlayer.LUK;

        currentHP = maxHP;
        currentST = maxST * 0.5f;

        initialized = true;

        OnStatsChanged?.Invoke();

        Debug.Log("[AdventureStats] 탐험 스탯 초기화");
    }

    // 탐험 스탯을 전투에 전달
    public void ApplyToBattleUnit(BattleUnit unit)
    {
        if (!initialized || unit == null)
            return;

        unit.maxHP = maxHP;
        unit.maxST = maxST;

        unit.ATK = ATK;
        unit.DEF = DEF;
        unit.RES = RES;
        unit.SPD = SPD;
        unit.LUK = LUK;

        unit.currentHP = Mathf.Clamp(
            currentHP, 0, maxHP
        );

        unit.currentST = Mathf.Clamp(
            currentST, 0f, maxST
        );

        // 행동 게이지는 전투마다 새로 시작
        unit.actionGauge = 0f;
    }

    // 전투 결과를 탐험에 저장
    public void CaptureFromBattleUnit(BattleUnit unit)
    {
        if (!initialized || unit == null)
            return;

        maxHP = unit.maxHP;
        maxST = unit.maxST;

        ATK = unit.ATK;
        DEF = unit.DEF;
        RES = unit.RES;
        SPD = unit.SPD;
        LUK = unit.LUK;

        currentHP = Mathf.Clamp(
            unit.currentHP, 0, maxHP
        );

        currentST = Mathf.Clamp(
            unit.currentST, 0f, maxST
        );

        OnStatsChanged?.Invoke();

        Debug.Log(
            $"[AdventureStats] HP {currentHP}/{maxHP}, " +
            $"ST {currentST:F1}/{maxST:F1}"
        );
    }

    // 탐험 이벤트에서 체력 회복
    public void Heal(int amount)
    {
        if (!initialized) return;

        currentHP = Mathf.Clamp(
            currentHP + Mathf.Max(0, amount),
            0,
            maxHP
        );

        OnStatsChanged?.Invoke();
    }

    // 탐험 이벤트에서 스태미나 회복
    public void RecoverST(float amount)
    {
        if (!initialized) return;

        currentST = Mathf.Clamp(
            currentST + Mathf.Max(0f, amount),
            0f,
            maxST
        );

        OnStatsChanged?.Invoke();
    }
}
