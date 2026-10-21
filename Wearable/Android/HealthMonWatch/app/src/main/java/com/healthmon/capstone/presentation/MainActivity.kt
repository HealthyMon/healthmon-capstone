package com.healthmon.capstone.presentation

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.wear.compose.material3.AppScaffold
import com.healthmon.capstone.presentation.theme.HealthMonWatchTheme

//Wear OS 앱 실행 및 compose UI시작
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            HealthMonWatchTheme {
                AppScaffold {
                    HealthMonApp()
                }
            }
        }
    }
}