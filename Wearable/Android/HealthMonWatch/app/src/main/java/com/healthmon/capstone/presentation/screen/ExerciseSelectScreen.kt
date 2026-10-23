package com.healthmon.capstone.presentation.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import com.healthmon.capstone.model.WorkoutType
import com.healthmon.capstone.presentation.theme.HealthMonBackground
import com.healthmon.capstone.presentation.theme.HealthMonSurface
import com.healthmon.capstone.presentation.theme.HealthMonText


@Composable
fun ExerciseSelectScreen(onExerciseSelected: (WorkoutType) -> Unit) {
    val listState = rememberTransformingLazyColumnState()

    ScreenScaffold(scrollState = listState) {
        TransformingLazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxSize()
                .background(HealthMonBackground),
            contentPadding = PaddingValues(
                top = 24.dp,
                bottom = 64.dp
            )
        ) {
            item {
                ListHeader {
                    Text(text = "운동 선택", color = HealthMonText)
                }
            }

            item {
                ExerciseButton(name = "걷기") {
                    onExerciseSelected(WorkoutType.WALKING)
                }
            }

            item {
                ExerciseButton(name = "달리기") {
                    onExerciseSelected(WorkoutType.RUNNING)
                }
            }

            item {
                ExerciseButton(name = "사이클") {
                    onExerciseSelected(WorkoutType.CYCLING)
                }
            }


            item {
                ExerciseButton(name = "스쿼트") {
                    onExerciseSelected(WorkoutType.SQUAT)
                }
            }

            item {
                ExerciseButton(name = "체조") {
                    onExerciseSelected(WorkoutType.GYMNASTICS)
                }
            }
        }
    }
}

@Composable
private fun ExerciseButton(name: String, onClick: () -> Unit) {
    Box(modifier = Modifier.fillMaxWidth(),
        contentAlignment = Alignment.Center) {
        Button(
            onClick = onClick,
            modifier = Modifier
                .fillMaxWidth(0.82f)
                .height(48.dp),
            colors = ButtonDefaults.buttonColors(
                    containerColor = HealthMonSurface,
                    contentColor = HealthMonText),
            label = {
                Text(
                    text = name
                )
            }
        )
    }
}