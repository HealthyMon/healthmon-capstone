package com.healthmon.app.presentation.screen

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text

import com.healthmon.app.R
import com.healthmon.app.model.WorkoutResult
import com.healthmon.app.presentation.theme.HealthMonBackground
import com.healthmon.app.presentation.theme.HealthMonMint
import com.healthmon.app.presentation.theme.HealthMonSubText
import com.healthmon.app.presentation.theme.HealthMonSurface
import com.healthmon.app.presentation.theme.HealthMonText
import com.healthmon.app.model.WorkoutMetric

import kotlinx.coroutines.delay


@Composable
fun WorkoutResultScreen(result: WorkoutResult, onConfirm: () -> Unit) {
    val listState = rememberTransformingLazyColumnState()
    //결과 화면 진입 시 한 번만 Unity 전송 요청
    ScreenScaffold(scrollState = listState) {
        contentPadding -> TransformingLazyColumn(
            state = listState,
            modifier = Modifier
                    .fillMaxSize()
                    .background(
                        HealthMonBackground
                    ),
            contentPadding = contentPadding) {
            // 제목
            item {
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "운동 완료!",
                        style = MaterialTheme
                                .typography
                                .titleMedium,
                        color = HealthMonMint
                    )

                    Text(
                        text = result
                                .exercise
                                .displayName,
                        style = MaterialTheme
                                .typography
                                .labelMedium,
                        color = HealthMonSubText
                    )
                }
            }

            // 완료 애니메이션
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(
                            vertical = 4.dp
                        ),
                    contentAlignment = Alignment.Center) {
                    WorkoutCompleteAnimation()
                }
            }


            // 운동 시간
            item {
                ResultMetric(
                    title = "운동 시간",
                    value = formatWorkoutTime(
                            result.durationSeconds)
                )
            }

            if (WorkoutMetric.HEART_RATE in result.supportedMetrics) {
                item {
                    ResultMetric(
                        title = "평균 심박수",
                        value = result.averageHeartRate
                                ?.let {

                                    String.format(
                                        "%.0f BPM",
                                        it
                                    )
                                }
                                ?: "-- BPM"
                    )
                }

                item {
                    ResultMetric(
                        title = "최대 심박수",
                        value = result.maxHeartRate
                                ?.let {

                                    String.format(
                                        "%.0f BPM",
                                        it
                                    )
                                }
                                ?: "-- BPM"
                    )
                }
            }

            if (WorkoutMetric.CALORIES in result.supportedMetrics) {
                item {
                    ResultMetric(
                        title = "칼로리",
                        value = result.calories
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

            if (WorkoutMetric.STEPS in result.supportedMetrics ||
                WorkoutMetric.DISTANCE in result.supportedMetrics) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly) {
                        if (WorkoutMetric.STEPS in result.supportedMetrics) {
                            ResultMetric(
                                title = "걸음",
                                value = result.steps
                                        ?.toString()
                                        ?: "--"
                            )
                        }

                        if (WorkoutMetric.DISTANCE in result.supportedMetrics) {
                            ResultMetric(
                                title = "거리",
                                value = result.distanceKm
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
            // 확인 완료
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(
                            top = 8.dp,
                            bottom = 40.dp
                        ),
                    contentAlignment = Alignment.Center) {
                    Button(
                        onClick = onConfirm,
                        modifier = Modifier
                                .fillMaxWidth(
                                    0.72f
                                )
                                .height(
                                    42.dp
                                ),
                        colors = ButtonDefaults
                                .buttonColors(
                                    containerColor = HealthMonSurface,
                                    contentColor = HealthMonText
                                ),
                        label = {
                            Text(
                                "확인 완료"
                            )
                        }
                    )
                }
            }
        }
    }
}


@Composable
private fun ResultMetric(title: String, value: String) {
    Column(
        modifier = Modifier.padding(
                vertical = 3.dp
            ),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme
                    .typography
                    .bodyLarge,
            color = HealthMonText
        )

        Text(
            text = title,
            style = MaterialTheme
                    .typography
                    .labelSmall,
            color = HealthMonSubText
        )
    }
}

@Composable
private fun WorkoutCompleteAnimation() {
    val frames = listOf(
        R.drawable.complete_00,
        R.drawable.complete_01,
        R.drawable.complete_02,
        R.drawable.complete_03,
        R.drawable.complete_04,
        R.drawable.complete_05,
        R.drawable.complete_06,
        R.drawable.complete_07
    )

    var frameIndex by remember {
        mutableIntStateOf(0)
    }

    LaunchedEffect(Unit) {
        for (i in frames.indices) {
            frameIndex = i
            delay(130)
        }
    }


    Image(
        painter = painterResource(
                id = frames[frameIndex]
            ),
        contentDescription = "Happy HealthMon",
        modifier = Modifier.size(90.dp)
    )
}