package com.healthmon.app.data.transfer

import android.content.Context
import android.util.Log

import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable

import com.healthmon.app.model.WorkoutResult
import com.healthmon.app.data.local.WorkoutStorage

import kotlinx.coroutines.tasks.await


object WorkoutDataLayerSender {
    private const val TAG = "HealthMonDataLayer"
    /*
     * 하나의 운동 결과를
     * Data Layer에 등록한다.
     */
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
                    /*
                     * nullable 데이터는
                     * 값이 있을 때만 DataMap에 넣는다.
                     */
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
            val dataItem = Wearable
                    .getDataClient(context)
                    .putDataItem(request)
                    .await()
            /*
            Log.d(
                TAG,
                "DataItem 등록 성공: " +
                        "path=${dataItem.uri.path}"
            )

             */
            true
        } catch (e: Exception) {
            Log.e(TAG, "DataItem 등록 실패: ${workout.id}", e)
            false
        }
    }

    suspend fun sendPendingWorkouts(context: Context) {
        val pendingWorkouts = WorkoutStorage.getPending(context)

        /*
        Log.d(TAG, "PENDING 운동 수: ${pendingWorkouts.size}")
        */

        pendingWorkouts.forEach { workout ->
            val success =
                sendWorkout(
                    context = context,
                    workout = workout
                )

            if (success) {
                //Log.d(TAG, "Data Layer 등록 완료: ${workout.id}")
            } else {
                //Log.d(TAG, "전송 대기 유지: ${workout.id}")
            }
        }
    }
}