package com.healthmon.app.exercise

import androidx.health.services.client.data.ExerciseType
import com.healthmon.app.model.WorkoutType

fun WorkoutType.toHealthServicesType(): ExerciseType {
    return when (this) {
        WorkoutType.WALKING -> ExerciseType.WALKING
        WorkoutType.RUNNING -> ExerciseType.RUNNING
        WorkoutType.CYCLING -> ExerciseType.BIKING
        WorkoutType.SQUAT -> ExerciseType.SQUAT
        WorkoutType.GYMNASTICS -> ExerciseType.GYMNASTICS
    }
}