package com.healthmon.capstone.data.local

import com.healthmon.capstone.model.WorkoutMetric
import com.healthmon.capstone.model.WorkoutResult
import com.healthmon.capstone.model.WorkoutType

fun WorkoutResult.toEntity(): WorkoutEntity {
    return WorkoutEntity(

        id = id,

        exerciseType = exercise.name,

        startTime = startTime,
        endTime = endTime,
        durationSeconds = durationSeconds,

        averageHeartRate = averageHeartRate,
        maxHeartRate = maxHeartRate,
        calories = calories,

        steps = steps,
        distanceKm = distanceKm,

        supportedMetrics = supportedMetrics
                .joinToString(",") {
                    it.name
                },

        source = source,
        syncState = "PENDING"
    )
}

fun WorkoutEntity.toWorkoutResult(): WorkoutResult {

    val metrics =
        if (supportedMetrics.isBlank()) {
            emptySet()
        }
        else {
            supportedMetrics
                .split(",")
                .mapNotNull { metricName ->
                    WorkoutMetric.entries
                        .find {
                            it.name == metricName
                        }
                }
                .toSet()
        }


    return WorkoutResult(
        id = id,

        exercise = WorkoutType.valueOf(
                exerciseType
            ),

        startTime = startTime,
        endTime = endTime,
        durationSeconds = durationSeconds,

        averageHeartRate = averageHeartRate,
        maxHeartRate = maxHeartRate,
        calories = calories,

        steps = steps,
        distanceKm = distanceKm,

        supportedMetrics = metrics,

        source = source
    )
}