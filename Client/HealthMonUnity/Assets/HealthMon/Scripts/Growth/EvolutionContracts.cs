using System;

namespace Healthmon.Evolution
{
    [Serializable] public sealed class GrowthStats
    {
        public float UpperBody, LowerBody, Nutrition, EnergyBalance, Activity, Affinity, Initiative, Mood;
        public bool IsValid()
        {
            foreach (float value in new[] { UpperBody, LowerBody, Nutrition, Activity, Affinity, Initiative, Mood })
                if (float.IsNaN(value) || float.IsInfinity(value) || value < 0 || value > 100) return false;
            return !float.IsNaN(EnergyBalance) && !float.IsInfinity(EnergyBalance) && EnergyBalance >= -1 && EnergyBalance <= 1;
        }
    }
    [Serializable] public sealed class EvolutionRequest
    {
        public string request_id, score_source;
        public int level;
        public GrowthStats stats;
    }
    [Serializable] public sealed class ModelManifest
    {
        public string pet_id, species, revision, image_url, model_url, image_sha256, model_sha256;
        public int stage;
    }
    [Serializable] public sealed class EvolutionJob
    {
        public string job_id, pet_id, request_id, status, phase, error;
        public int target_stage;
        public ModelManifest result;
    }
    [Serializable] public sealed class EvolutionSettings
    {
        public string base_url = "https://127.0.0.1:8010";
        public string certificate_sha256;
        public string pet_id = "lucan-local";
        public float display_height_m = 0.35f;
        public float model_yaw_degrees = 180f;
        public bool auto_level_evolution = true;
    }
}
