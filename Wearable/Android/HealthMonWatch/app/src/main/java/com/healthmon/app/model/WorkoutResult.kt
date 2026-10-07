package com.healthmon.app.model


data class WorkoutResult(

    val id: String,

    val exercise: WorkoutType,

    val startTime: Long,

    val endTime: Long,

    val durationSeconds: Long,

    val averageHeartRate: Double?,

    val maxHeartRate: Double?,

    val calories: Double?,

    val steps: Long?,

    val distanceKm: Double?,

    val supportedMetrics:
    Set<WorkoutMetric>,

    val source: String = "WATCH_MANUAL"
)