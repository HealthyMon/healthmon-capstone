package com.healthmon.app.data.transfer


object WorkoutDataContract {

    /*
     * 운동 결과 DataItem 경로
     *
     * 실제 경로:
     * /workout/result/{운동 ID}
     */
    const val RESULT_PATH_PREFIX = "/workout/result/"

    const val KEY_ID = "id"

    const val KEY_EXERCISE = "exercise"

    const val KEY_START_TIME = "start_time"
    const val KEY_END_TIME = "end_time"
    const val KEY_DURATION_SECONDS = "duration_seconds"

    const val KEY_AVERAGE_HEART_RATE = "average_heart_rate"
    const val KEY_MAX_HEART_RATE = "max_heart_rate"

    const val KEY_CALORIES = "calories"
    const val KEY_STEPS = "steps"
    const val KEY_DISTANCE_KM = "distance_km"

    const val KEY_SUPPORTED_METRICS = "supported_metrics"
    const val KEY_SOURCE = "source"

    const val ACK_PATH_PREFIX = "/workout/ack/"
}