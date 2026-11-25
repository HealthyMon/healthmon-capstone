using System;
using Healthmon.Beta;

public static class CombatStatsChecks
{
    private static int checks;
    private static void Check(bool value, string message)
    { checks++; if (!value) throw new Exception(message); }
    private static PetCombatStats Stats(int level = 1, float upper = 50, float lower = 50,
        float nutrition = 50, float energy = 0, float activity = 50, float affinity = 50, float initiative = 50)
        => PetCombatStats.Calculate(level, upper, lower, nutrition, energy, activity, affinity, initiative);
    public static void Main(string[] args)
    {
        var first = Stats(); var last = Stats(30);
        Check(first.MaxHP == 100 && first.MaxST == 20 && first.ATK == 10 && first.DEF == 5 &&
              first.RES == 5 && first.SPD == 5 && first.LUK == 5, "level-one baseline");
        Check(last.MaxHP == 274 && last.ATK == 45 && last.DEF == 20, "level 30 changes real battle values");
        Check(Stats(10, upper:90).ATK > Stats(10).ATK, "upper training increases damage");
        Check(Stats(30, lower:90).DEF > last.DEF && Stats(30, lower:90).SPD > last.SPD, "lower training changes armor and speed");
        Check(Stats(nutrition:80).MaxHP > first.MaxHP && Stats(nutrition:80).RES > first.RES, "nutrition changes health and resistance");
        Check(Stats(nutrition:80).StaminaRecoveryMultiplier > first.StaminaRecoveryMultiplier &&
              Stats(nutrition:20).StaminaRecoveryMultiplier < 1, "food quality changes stamina recovery");
        var fat = Stats(10, upper:30, lower:30, energy:30);
        var normal = Stats(10, upper:30, lower:30);
        Check(fat.BodyType == "adipose" && fat.MaxHP < normal.MaxHP, "energy imbalance reduces weighted health");
        Check(fat.ActionSpeedMultiplier == .5f && fat.ActionGaugePerSecond == (20 + 3 * fat.SPD) * .5f, "adipose needs twice the gauge time at the same SPD");
        Check(Stats(10, energy:30).ActionSpeedMultiplier == .8f, "moderate strength surplus is rounded, not adipose");
        Check(Stats(10, upper:80, lower:80, energy:30).BodyType == "bulky_athletic", "trained surplus is not mislabeled adipose");
        Check(Stats(10, energy:-30).StaminaRecoveryMultiplier < 1, "energy deficit also affects recovery");
        Check(Stats(10, energy:-30).MaxHP < Stats(10).MaxHP, "lean tradeoff has less health");
        Check(Stats(10, upper:80, lower:80, energy:-30).BodyType == "lean_athletic", "trained deficit priority");
        var example = Stats(10, 80, 60, 70, 8, 75, 40, 85);
        Check(example.MaxHP == 167 && example.MaxST == 32.6f && example.ATK == 24 &&
              example.DEF == 11 && example.RES == 11 && example.SPD == 8 && example.LUK == 7,
              "level-ten design example, all seven values");
        var opposite = Stats(10, 80, 60, 70, -8, 75, 40, 85);
        Check(opposite.Equals(example), "same magnitude energy penalty");
        Check(Stats(10, 0, 0, 0, 0, 0, 50, 0).ATK == 15 &&
              Stats(10, 100, 100, 100, 0, 100, 50, 100).ATK == 27,
              "attack ranges from 70% to 130% of level base");
        Check(Stats(10, upper:80, lower:65).ATK == Stats(10, upper:80, lower:66).ATK,
              "crossing a body threshold does not apply another attack multiplier");
        foreach (int level in new[] { 1, 10, 20, 30 })
        foreach (float axis in new[] { 0f, 50f, 100f })
        foreach (float energy in new[] { -100f, -30f, 0f, 30f, 100f })
        {
            var s = Stats(level, axis, axis, axis, energy, axis, axis, axis);
            Check(s.MaxHP > 0 && s.MaxST > 0 && s.ATK > 0 && s.DEF >= 0 && s.RES >= 0 &&
                s.SPD > 0 && s.LUK >= 0 && s.ActionGaugePerSecond > 0 && s.StaminaRecoveryMultiplier > 0,
                "no deadlock/negative stat at score boundaries");
        }
        bool overLevelRejected = false;
        try { Stats(31); } catch (ArgumentOutOfRangeException) { overLevelRejected = true; }
        Check(overLevelRejected, "levels above 30 rejected");
        foreach (float invalid in new[] { float.NaN, float.PositiveInfinity, -1f, 101f })
        {
            bool rejected = false; try { Stats(upper:invalid); } catch (ArgumentOutOfRangeException) { rejected = true; }
            Check(rejected, "bad score rejected");
        }
        Check(first.StatusText.Contains("HP 100") && last.StatusText.Contains("HP 274") &&
              fat.StatusText.Contains("0.5"), "status uses actual computed stats and body effect");
        // TSV generated directly from Python's production evolution_profile, not a second test implementation.
        if (args.Length > 0)
        {
            foreach (string row in System.IO.File.ReadAllLines(args[0]))
            {
                var v = row.Split('\t');
                var culture = System.Globalization.CultureInfo.InvariantCulture;
                Check(PetCombatStats.ClassifyBody(float.Parse(v[0],culture), float.Parse(v[1],culture),
                    float.Parse(v[2],culture), float.Parse(v[3],culture)) == v[4], "body classification agrees with server");
            }
        }
        Console.WriteLine("HEALTHMON_COMBAT_STATS_CHECKS_PASS assertions=" + checks);
    }
}
