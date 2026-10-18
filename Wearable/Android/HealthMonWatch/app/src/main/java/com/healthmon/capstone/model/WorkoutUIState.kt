package com.healthmon.capstone.model


data class WorkoutUiState(
    val heartRate: Double? = null,
    val averageHeartRate: Double? = null,
    val maxHeartRate: Double? = null,

    val calories: Double? = null,
    val steps: Long? = null,
    val distanceKm: Double? = null,

    val supportedMetrics: Set<WorkoutMetric> = emptySet(),

    val checkpointTimeMillis: Long? = null,
    val checkpointActiveDurationMillis: Long = 0L,

    val isActive: Boolean = false
) {
    fun getActiveDurationMillis(nowMillis: Long = System.currentTimeMillis()): Long {
        val checkpointTime = checkpointTimeMillis

        return if (isActive && checkpointTime != null) {
            checkpointActiveDurationMillis + (nowMillis - checkpointTime).coerceAtLeast(0L)
        } else {
            checkpointActiveDurationMillis
        }
    }
}