using System;
using System.Globalization;
using Healthmon.Beta;

/// <summary>One projection of verified growth scores, shared by status and both battle modes.
/// Balance version 1. See Docs/COMBAT_STATS.md; these are game rules, not health advice.</summary>
public readonly struct PetCombatStats
{
    public readonly int Level, MaxHP, ATK, DEF, RES, SPD, LUK;
    public readonly float MaxST, ActionSpeedMultiplier, StaminaRecoveryMultiplier;
    public readonly string BodyType;

    private PetCombatStats(int level, int hp, float st, int atk, int def, int res, int spd, int luk,
        float tempo, float recovery, string body)
    {
        Level = level; MaxHP = hp; MaxST = st; ATK = atk; DEF = def; RES = res; SPD = spd; LUK = luk;
        ActionSpeedMultiplier = tempo; StaminaRecoveryMultiplier = recovery; BodyType = body;
    }

    public static PetCombatStats FromState(PetState state)
    {
        if (state == null || !state.IsValidCommonState(state.pet_id))
            throw new ArgumentException("A verified common pet state is required.");
        return Calculate(state.level, state.upper_body, state.lower_body, state.nutrition,
            state.energy_balance, state.activity, state.affinity, state.initiative);
    }

    public static PetCombatStats Calculate(int level, float upper, float lower, float nutrition,
        float energy, float activity, float affinity, float initiative)
    {
        if (level < 1 || level > 30) throw new ArgumentOutOfRangeException(nameof(level));
        foreach (float value in new[] { upper, lower, nutrition, activity, affinity, initiative })
            if (!Bounded(value, 0, 100)) throw new ArgumentOutOfRangeException("growth score");
        if (!Bounded(energy, -100, 100)) throw new ArgumentOutOfRangeException(nameof(energy));

        float growth = level - 1;
        float hp = 100 + 8 * growth + .6f * (nutrition - 50);
        float st = 20 + .3f * growth + .12f * (activity - 50);
        float atk = 10 + 2 * growth + .16f * (upper - 50);
        float def = 5 + growth + .10f * (lower - 50);
        float res = 5 + growth + .10f * (nutrition - 50);
        float spd = 5 + .05f * growth + .06f * (lower - 50) + .04f * (activity - 50);
        float luk = 5 + .02f * growth + .06f * (initiative - 50) + .02f * (affinity - 50);
        float tempo = 1, recovery = nutrition >= 60 ? 1.15f : nutrition < 40 ? .75f : 1;
        string body = ClassifyBody(upper, lower, nutrition, energy);
        switch (body)
        {
            case "adipose": hp *= 1.20f; def *= 1.10f; tempo = .50f; break;
            case "rounded_general": hp *= 1.10f; tempo = .80f; break;
            case "bulky_athletic": hp *= 1.15f; atk *= 1.10f; tempo = .90f; break;
            case "lean": hp *= .85f; atk *= .90f; tempo = 1.10f; recovery *= .75f; break;
            case "lean_athletic": hp *= .95f; tempo = 1.15f; recovery *= .85f; break;
            case "upper_developed": atk *= 1.10f; break;
            case "lower_developed": spd *= 1.10f; break;
        }
        return new PetCombatStats(level, Math.Max(1, Round(hp)), Math.Max(1, st),
            Math.Max(1, Round(atk)), Math.Max(0, Round(def)), Math.Max(0, Round(res)),
            Math.Max(1, Round(spd)), Math.Max(0, Round(luk)), tempo, recovery, body);
    }

    // Mirrors healthmon.v2.2 evolution_profile thresholds, including branch priority.
    public static string ClassifyBody(float upper, float lower, float nutrition, float energy)
    {
        float strength = (upper + lower) / 2, difference = upper - lower;
        if (energy >= 30 && strength < 45) return "adipose";
        if (energy <= -30 && strength >= 65) return "lean_athletic";
        if (energy <= -30) return "lean";
        if (energy >= 30 && strength >= 65) return "bulky_athletic";
        if (energy >= 30) return "rounded_general";
        if (strength >= 65 && difference >= 15) return "upper_developed";
        if (strength >= 65 && difference <= -15) return "lower_developed";
        if (strength >= 65 && nutrition >= 60) return "balanced_athletic";
        if (strength >= 65) return "developed_general";
        return strength >= 45 ? "ordinary" : "undertrained";
    }

    public string BodyName
    {
        get
        {
            switch (BodyType)
            {
                case "adipose": return "비만형";
                case "rounded_general": return "통통형";
                case "bulky_athletic": return "벌크 운동형";
                case "lean": return "마른형";
                case "lean_athletic": return "마른 운동형";
                case "upper_developed": return "상체 발달형";
                case "lower_developed": return "하체 발달형";
                case "balanced_athletic": return "균형 운동형";
                case "developed_general": return "운동형";
                case "undertrained": return "운동 부족형";
                default: return "일반형";
            }
        }
    }

    public float ActionGaugePerSecond => (20 + SPD * 3) * ActionSpeedMultiplier;
    public string StatusText => string.Format(CultureInfo.InvariantCulture,
        "<b>전투 능력치 · {0}</b>\nHP {1}    ST {2:0.#}\n공격 {3}    방어 {4}    저항 {5}\n속도 {6}    행운 {7}\n행동 속도 ×{8:0.##}    ST 회복 ×{9:0.##}",
        BodyName, MaxHP, MaxST, ATK, DEF, RES, SPD, LUK, ActionSpeedMultiplier, StaminaRecoveryMultiplier);

    private static bool Bounded(float v, float min, float max) => !float.IsNaN(v) && !float.IsInfinity(v) && v >= min && v <= max;
    private static int Round(float v) => (int)Math.Round(v, MidpointRounding.AwayFromZero);
}
