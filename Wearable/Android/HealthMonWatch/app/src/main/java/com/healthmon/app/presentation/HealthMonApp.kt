package com.healthmon.app.presentation

import com.healthmon.app.presentation.screen.MainScreen
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState

import com.healthmon.app.data.WorkoutRepository
import com.healthmon.app.model.WorkoutType
import com.healthmon.app.presentation.navigation.WatchScreen
import com.healthmon.app.presentation.screen.*
import android.Manifest
import android.health.connect.HealthPermissions
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import com.healthmon.app.exercise.ExerciseService

@Composable
fun HealthMonApp() {
    val context = LocalContext.current

    val workoutUiState by
    WorkoutRepository
        .workoutUiState
        .collectAsState()

    val completedWorkout by
    WorkoutRepository
        .completedWorkout
        .collectAsState()

    val permissions = buildList {
            add(Manifest.permission.ACTIVITY_RECOGNITION)
            if (Build.VERSION.SDK_INT >= 36) {
                add(
                    HealthPermissions.READ_HEART_RATE
                )
            } else {

                add(
                    Manifest.permission.BODY_SENSORS
                )
            }
        }

    val permissionLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts
                    .RequestMultiplePermissions()
        ) {
            // 이후 결과 처리
        }
    LaunchedEffect(Unit) {
        permissionLauncher.launch(
            permissions.toTypedArray()
        )
    }

    var screen by remember {
        mutableStateOf(WatchScreen.MAIN)
    }
    var selectedExercise by remember {
        mutableStateOf<WorkoutType?>(null)
    }

    LaunchedEffect(completedWorkout) {
        if (
            completedWorkout != null &&
            screen == WatchScreen.WORKOUT
        ) {

            screen =
                WatchScreen.WORKOUT_RESULT
        }
    }

    when (screen) {
        WatchScreen.MAIN -> {
            MainScreen(
                onWakeFinished = {
                    screen = WatchScreen.EXERCISE_SELECT
                }
            )
        }
        WatchScreen.EXERCISE_SELECT -> {
            ExerciseSelectScreen(
                onExerciseSelected = { exercise ->
                    /*
                     * 실제 ExerciseClient 운동 측정 시작
                     */
                    ExerciseService.start(
                        context,
                        exercise
                    )

                    selectedExercise = exercise

                    screen = WatchScreen.WORKOUT
                }
            )
        }
        WatchScreen.WORKOUT -> {
            selectedExercise?.let { exercise ->
                WorkoutScreen(
                    exercise = exercise,

                    workoutData = workoutUiState,

                    onFinish = {
                        ExerciseService.end(
                            context
                        )
                    }
                )
            }
        }
        WatchScreen.WORKOUT_RESULT -> {
            completedWorkout?.let { result ->
                WorkoutResultScreen(
                    result = result,

                    onConfirm = {

                        WorkoutRepository
                            .clearCompletedWorkout()

                        selectedExercise =
                            null

                        screen =
                            WatchScreen.MAIN
                    }
                )
            }
        }
    }
}