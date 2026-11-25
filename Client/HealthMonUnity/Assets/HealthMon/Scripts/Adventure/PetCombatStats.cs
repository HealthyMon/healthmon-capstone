using System;
using System.Globalization;
using Healthmon.Beta;

/// <summary>One projection of verified growth scores, shared by status and both battle modes.
/// Weighted growth rules. See Docs/COMBAT_STATS.md; these are game rules, not health advice.</summary>
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

        int growth = level - 1;
        decimal upperScore = Normalize(upper), lowerScore = Normalize(lower), nutritionScore = Normalize(nutrition);
        decimal activityScore = Normalize(activity), affinityScore = Normalize(affinity), initiativeScore = Normalize(initiative);
        decimal energyPenalty = -Math.Abs((decimal)energy) / 100m;

        decimal hp = Scale(100 + 6 * growth,
            .15m * upperScore + .30m * lowerScore + .25m * nutritionScore + .10m * activityScore + .20m * energyPenalty);
        decimal st = Scale(20 + growth,
            .30m * lowerScore + .50m * activityScore + .15m * initiativeScore + .05m * energyPenalty);
        decimal atk = Scale(10 + 1.2m * growth,
            .45m * upperScore + .15m * lowerScore + .10m * nutritionScore + .15m * activityScore + .15m * initiativeScore);
        decimal def = Scale(5 + .5m * growth,
            .40m * upperScore + .35m * lowerScore + .15m * nutritionScore + .10m * energyPenalty);
        decimal res = Scale(5 + .5m * growth,
            .60m * nutritionScore + .20m * activityScore + .10m * initiativeScore + .10m * energyPenalty);
        decimal spd = Scale(5 + .25m * growth,
            .50m * lowerScore + .35m * activityScore + .10m * initiativeScore + .05m * energyPenalty);
        decimal luk = Scale(5 + .20m * growth,
            .45m * affinityScore + .45m * initiativeScore + .10m * activityScore);

        // Timing and recovery are separate battle mechanics, outside the seven stat projections.
        string body = ClassifyBody(upper, lower, nutrition, energy);
        float tempo = 1, recovery = nutrition >= 60 ? 1.15f : nutrition < 40 ? .75f : 1;
        switch (body)
        {
            case "adipose": tempo = .50f; break;
            case "rounded_general": tempo = .80f; break;
            case "bulky_athletic": tempo = .90f; break;
            case "lean": tempo = 1.10f; recovery *= .75f; break;
            case "lean_athletic": tempo = 1.15f; recovery *= .85f; break;
        }
        return new PetCombatStats(level, Round(hp), (float)Math.Round(st, 1, MidpointRounding.AwayFromZero),
            Round(atk), Round(def), Round(res), Round(spd), Round(luk), tempo, recovery, body);
    }

    private static decimal Normalize(float score) => ((decimal)score - 50m) / 50m;
    private static decimal Scale(decimal levelBase, decimal weightedScore) => levelBase * (1 + .30m * weightedScore);

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
    private static int Round(decimal v) => (int)Math.Round(v, MidpointRounding.AwayFromZero);
}
