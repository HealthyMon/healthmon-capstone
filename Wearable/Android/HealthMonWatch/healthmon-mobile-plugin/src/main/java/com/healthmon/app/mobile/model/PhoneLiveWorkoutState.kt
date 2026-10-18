package com.healthmon.app.mobile.model

data class PhoneLiveWorkoutState(
    val sessionId: String,
    val exercise: String,
    val status: String,

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