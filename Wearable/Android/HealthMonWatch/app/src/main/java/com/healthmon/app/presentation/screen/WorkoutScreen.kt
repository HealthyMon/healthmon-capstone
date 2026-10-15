package com.healthmon.app.presentation.screen

import android.app.Activity
import android.view.WindowManager
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Straighten
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.Icon
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import com.healthmon.app.R
import com.healthmon.app.model.WorkoutMetric
import com.healthmon.app.model.WorkoutType
import com.healthmon.app.model.WorkoutUiState
import com.healthmon.app.presentation.theme.HealthMonBackground
import com.healthmon.app.presentation.theme.HealthMonFinish
import com.healthmon.app.presentation.theme.HealthMonMint
import com.healthmon.app.presentation.theme.HealthMonSubText
import com.healthmon.app.presentation.theme.HealthMonText
import kotlinx.coroutines.delay

@Composable
fun WorkoutScreen(exercise: WorkoutType, workoutData: WorkoutUiState, onFinish: () -> Unit) {
    val context = LocalContext.current

    DisposableEffect(context) {
        val activity = context as? Activity

        activity?.window?.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        )

        onDispose {
            activity?.window?.clearFlags(
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            )
        }
    }

    var isEnding by remember {
        mutableStateOf(false)
    }

    var nowMillis by remember {
        mutableLongStateOf(
            System.currentTimeMillis()
        )
    }

    LaunchedEffect(Unit) {
        while (true) {
            nowMillis = System.currentTimeMillis()

            delay(250)
        }
    }

    val elapsedSeconds = workoutData
            .getActiveDurationMillis(
                nowMillis
            )
            .div(1000)

    val listState = rememberTransformingLazyColumnState()

    ScreenScaffold(scrollState = listState) {
        TransformingLazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxSize()
                .background(
                    HealthMonBackground
                ),
            contentPadding = PaddingValues(
                    top = 20.dp,
                    bottom = 60.dp
                )
        ) {
            // 운동 이름 / 시간
            item {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = exercise.displayName,
                        style = MaterialTheme.typography.titleMedium,
                        color = HealthMonMint
                    )

                    Text(
                        text = formatWorkoutTime(
                                elapsedSeconds
                            ),
                        style = MaterialTheme.typography.titleLarge,
                        color = HealthMonText
                    )
                }
            }

            // 운동 애니메이션
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(
                            vertical = 4.dp
                        ),
                    contentAlignment = Alignment.Center) {
                    WorkoutAnimation(
                        exercise = exercise
                    )
                }
            }

            // 운동 수치
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(
                            horizontal = 12.dp,
                            vertical = 4.dp
                        )
                ) {
                    WorkoutMetrics(
                        workoutData = workoutData
                    )
                }
            }


            // 운동 종료
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(
                            top = 8.dp,
                            bottom = 12.dp
                        ),
                    contentAlignment = Alignment.Center) {
                    Button(
                        onClick = {
                            isEnding = true
                            onFinish()
                        },

                        enabled = !isEnding,

                        modifier = Modifier
                            .fillMaxWidth(0.72f)
                            .height(42.dp),

                        colors = ButtonDefaults.buttonColors(
                            containerColor = HealthMonFinish,
                            contentColor = Color.White
                            ),

                        label = {
                            Text(
                                if (isEnding) {
                                    "종료 중..."
                                } else {
                                    "운동 종료"
                                }
                            )
                        }
                    )
                }
            }

            item {
                Spacer(
                    modifier = Modifier.height(40.dp)
                )
            }
        }
    }
}

@Composable
private fun WorkoutAnimation(exercise: WorkoutType) {
    val frames = when (exercise) {
            WorkoutType.WALKING -> listOf(
                R.drawable.walk_00,
                R.drawable.walk_01,
                R.drawable.walk_02,
                R.drawable.walk_03,
                R.drawable.walk_04,
                R.drawable.walk_05,
                R.drawable.walk_06,
                R.drawable.walk_07
            )

            WorkoutType.RUNNING -> listOf(
                R.drawable.run_00,
                R.drawable.run_01,
                R.drawable.run_02,
                R.drawable.run_03,
                R.drawable.run_04,
                R.drawable.run_05,
                R.drawable.run_06,
                R.drawable.run_07
            )

            WorkoutType.CYCLING -> listOf(
                R.drawable.cycle_00,
                R.drawable.cycle_01,
                R.drawable.cycle_02,
                R.drawable.cycle_03,
                R.drawable.cycle_04,
                R.drawable.cycle_05,
                R.drawable.cycle_06,
                R.drawable.cycle_07
            )

            WorkoutType.SQUAT -> listOf(
                R.drawable.squat_00,
                R.drawable.squat_01,
                R.drawable.squat_02,
                R.drawable.squat_03,
                R.drawable.squat_04,
                R.drawable.squat_05,
                R.drawable.squat_06,
                R.drawable.squat_07
            )

            WorkoutType.GYMNASTICS -> listOf(
                R.drawable.stretch_00,
                R.drawable.stretch_01,
                R.drawable.stretch_02,
                R.drawable.stretch_03,
                R.drawable.stretch_04,
                R.drawable.stretch_05,
                R.drawable.stretch_06,
                R.drawable.stretch_07
            )
        }


    var frameIndex by remember(exercise) { mutableIntStateOf(0) }

    val frameDelay =
        when (exercise) {
            WorkoutType.RUNNING -> 100L
            WorkoutType.WALKING -> 160L
            WorkoutType.CYCLING -> 120L
            WorkoutType.SQUAT -> 220L
            WorkoutType.GYMNASTICS -> 250L
        }

    LaunchedEffect(exercise) {
        while (true) {
            delay(frameDelay)
            frameIndex = (frameIndex + 1) % frames.size
        }
    }


    Image(
        painter = painterResource(
                id = frames[frameIndex]
            ),
        contentDescription = "Workout HealthMon",
        modifier = Modifier.size(90.dp)
    )
}

@Composable
private fun WorkoutMetrics(workoutData: WorkoutUiState) {
    val supported = workoutData.supportedMetrics

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally) {
        if (WorkoutMetric.HEART_RATE in supported ||
            WorkoutMetric.CALORIES in supported) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly) {
                if (WorkoutMetric.HEART_RATE in supported) {
                    MetricItem(
                        icon = Icons.Filled.Favorite,
                        title = "심박수",
                        value = workoutData
                                .heartRate
                                ?.let {
                                    String.format(
                                        "%.0f BPM",
                                        it
                                    )
                                }
                                ?: "-- BPM"
                    )
                }

                if (WorkoutMetric.CALORIES in supported) {
                    MetricItem(
                        icon = Icons.Filled.LocalFireDepartment,
                        title = "칼로리",
                        value = workoutData
                                .calories
                                ?.let {
                                    String.format(
                                        "%.1f kcal",
                                        it
                                    )
                                }
                                ?: "-- kcal"
                    )
                }
            }
        }

        if (WorkoutMetric.STEPS in supported ||
            WorkoutMetric.DISTANCE in supported) {
            Spacer(
                modifier = Modifier.height(6.dp)
            )

            Row(modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly) {
                if (WorkoutMetric.STEPS in supported) {
                    MetricItem(
                        icon = Icons.Filled.DirectionsWalk,
                        title = "걸음 수",
                        value = workoutData
                                .steps
                                ?.toString()
                                ?: "--"
                    )
                }

                if (WorkoutMetric.DISTANCE in supported) {
                    MetricItem(
                        icon = Icons.Filled.Straighten,
                        title = "거리",
                        value = workoutData
                                .distanceKm
                                ?.let {
                                    String.format(
                                        "%.2f km",
                                        it
                                    )
                                }
                                ?: "-- km"
                    )
                }
            }
        }
    }
}

@Composable
private fun MetricItem(icon: ImageVector, title: String, value: String, iconColor: Color = HealthMonMint) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(
            imageVector = icon,
            contentDescription = title,
            tint = iconColor,
            modifier = Modifier.size(20.dp)
        )

        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = HealthMonText
        )

        Text(
            text = title,
            style = MaterialTheme.typography.labelSmall,
            color = HealthMonSubText
        )
    }
}


fun formatWorkoutTime(totalSeconds: Long): String {
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60

    return String.format("%02d:%02d:%02d", hours, minutes, seconds)
}