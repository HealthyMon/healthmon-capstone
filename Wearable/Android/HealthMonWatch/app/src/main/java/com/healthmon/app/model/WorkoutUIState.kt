package com.healthmon.app.model


data class WorkoutUiState(

    val heartRate: Double? = null,

    val averageHeartRate: Double? = null,

    val maxHeartRate: Double? = null,

    val calories: Double? = null,

    val steps: Long? = null,

    val distanceKm: Double? = null,

    val supportedMetrics: Set<WorkoutMetric> = emptySet(),


    /*
     * Health Services가 보내준
     * ActiveDurationCheckpoint 정보
     */
    val checkpointTimeMillis: Long? = null,

    val checkpointActiveDurationMillis: Long = 0L,

    val isActive: Boolean = false
) {

    /*
     * 현재 실제 운동 시간을 계산
     */
    fun getActiveDurationMillis(
        nowMillis: Long = System.currentTimeMillis()
    ): Long {

        val checkpointTime =
            checkpointTimeMillis


        return if (
            isActive &&
            checkpointTime != null
        ) {

            checkpointActiveDurationMillis +
                    (
                            nowMillis -
                                    checkpointTime
                            ).coerceAtLeast(0L)

        } else {

            checkpointActiveDurationMillis
        }
    }
}