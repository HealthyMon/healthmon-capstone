package com.healthmon.capstone.exercise

import androidx.health.services.client.data.ExerciseType
import com.healthmon.capstone.model.WorkoutType

fun WorkoutType.toHealthServicesType(): ExerciseType {
    return when (this) {
        WorkoutType.WALKING -> ExerciseType.WALKING
        WorkoutType.RUNNING -> ExerciseType.RUNNING
        WorkoutType.CYCLING -> ExerciseType.BIKING
        WorkoutType.SQUAT -> ExerciseType.SQUAT
        WorkoutType.GYMNASTICS -> ExerciseType.GYMNASTICS
    }
}