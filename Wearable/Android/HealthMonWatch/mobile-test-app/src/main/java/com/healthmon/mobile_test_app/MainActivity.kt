package com.healthmon.mobiletest

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.healthmon.mobile_test_app.ui.theme.HealthMonWatchTheme
import android.util.Log
import com.healthmon.app.mobile.unity.HealthMonUnityBridge

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HealthMonUnityBridge
            .initialize(
                applicationContext
            )


        val pendingCount =
            HealthMonUnityBridge
                .getPendingWorkoutCount()


        Log.d(
            "HealthMonBridgeTest",
            "Pending 운동 수: $pendingCount"
        )


        val json =
            HealthMonUnityBridge
                .getPendingWorkoutResults()


        Log.d(
            "HealthMonBridgeTest",
            "Unity 전달 JSON: $json"
        )
        val testWorkoutId =
            "e0b54b8d-f5d1-4534-9e7b-d2e8739f1826"

        val consumedResult =
            HealthMonUnityBridge.markWorkoutConsumed(
                testWorkoutId
            )

        Log.d(
            "HealthMonBridgeTest",
            "Consumed 처리 결과: $consumedResult"
        )

        val countAfter =
            HealthMonUnityBridge.getPendingWorkoutCount()

        Log.d(
            "HealthMonBridgeTest",
            "Consumed 처리 후 Pending 운동 수: $countAfter"
        )

        val jsonAfter =
            HealthMonUnityBridge.getPendingWorkoutResults()

        Log.d(
            "HealthMonBridgeTest",
            "Consumed 처리 후 JSON: $jsonAfter"
        )
        enableEdgeToEdge()
        setContent {
            HealthMonWatchTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    Greeting(
                        name = "Android",
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}

@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    Text(
        text = "Hello $name!",
        modifier = modifier
    )
}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
    HealthMonWatchTheme {
        Greeting("Android")
    }
}