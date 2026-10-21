package com.healthmon.capstone.mobile.model

data class PhoneWorkoutResult(

    val id: String,
    val exercise: String,

    val startTime: Long,
    val endTime: Long,
    val durationSeconds: Long,

    val averageHeartRate: Double?,
    val maxHeartRate: Double?,
    val calories: Double?,
    val steps: Long?,
    val distanceKm: Double?,

    val supportedMetrics: List<String>,
    val source: String
)