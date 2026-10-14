package com.healthmon.app.exercise

import android.content.Context
import android.util.Log
import androidx.health.services.client.HealthServices
import androidx.health.services.client.getCapabilities
import androidx.health.services.client.data.ExerciseType

class HealthServicesManager(context: Context) {
    private val exerciseClient = HealthServices.getClient(context).exerciseClient

    suspend fun checkWalkingCapabilities() {
        try {
            val capabilities = exerciseClient.getCapabilities()

            if (ExerciseType.WALKING !in capabilities.supportedExerciseTypes) {
                Log.d("HealthMon", "걷기 운동은 이 기기에서 지원되지 않습니다.")
                return
            }

            val walkingCapabilities = capabilities.getExerciseTypeCapabilities(ExerciseType.WALKING)

            //Log.d("HealthMon", "걷기 지원 데이터: " + walkingCapabilities.supportedDataTypes)

        } catch (e: Exception) {
            Log.e("HealthMon", "Health Services capability 확인 실패", e)
        }
    }
}