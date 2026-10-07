package com.healthmon.app.presentation.screen

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import com.healthmon.app.R
import com.healthmon.app.presentation.theme.HealthMonBackground
import kotlinx.coroutines.delay


@Composable
fun MainScreen(
    onWakeFinished: () -> Unit
) {

    val sleepFrames = listOf(
        R.drawable.sleep_00,
        R.drawable.sleep_01,
        R.drawable.sleep_02,
        R.drawable.sleep_03,
        R.drawable.sleep_04,
        R.drawable.sleep_05,
        R.drawable.sleep_06,
        R.drawable.sleep_07,
        R.drawable.sleep_08,
        R.drawable.sleep_09
    )

    val wakeFrames = listOf(
        R.drawable.wake_00,
        R.drawable.wake_01,
        R.drawable.wake_02,
        R.drawable.wake_03,
        R.drawable.wake_04,
        R.drawable.wake_05,
        R.drawable.wake_06,
        R.drawable.wake_07
    )


    var isWaking by remember {
        mutableStateOf(false)
    }

    var sleepFrame by remember {
        mutableIntStateOf(0)
    }

    var wakeFrame by remember {
        mutableIntStateOf(0)
    }


    // 잠자는 애니메이션
    LaunchedEffect(isWaking) {

        while (!isWaking) {

            delay(250)

            sleepFrame =
                (sleepFrame + 1) % sleepFrames.size
        }
    }


    // 잠에서 깨는 애니메이션
    LaunchedEffect(isWaking) {

        if (isWaking) {

            for (i in wakeFrames.indices) {

                wakeFrame = i

                delay(250)
            }

            onWakeFinished()
        }
    }


    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(HealthMonBackground)
            .clickable(
                enabled = !isWaking
            ) {
                isWaking = true
            },

        contentAlignment = Alignment.Center
    ) {

        val currentImage =
            if (isWaking) {
                wakeFrames[wakeFrame]
            } else {
                sleepFrames[sleepFrame]
            }


        Image(
            painter = painterResource(
                id = currentImage
            ),

            contentDescription = "HealthMon",

            modifier =
                Modifier.fillMaxSize(0.7f)
        )
    }
}