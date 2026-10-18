package com.healthmon.capstone.data.local

import android.content.Context

import com.healthmon.capstone.model.WorkoutResult


object WorkoutStorage {


    suspend fun save(
        context: Context,
        result: WorkoutResult
    ) {

        val dao =
            HealthMonDatabase
                .getInstance(context)
                .workoutDao()


        dao.saveWorkout(
            result.toEntity()
        )
    }


    suspend fun getAll(
        context: Context
    ): List<WorkoutResult> {

        val dao =
            HealthMonDatabase
                .getInstance(context)
                .workoutDao()


        return dao
            .getAllWorkouts()
            .map {
                it.toWorkoutResult()
            }
    }


    suspend fun getPending(
        context: Context
    ): List<WorkoutResult> {

        val dao =
            HealthMonDatabase
                .getInstance(context)
                .workoutDao()


        return dao
            .getPendingWorkouts()
            .map {
                it.toWorkoutResult()
            }
    }


    suspend fun markAsSent(
        context: Context,
        id: String
    ) {

        HealthMonDatabase
            .getInstance(context)
            .workoutDao()
            .markAsSent(id)
    }
}