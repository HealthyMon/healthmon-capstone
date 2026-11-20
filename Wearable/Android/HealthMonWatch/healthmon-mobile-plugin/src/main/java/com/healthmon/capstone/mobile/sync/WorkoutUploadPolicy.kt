package com.healthmon.capstone.mobile.sync

import com.healthmon.capstone.mobile.data.local.WorkoutEntity
import org.json.JSONObject
import java.time.Instant

/** Only measured primary metrics are normalized. HR/calories/distance never become reps. */
object WorkoutUploadPolicy {
    enum class Outcome { SYNCED, RETRY, AUTH_REQUIRED, NEEDS_CORRECTION }

    fun outcome(code: Int, durableAcknowledgement: Boolean): Outcome = when {
        code in 200..299 && durableAcknowledgement -> Outcome.SYNCED
        code in 200..299 -> Outcome.RETRY // truncated/invalid success cannot consume a record
        code == 401 -> Outcome.AUTH_REQUIRED
        code == 408 || code == 429 || code >= 500 -> Outcome.RETRY
        else -> Outcome.NEEDS_CORRECTION
    }

    fun payload(workout: WorkoutEntity): JSONObject {
        require(workout.startTime > 0 && workout.endTime >= workout.startTime) { "invalid_time" }
        val type = when (workout.exerciseType.uppercase()) {
            "WALK", "WALKING" -> "walk"
            "RUN", "RUNNING" -> "run"
            "SQUAT", "SQUATS" -> "squat"
            "LUNGE", "LUNGES" -> "lunge"
            "PUSHUP", "PUSH_UP", "PUSH_UPS" -> "pushup"
            "DUMBBELL" -> "dumbbell"
            "CYCLE", "CYCLING", "BIKING" -> "cycle"
            "STRETCH", "STRETCHING" -> "stretch"
            "GYMNASTICS" -> "gymnastics"
            else -> throw IllegalArgumentException("unsupported_exercise")
        }
        val metrics = workout.supportedMetrics.split(',').toSet()
        val actual: Double? = when (type) {
            "walk" -> workout.steps?.takeIf { it >= 0 && "STEPS" in metrics }?.toDouble()
            "run", "cycle", "stretch", "gymnastics" -> workout.durationSeconds.takeIf { it >= 0 }?.div(60.0)
            // Existing watch schema has no repetition sensor field. Null remains null.
            else -> null
        }
        val unit = when (type) {
            "walk" -> "steps"
            "run", "cycle", "stretch", "gymnastics" -> "minutes"
            else -> "repetitions"
        }
        return JSONObject().apply {
            put("event_id", workout.id)
            put("revision", 1)
            put("occurred_at", Instant.ofEpochMilli(workout.endTime).toString())
            put("started_at", Instant.ofEpochMilli(workout.startTime).toString())
            put("workout_type", type)
            put("actual", actual ?: JSONObject.NULL)
            put("unit", unit)
            // The server resolves the goal effective at started_at. No fabricated defaults.
            put("target", JSONObject.NULL)
            put("source", "watch")
            put("synthetic", false)
        }
    }

    fun acknowledged(body: String, eventId: String): Boolean = try {
        val json = JSONObject(body)
        json.optString("event_id") == eventId && json.opt("stored") == true &&
            json.optInt("revision", -1) == 1 && json.has("evaluation_status")
    } catch (_: Exception) { false }
}
