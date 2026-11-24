using System;
using System.Globalization;
using Healthmon.Beta;

/// <summary>A read-only projection for the status window; never awards or changes game state.</summary>
public sealed class HealthMonStatusSnapshot
{
    public string Name, Scope, Evolution;
    public int Level, Experience, RequiredExperience;
    public bool IsCached;
    public float Energy;
    // Clockwise from twelve o'clock. The radar labels and points share this order.
    public readonly float[] Axes = new float[6];
    public PetCombatStats Combat;

    public static readonly string[] AxisNames = { "상체", "친밀도", "활동성", "영양", "주도성", "하체" };

    public static HealthMonStatusSnapshot FromServer(PetState state, string expectedPet, bool connected)
    {
        if (state == null || !state.IsValidCommonState(expectedPet)) return null;
        var result = Create(state.settings?.name, state.pet_id, state.level, state.current_exp,
            state.required_exp, state.upper_body, state.lower_body, state.nutrition,
            state.energy_balance, state.activity, state.affinity, state.initiative);
        result.IsCached = !connected;
        int stage = state.published_model_stage;
        result.Evolution = state.evolution_target_stage > stage ? "진화 가능 · " + (stage + 1) + "차 진화" :
            stage >= 3 ? "최종 진화 완료" : stage == 0 ? "첫 진화 Lv.10" :
            stage + "차 진화 · 다음 Lv." + ((stage + 1) * 10);
        return result;
    }

    public static HealthMonStatusSnapshot Create(string name, string scope, int level, int exp, int required,
        float upper, float lower, float nutrition, float energy, float activity, float affinity, float initiative)
    {
        var result = new HealthMonStatusSnapshot {
            Name = string.IsNullOrWhiteSpace(name) ? "헬스몬" : name,
            Scope = scope, Level = level, Experience = exp, RequiredExperience = required, Energy = energy,
            Combat = PetCombatStats.Calculate(level, upper, lower, nutrition, energy, activity, affinity, initiative)
        };
        result.Axes[0] = upper; result.Axes[1] = affinity; result.Axes[2] = activity;
        result.Axes[3] = nutrition; result.Axes[4] = initiative; result.Axes[5] = lower;
        return result;
    }

    public float ExperienceFraction => Level >= 30 ? 1 : Unit(RequiredExperience <= 0 ? 0 : (float)Experience / RequiredExperience);
    public static float Unit(float value) => float.IsNaN(value) || float.IsInfinity(value) ? 0 : Math.Max(0, Math.Min(1, value));
    public static float EnergyFraction(float value) => Unit((value + 100) / 200);
    public static string Number(float value) => value.ToString("0.#", CultureInfo.InvariantCulture);
    public string EnergyText => Energy.ToString("+0.#;-0.#;0", CultureInfo.InvariantCulture);
}
