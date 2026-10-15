package com.healthmon.app.presentation

import com.healthmon.app.presentation.screen.MainScreen
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState

import com.healthmon.app.data.WorkoutRepository
import com.healthmon.app.model.WorkoutType
import com.healthmon.app.presentation.navigation.WatchScreen
import com.healthmon.app.presentation.screen.*
import android.Manifest
import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import android.os.Build
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.healthmon.app.exercise.ExerciseService

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
        mutableStateOf(
            WatchScreen.MAIN
        )
    }

    var selectedExercise by remember {
        mutableStateOf<WorkoutType?>(null)
    }

    /*
     * 권한 요청 후 자동으로 시작할 운동
     */
    var pendingExercise by remember {
        mutableStateOf<WorkoutType?>(null)
    }

    /*
     * 운동 측정에 반드시 필요한 권한만 정의한다.
     *
     * POST_NOTIFICATIONS는 운동 측정 자체에는 필수가 아니므로
     * 여기에 넣지 않는다.
     */
    val requiredExercisePermissions = remember {
        buildList {

            add(
                Manifest.permission.ACTIVITY_RECOGNITION
            )

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
    }

    /*
     * 앱 시작 시 요청할 전체 권한.
     *
     * 알림 권한은 OngoingActivity 표시를 위해 요청하지만
     * 거부되어도 운동 측정 자체는 허용한다.
     */
    val startupPermissions = remember {
        buildList {

            addAll(
                requiredExercisePermissions
            )

            if (
                Build.VERSION.SDK_INT >=
                Build.VERSION_CODES.TIRAMISU
            ) {
                add(
                    Manifest.permission.POST_NOTIFICATIONS
                )
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

    fun startWorkout(
        exercise: WorkoutType
    ) {
        ExerciseService.start(
            context,
            exercise
        )

        selectedExercise = exercise
        screen = WatchScreen.WORKOUT
    }

    val permissionLauncher =
        rememberLauncherForActivityResult(
            contract =
                ActivityResultContracts
                    .RequestMultiplePermissions()
        ) {

            if (
                hasRequiredExercisePermissions()
            ) {

                pendingExercise?.let { exercise ->

                    pendingExercise = null

                    startWorkout(
                        exercise
                    )
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
                selectedExercise =
                    completedWorkout!!.exercise

                screen =
                    WatchScreen.WORKOUT_RESULT
            }

            activeWorkoutType != null -> {
                selectedExercise =
                    activeWorkoutType

                screen =
                    WatchScreen.WORKOUT
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