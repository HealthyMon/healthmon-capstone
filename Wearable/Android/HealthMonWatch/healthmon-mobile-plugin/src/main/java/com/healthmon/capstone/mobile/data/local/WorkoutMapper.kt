package com.healthmon.capstone.mobile.data.local

import com.healthmon.capstone.mobile.model.PhoneWorkoutResult


fun PhoneWorkoutResult.toEntity(): WorkoutEntity {

    return WorkoutEntity(

        id =
            id,

        exerciseType =
            exercise,

        startTime =
            startTime,

        endTime =
            endTime,

        durationSeconds =
            durationSeconds,

        averageHeartRate =
            averageHeartRate,

        maxHeartRate =
            maxHeartRate,

        calories =
            calories,

        steps =
            steps,

        distanceKm =
            distanceKm,

        supportedMetrics =
            supportedMetrics.joinToString(","),

        source =
            source,

        consumedByUnity =
            false,

        receivedAt =
            System.currentTimeMillis()
    )
}