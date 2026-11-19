
using System;
using UnityEngine;

// 이벤트/아이템에서 변경할 수 있는 탐험 능력치
public enum AdventureStatType
{
    HP, MaxHP, ST, MaxST, ATK, DEF, RES, SPD, LUK
}

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

        // 기본 최대 체력과 스태미나
        maxHP = initialPlayer.maxHP;
        maxST = initialPlayer.maxST;

        // ATK, DEF, RES, SPD, LUK는
        // AdventurePlayerStats Inspector 값을 그대로 사용

        currentHP = maxHP;
        currentST = maxST * 0.5f;

        initialized = true;

        OnStatsChanged?.Invoke();

        Debug.Log(
            $"[AdventureStats] 탐험 초기화: " +
            $"ATK={ATK}, DEF={DEF}, RES={RES}, " +
            $"SPD={SPD}, LUK={LUK}"
        );
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

    // 현재 탐험에만 적용되는 능력치 변경. 실제 반영량을 반환한다.
    // 정수 능력치(HP, MaxHP, ATK 등)의 amount는 반올림한다.
    public float ModifyStat(AdventureStatType stat, float amount)
    {
        if (!initialized || float.IsNaN(amount) || float.IsInfinity(amount))
            return 0f;

        float before = GetStatValue(stat);
        int delta = Mathf.RoundToInt(amount);

        switch (stat)
        {
            case AdventureStatType.HP:
                currentHP = Mathf.Clamp(currentHP + delta, 0, maxHP);
                break;
            case AdventureStatType.MaxHP:
                maxHP = Mathf.Max(1, maxHP + delta);
                currentHP = Mathf.Min(currentHP, maxHP);
                break;
            case AdventureStatType.ST:
                currentST = Mathf.Clamp(currentST + amount, 0f, maxST);
                break;
            case AdventureStatType.MaxST:
                maxST = Mathf.Max(0.1f, maxST + amount);
                currentST = Mathf.Min(currentST, maxST);
                break;
            case AdventureStatType.ATK:
                ATK = Mathf.Max(0, ATK + delta);
                break;
            case AdventureStatType.DEF:
                DEF = Mathf.Max(0, DEF + delta);
                break;
            case AdventureStatType.RES:
                RES = Mathf.Max(0, RES + delta);
                break;
            case AdventureStatType.SPD:
                SPD = Mathf.Max(1, SPD + delta);
                break;
            case AdventureStatType.LUK:
                LUK = Mathf.Max(0, LUK + delta);
                break;
            default:
                return 0f;
        }

        float applied = GetStatValue(stat) - before;
        if (!Mathf.Approximately(applied, 0f))
        {
            OnStatsChanged?.Invoke();
            Debug.Log($"[AdventureStats] {stat}: {before:0.##} -> {GetStatValue(stat):0.##}");
        }
        return applied;
    }

    public float GetStatValue(AdventureStatType stat)
    {
        switch (stat)
        {
            case AdventureStatType.HP: return currentHP;
            case AdventureStatType.MaxHP: return maxHP;
            case AdventureStatType.ST: return currentST;
            case AdventureStatType.MaxST: return maxST;
            case AdventureStatType.ATK: return ATK;
            case AdventureStatType.DEF: return DEF;
            case AdventureStatType.RES: return RES;
            case AdventureStatType.SPD: return SPD;
            case AdventureStatType.LUK: return LUK;
            default: return 0f;
        }
    }

    public AdventureStatsData CreateSnapshot()
    {
        return new AdventureStatsData
        {
            maxHP = maxHP, currentHP = currentHP,
            maxST = maxST, currentST = currentST,
            ATK = ATK, DEF = DEF, RES = RES, SPD = SPD, LUK = LUK
        };
    }

    public bool RestoreSnapshot(AdventureStatsData data)
    {
        if (data == null || !data.IsValid()) return false;

        maxHP = data.maxHP;
        currentHP = data.currentHP;
        maxST = data.maxST;
        currentST = data.currentST;
        ATK = data.ATK;
        DEF = data.DEF;
        RES = data.RES;
        SPD = data.SPD;
        LUK = data.LUK;
        initialized = true;
        OnStatsChanged?.Invoke();
        return true;
    }
}
