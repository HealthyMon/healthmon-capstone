package com.healthmon.capstone.presentation

import com.healthmon.capstone.presentation.screen.MainScreen
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState

import com.healthmon.capstone.data.WorkoutRepository
import com.healthmon.capstone.model.WorkoutType
import com.healthmon.capstone.presentation.navigation.WatchScreen
import com.healthmon.capstone.presentation.screen.*
import android.Manifest
import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import android.os.Build
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.healthmon.capstone.exercise.ExerciseService

//화면 관리자 - Repository의 운동상태 감시, 현재 보여줄 화면 관리, 사용자 입력에 따라 ExerciseService 호출
@Composable
fun HealthMonApp() {
    val activeWorkoutType by WorkoutRepository
        .activeWorkoutType
        .collectAsState()

    val context = LocalContext.current

    val workoutUiState by WorkoutRepository
        .workoutUiState
        .collectAsState()

    val completedWorkout by WorkoutRepository
        .completedWorkout
        .collectAsState()


    var screen by remember {
        mutableStateOf(WatchScreen.MAIN)
    }

    var selectedExercise by remember {
        mutableStateOf<WorkoutType?>(null)
    }

    var pendingExercise by remember {
        mutableStateOf<WorkoutType?>(null)
    }

    val requiredExercisePermissions = remember {
        buildList {
            add(Manifest.permission.ACTIVITY_RECOGNITION)

            if (Build.VERSION.SDK_INT >= 36) {
                add(HealthPermissions.READ_HEART_RATE)
            } else {
                add(Manifest.permission.BODY_SENSORS)
            }
        }
    }

    val startupPermissions = remember {
        buildList {
            addAll(requiredExercisePermissions)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    fun hasRequiredExercisePermissions(): Boolean {
        return requiredExercisePermissions.all { permission ->
            ContextCompat.checkSelfPermission(
                context,
                permission
            ) == PackageManager.PERMISSION_GRANTED
        }
    }

    fun startWorkout(exercise: WorkoutType) {
        ExerciseService.start(
            context,
            exercise
        )

        selectedExercise = exercise
        screen = WatchScreen.WORKOUT
    }

    val permissionLauncher = rememberLauncherForActivityResult(
            contract = ActivityResultContracts
                    .RequestMultiplePermissions()
        ) {
            if (hasRequiredExercisePermissions()) {
                pendingExercise?.let { exercise ->

                    pendingExercise = null

                    startWorkout(exercise)
                }

            } else {
                pendingExercise = null

                Toast.makeText(
                    context,
                    "운동 측정을 위해 활동 및 심박수 권한이 필요합니다.",
                    Toast.LENGTH_LONG
                ).show()
            }
        }

    LaunchedEffect(Unit) {
        val missingPermissions =
            startupPermissions.filter { permission ->
                ContextCompat.checkSelfPermission(
                    context,
                    permission
                ) != PackageManager.PERMISSION_GRANTED
            }

        if (missingPermissions.isNotEmpty()) {
            permissionLauncher.launch(
                missingPermissions.toTypedArray()
            )
        }
    }

    LaunchedEffect(activeWorkoutType, completedWorkout) {
        when {
            completedWorkout != null -> {
                selectedExercise = completedWorkout!!.exercise

                screen = WatchScreen.WORKOUT_RESULT
            }

            activeWorkoutType != null -> {
                selectedExercise = activeWorkoutType

                screen = WatchScreen.WORKOUT
            }
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
                    if (hasRequiredExercisePermissions()) {
                        startWorkout(exercise)
                    } else {
                        pendingExercise = exercise

                        permissionLauncher.launch(
                            requiredExercisePermissions
                                .toTypedArray()
                        )
                    }
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
                        WorkoutRepository.clearCompletedWorkout()
                        selectedExercise = null
                        screen = WatchScreen.MAIN
                    }
                )
            }
        }
    }
}