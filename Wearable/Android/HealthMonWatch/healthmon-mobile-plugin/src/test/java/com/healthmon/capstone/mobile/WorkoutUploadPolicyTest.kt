package com.healthmon.capstone.mobile

import com.healthmon.capstone.mobile.data.local.WorkoutEntity
import com.healthmon.capstone.mobile.sync.WorkoutUploadPolicy
import com.healthmon.capstone.mobile.sync.WorkoutUploadPolicy.Outcome
import org.junit.Assert.*
import org.junit.Test

class WorkoutUploadPolicyTest {
    private fun workout(type: String = "RUNNING", seconds: Long = 1800, steps: Long? = null,
                        metrics: String = "") = WorkoutEntity(
        "watch-stable-id", type, 1_760_000_000_000, 1_760_001_800_000,
        seconds, 88.0, 110.0, 123.0, steps, 3.0, metrics, "WATCH_MANUAL", false, 1_760_001_800_010)

    @Test fun durationIsMinutesAndGoalComesFromServer() {
        val body = WorkoutUploadPolicy.payload(workout())
        assertEquals(30.0, body.getDouble("actual"), 0.00001)
        assertEquals("minutes", body.getString("unit"))
        assertEquals("run", body.getString("workout_type"))
        assertTrue(body.isNull("target"))
        assertEquals("2025-10-09T09:23:20Z", body.getString("occurred_at"))
        assertEquals("watch-stable-id", body.getString("event_id"))
        assertFalse(body.has("user_id")); assertFalse(body.has("verified"))
    }

    @Test fun unavailableRepetitionsStayNull() {
        val body = WorkoutUploadPolicy.payload(workout("SQUAT"))
        assertTrue(body.isNull("actual"))
        assertEquals("repetitions", body.getString("unit"))
        assertTrue(body.isNull("target"))
    }

    @Test fun unknownStepsAndMeasuredZeroAreDistinct() {
        assertTrue(WorkoutUploadPolicy.payload(workout("WALKING")).isNull("actual"))
        assertEquals(0.0, WorkoutUploadPolicy.payload(workout("WALKING", steps=0, metrics="STEPS"))
            .getDouble("actual"), 0.0)
        assertTrue(WorkoutUploadPolicy.payload(workout("WALKING", steps=0)).isNull("actual"))
    }

    @Test fun gymnasticsIsNeverRelabelledAsStretching() {
        val body = WorkoutUploadPolicy.payload(workout("GYMNASTICS"))
        assertEquals("gymnastics", body.getString("workout_type"))
        assertEquals("minutes", body.getString("unit"))
        assertTrue(body.isNull("target"))
    }

    @Test fun retriesNeverConsumeUntilDurableAcknowledgement() {
        assertEquals(Outcome.RETRY, WorkoutUploadPolicy.outcome(200, false))
        assertEquals(Outcome.RETRY, WorkoutUploadPolicy.outcome(429, false))
        assertEquals(Outcome.RETRY, WorkoutUploadPolicy.outcome(503, false))
        assertEquals(Outcome.AUTH_REQUIRED, WorkoutUploadPolicy.outcome(401, false))
        assertEquals(Outcome.NEEDS_CORRECTION, WorkoutUploadPolicy.outcome(409, false))
        assertEquals(Outcome.NEEDS_CORRECTION, WorkoutUploadPolicy.outcome(422, false))
        assertEquals(Outcome.SYNCED, WorkoutUploadPolicy.outcome(201, true))
    }

    @Test fun malformedOrOtherEventAcknowledgementIsNotSuccess() {
        assertFalse(WorkoutUploadPolicy.acknowledged("not JSON", "id"))
        assertFalse(WorkoutUploadPolicy.acknowledged("{\"event_id\":\"other\",\"stored\":true,\"revision\":1,\"evaluation_status\":\"scored\"}", "id"))
        assertFalse(WorkoutUploadPolicy.acknowledged("{\"event_id\":\"id\",\"stored\":false}", "id"))
        assertTrue(WorkoutUploadPolicy.acknowledged("{\"event_id\":\"id\",\"stored\":true,\"revision\":1,\"evaluation_status\":\"recorded_unscored\"}", "id"))
    }
}
