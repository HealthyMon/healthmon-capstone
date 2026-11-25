using System;
using Healthmon.Common;
using UnityEngine;

// 이벤트/아이템에서 변경할 수 있는 탐험 능력치
public enum AdventureStatType
{
    HP, MaxHP, ST, MaxST, ATK, DEF, RES, SPD, LUK
}

public class AdventurePlayerStats : MonoBehaviour
{
    // Retain serialized fields/GUIDs used by the team's scenes. Growth replaces their sample values.
    [SerializeField] private BattleUnit initialPlayer;
    [SerializeField] private int maxHP, currentHP;
    [SerializeField] private float maxST, currentST;
    [SerializeField] private int ATK, DEF, RES, SPD, LUK;
    private bool initialized;
    private PetCombatStats growthStats;
    private string growthScope;
    private float nextRefresh;

    public int CurrentHP => currentHP;
    public int MaxHP => maxHP;
    public float CurrentST => currentST;
    public float MaxST => maxST;
    public bool IsInitialized => initialized;
    public bool IsAlive => currentHP > 0;
    public PetCombatStats GrowthStats => growthStats;
    public event Action OnStatsChanged;

    private void Awake() { InitializeExploration(); }

    private void Update()
    {
        if (Time.unscaledTime < nextRefresh) return;
        nextRefresh = Time.unscaledTime + .5f;
        var battle = FindAnyObjectByType<BattleController>(FindObjectsInactive.Include);
        // Keep the current fight's snapshot stable; changes take effect before the next fight.
        if (battle == null || !battle.IsBattling) RefreshGrowthStats();
    }

    public void InitializeExploration()
    {
        initialized = false;
        RefreshGrowthStats();
    }

    public bool RefreshGrowthStats()
    {
        if (!PetCombatStatsSource.TryGetCurrent(out var stats, out var scope)) return false;
        ApplyGrowthStats(stats, scope);
        return true;
    }

    // Also used by native Unity verification to check transfer/resource lifecycle independently of I/O.
    public void ApplyGrowthStats(PetCombatStats stats, string scope)
    {
        if (initialized && growthScope == scope && growthStats.Equals(stats)) return;
        bool samePet = initialized && growthScope == scope;
        var previous = samePet ? CreateSnapshot() : null;
        growthStats = stats;
        growthScope = scope;
        ApplyExplorationState(previous);
        initialized = true;
        OnStatsChanged?.Invoke();
    }

    private void ApplyExplorationState(AdventureStatsData saved)
    {
        // Old checkpoints stored only totals. Their resource ratios still describe the run.
        var bonus = saved?.bonuses;
        maxHP = Mathf.Max(1, growthStats.MaxHP + (bonus?.maxHP ?? 0));
        maxST = Mathf.Max(.1f, growthStats.MaxST + (bonus?.maxST ?? 0));
        ATK = Mathf.Max(0, growthStats.ATK + (bonus?.ATK ?? 0));
        DEF = Mathf.Max(0, growthStats.DEF + (bonus?.DEF ?? 0));
        RES = Mathf.Max(0, growthStats.RES + (bonus?.RES ?? 0));
        SPD = Mathf.Max(1, growthStats.SPD + (bonus?.SPD ?? 0));
        LUK = Mathf.Max(0, growthStats.LUK + (bonus?.LUK ?? 0));

        float hpRatio = saved == null ? 1 : (float)saved.currentHP / saved.maxHP;
        float stRatio = saved == null ? .5f : saved.currentST / saved.maxST;
        int minimumHP = saved != null && saved.currentHP > 0 ? 1 : 0;
        currentHP = Mathf.Clamp(Mathf.RoundToInt(maxHP * hpRatio), minimumHP, maxHP);
        currentST = Mathf.Clamp(maxST * stRatio, 0, maxST);
    }

    public bool ApplyToBattleUnit(BattleUnit unit)
    {
        if (unit == null || !RefreshGrowthStats()) return false;
        CopyToBattleUnit(unit);
        return true;
    }

    public void CopyToBattleUnit(BattleUnit unit)
    {
        if (!initialized || unit == null) return;
        unit.maxHP = maxHP; unit.maxST = maxST;
        unit.ATK = ATK; unit.DEF = DEF; unit.RES = RES; unit.SPD = SPD; unit.LUK = LUK;
        unit.actionSpeedMultiplier = growthStats.ActionSpeedMultiplier;
        unit.staminaRecoveryRate = BattleUnit.BaseStaminaRecoveryRate * growthStats.StaminaRecoveryMultiplier;
        unit.currentHP = Mathf.Clamp(currentHP, 0, maxHP);
        unit.currentST = Mathf.Clamp(currentST, 0, maxST);
        unit.actionGauge = 0;
    }

    public void CaptureFromBattleUnit(BattleUnit unit)
    {
        if (!initialized || unit == null) return;
        // Only resources persist between fights; never turn a battle modifier into permanent growth.
        currentHP = Mathf.Clamp(unit.currentHP, 0, maxHP);
        currentST = Mathf.Clamp(unit.currentST, 0, maxST);
        OnStatsChanged?.Invoke();
    }

    public void Heal(int amount)
    {
        if (!initialized) return;
        currentHP = Mathf.Clamp(currentHP + Mathf.Max(0, amount), 0, maxHP);
        OnStatsChanged?.Invoke();
    }

    public void RecoverST(float amount)
    {
        if (!initialized) return;
        currentST = Mathf.Clamp(currentST + Mathf.Max(0, amount), 0, maxST);
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
            ATK = ATK, DEF = DEF, RES = RES, SPD = SPD, LUK = LUK,
            growthScope = growthScope,
            bonuses = new AdventureStatBonuses
            {
                maxHP = maxHP - growthStats.MaxHP, maxST = maxST - growthStats.MaxST,
                ATK = ATK - growthStats.ATK, DEF = DEF - growthStats.DEF, RES = RES - growthStats.RES,
                SPD = SPD - growthStats.SPD, LUK = LUK - growthStats.LUK
            }
        };
    }

    public bool RestoreSnapshot(AdventureStatsData data)
    {
        if (!initialized || data == null || !data.IsValid()) return false;
        if (!string.IsNullOrEmpty(data.growthScope) && data.growthScope != growthScope) return false;
        ApplyExplorationState(data);
        OnStatsChanged?.Invoke();
        return true;
    }
}
