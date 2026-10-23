using System;

namespace Healthmon.Beta
{
    [Serializable] public sealed class TestPetStateRequest
    {
        public int level, coin;
        public float upper_body, lower_body, nutrition, energy_balance, activity, affinity, initiative;
    }
    [Serializable] public sealed class TestWorkoutRequest
    { public string request_id, exercise; public float actual; }
    [Serializable] public sealed class TestQuestRequest
    { public string slot, candidate; }
}
