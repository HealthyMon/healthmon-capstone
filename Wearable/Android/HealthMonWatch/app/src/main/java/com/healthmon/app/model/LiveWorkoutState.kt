package com.healthmon.app.model

data class LiveWorkoutState(
    val sessionId: String,
    val exercise: WorkoutType,
    val status: LiveWorkoutStatus,

    val durationSeconds: Long,

    val heartRate: Double?,
    val averageHeartRate: Double?,
    val maxHeartRate: Double?,

    val calories: Double?,
    val steps: Long?,
    val distanceKm: Double?,

    val timestamp: Long,
    val sequence: Long
)