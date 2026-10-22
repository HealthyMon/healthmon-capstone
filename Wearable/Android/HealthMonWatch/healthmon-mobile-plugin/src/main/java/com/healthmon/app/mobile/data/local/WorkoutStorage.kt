package com.healthmon.app.mobile.data.local

import android.content.Context

import com.healthmon.app.mobile.model.PhoneWorkoutResult
import com.healthmon.app.mobile.sync.ServerWorkoutSync


object WorkoutStorage {


    suspend fun save(
        context: Context,
        result: PhoneWorkoutResult
    ) {

        val database =
            HealthMonPhoneDatabase
                .getInstance(
                    context
                )


        database
            .workoutDao()
            .saveWorkout(
                result.toEntity()
            )

        // The durable Room row is committed first. Startup/manual recovery schedules
        // again if the process dies between this commit and WorkManager enqueue.
        ServerWorkoutSync.schedule(context)
    }


    suspend fun getAll(
        context: Context
    ): List<WorkoutEntity> {

        return HealthMonPhoneDatabase
            .getInstance(
                context
            )
            .workoutDao()
            .getAllWorkouts()
    }


    suspend fun getPendingForUnity(
        context: Context
    ): List<WorkoutEntity> {

        return HealthMonPhoneDatabase
            .getInstance(
                context
            )
            .workoutDao()
            .getPendingForUnity()
    }


    suspend fun markConsumed(
        context: Context,
        id: String
    ) {

        HealthMonPhoneDatabase
            .getInstance(
                context
            )
            .workoutDao()
            .markConsumedByUnity(
                id
            )
    }
}
