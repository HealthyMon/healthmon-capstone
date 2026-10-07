package com.healthmon.app.presentation

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.lifecycleScope
import androidx.wear.compose.material3.AppScaffold
import com.healthmon.app.exercise.HealthServicesManager
import com.healthmon.app.presentation.theme.HealthMonWatchTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    override fun onCreate(
        savedInstanceState: Bundle?
    ) {

        super.onCreate(savedInstanceState)


        val healthServicesManager =
            HealthServicesManager(this)


        lifecycleScope.launch {

            healthServicesManager
                .checkWalkingCapabilities()
        }


        setContent {

            HealthMonWatchTheme {

                AppScaffold {

                    HealthMonApp()
                }
            }
        }
    }
}