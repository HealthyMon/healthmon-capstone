package com.healthmon.capstone.data.transfer

import android.content.Context
import android.util.Log

import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable

import com.healthmon.capstone.model.WorkoutResult
import com.healthmon.capstone.data.local.WorkoutStorage

import kotlinx.coroutines.tasks.await


object WorkoutDataLayerSender {
    private const val TAG = "HealthMonDataLayer"

    suspend fun sendWorkout(context: Context, workout: WorkoutResult): Boolean {
        val path = WorkoutDataContract.RESULT_PATH_PREFIX + workout.id

        val request = PutDataMapRequest
                .create(path)
                .apply {
                    dataMap.putString(
                        WorkoutDataContract.KEY_ID,
                        workout.id
                    )
                    dataMap.putString(
                        WorkoutDataContract.KEY_EXERCISE,
                        workout.exercise.name
                    )
                    dataMap.putLong(
                        WorkoutDataContract.KEY_START_TIME,
                        workout.startTime
                    )
                    dataMap.putLong(
                        WorkoutDataContract.KEY_END_TIME,
                        workout.endTime
                    )
                    dataMap.putLong(
                        WorkoutDataContract.KEY_DURATION_SECONDS,
                        workout.durationSeconds
                    )

                    workout
                        .averageHeartRate
                        ?.let {
                            dataMap.putDouble(
                                WorkoutDataContract
                                    .KEY_AVERAGE_HEART_RATE,
                                it
                            )
                        }

                    workout
                        .maxHeartRate
                        ?.let {
                            dataMap.putDouble(
                                WorkoutDataContract
                                    .KEY_MAX_HEART_RATE,
                                it
                            )
                        }

                    workout
                        .calories
                        ?.let {
                            dataMap.putDouble(
                                WorkoutDataContract.KEY_CALORIES,
                                it
                            )
                        }

                    workout
                        .steps
                        ?.let {
                            dataMap.putLong(
                                WorkoutDataContract.KEY_STEPS,
                                it
                            )
                        }

                    workout
                        .distanceKm
                        ?.let {
                            dataMap.putDouble(
                                WorkoutDataContract.KEY_DISTANCE_KM,
                                it
                            )
                        }

                    dataMap.putStringArrayList(
                        WorkoutDataContract.KEY_SUPPORTED_METRICS,
                        ArrayList(
                            workout
                                .supportedMetrics
                                .map {
                                    it.name
                                }
                        )
                    )

                    dataMap.putString(
                        WorkoutDataContract.KEY_SOURCE,
                        workout.source
                    )
                }
                .asPutDataRequest()
                .setUrgent()

        return try {
            Wearable
                    .getDataClient(context)
                    .putDataItem(request)
                    .await()
            true
        } catch (e: Exception) {
            Log.e(TAG, "DataItem 등록 실패: ${workout.id}", e)
            false
        }
    }

    suspend fun sendPendingWorkouts(context: Context) {
        val pendingWorkouts = WorkoutStorage.getPending(context)

        pendingWorkouts.forEach { workout ->
            sendWorkout(
                context,
                workout
            )
        }
    }
}