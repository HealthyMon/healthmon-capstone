package com.healthmon.capstone.data

import com.healthmon.capstone.model.WorkoutMetric
import com.healthmon.capstone.model.WorkoutResult
import com.healthmon.capstone.model.WorkoutType
import com.healthmon.capstone.model.WorkoutUiState

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update


object WorkoutRepository {
    private val _workoutUiState = MutableStateFlow(WorkoutUiState())
    val workoutUiState: StateFlow<WorkoutUiState> = _workoutUiState.asStateFlow()

    private val _completedWorkout = MutableStateFlow<WorkoutResult?>(null)
    val completedWorkout: StateFlow<WorkoutResult?> = _completedWorkout.asStateFlow()

    private val _activeWorkoutType = MutableStateFlow<WorkoutType?>(null)

    val activeWorkoutType: StateFlow<WorkoutType?> = _activeWorkoutType.asStateFlow()

    fun setActiveWorkout(workoutType: WorkoutType) {
        _activeWorkoutType.value = workoutType
    }

    fun clearActiveWorkout() {
        _activeWorkoutType.value = null
    }

    fun reset() {
        _workoutUiState.value = WorkoutUiState()
        _completedWorkout.value = null
    }

    fun setSupportedMetrics(metrics: Set<WorkoutMetric>) {
        _workoutUiState.update { current ->
            current.copy(
                supportedMetrics = metrics
            )
        }
    }

    fun updateMetrics(heartRate: Double?, averageHeartRate: Double?, maxHeartRate: Double?, steps: Long?, calories: Double?, distanceMeters: Double?) {
        _workoutUiState.update { current ->
            current.copy(
                heartRate = heartRate ?: current.heartRate,
                averageHeartRate = averageHeartRate ?: current.averageHeartRate,
                maxHeartRate = maxHeartRate ?: current.maxHeartRate,

                steps = steps ?: current.steps,
                calories = calories ?: current.calories,
                distanceKm = distanceMeters?.div(1000.0) ?: current.distanceKm
            )
        }
    }

    fun updateTimer(checkpointTimeMillis: Long?, activeDurationMillis: Long?, isActive: Boolean) {
        _workoutUiState.update { current ->
            if (checkpointTimeMillis != null && activeDurationMillis != null) {
                current.copy(
                    checkpointTimeMillis = checkpointTimeMillis,
                    checkpointActiveDurationMillis = activeDurationMillis,
                    isActive = isActive
                )
            } else if (!isActive && current.isActive) {
                val finalDuration = current.getActiveDurationMillis()

                current.copy(
                    checkpointTimeMillis = null,
                    checkpointActiveDurationMillis = finalDuration,
                    isActive = false
                )
            } else {
                current.copy(
                    isActive = isActive
                )
            }
        }
    }

    fun getCurrentState(): WorkoutUiState {
        return _workoutUiState.value
    }

    fun completeWorkout(result: WorkoutResult) {
        _completedWorkout.value = result
    }

    fun clearCompletedWorkout() {
        _completedWorkout.value = null
    }
}