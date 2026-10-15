package com.healthmon.app.mobile.wear

import android.util.Log

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.WearableListenerService
import com.google.android.gms.wearable.Wearable

import com.healthmon.app.mobile.data.local.WorkoutStorage
import com.healthmon.app.mobile.model.PhoneWorkoutResult

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class WorkoutDataLayerReceiver :
    WearableListenerService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onDataChanged(dataEvents: DataEventBuffer) {
        super.onDataChanged(dataEvents)

        dataEvents.forEach { event ->
            if (event.type != DataEvent.TYPE_CHANGED) {
                return@forEach
            }

            val dataItem = event.dataItem

            val path = dataItem.uri.path ?: return@forEach

            val resultUri = dataItem.uri

            if (!path.startsWith(WorkoutDataContract.RESULT_PATH_PREFIX)) {
                return@forEach
            }

            val dataMap = DataMapItem
                    .fromDataItem(dataItem)
                    .dataMap

            val id = dataMap.getString(WorkoutDataContract.KEY_ID)
                    ?: return@forEach

            val exercise = dataMap.getString(WorkoutDataContract.KEY_EXERCISE)
                    ?: return@forEach

            val startTime = dataMap.getLong(WorkoutDataContract.KEY_START_TIME)

            val endTime = dataMap.getLong(WorkoutDataContract.KEY_END_TIME)

            val duration = dataMap.getLong(WorkoutDataContract.KEY_DURATION_SECONDS)

            val averageHeartRate =
                if (dataMap.containsKey(WorkoutDataContract.KEY_AVERAGE_HEART_RATE)) {
                    dataMap.getDouble(WorkoutDataContract.KEY_AVERAGE_HEART_RATE)
                } else {
                    null
                }

            val maxHeartRate =
                if (dataMap.containsKey(WorkoutDataContract.KEY_MAX_HEART_RATE)) {
                    dataMap.getDouble(WorkoutDataContract.KEY_MAX_HEART_RATE)
                } else {
                    null
                }

            val calories =
                if (dataMap.containsKey(WorkoutDataContract.KEY_CALORIES)) {
                    dataMap.getDouble(WorkoutDataContract.KEY_CALORIES)
                } else {
                    null
                }

            val steps =
                if (dataMap.containsKey(WorkoutDataContract.KEY_STEPS)) {
                    dataMap.getLong(WorkoutDataContract.KEY_STEPS)
                } else {
                    null
                }

            val distance =
                if (dataMap.containsKey(WorkoutDataContract.KEY_DISTANCE_KM)) {
                    dataMap.getDouble(WorkoutDataContract.KEY_DISTANCE_KM)
                } else {
                    null
                }

            val supportedMetrics = dataMap.getStringArrayList(WorkoutDataContract.KEY_SUPPORTED_METRICS)
                    ?.toList()
                    ?: emptyList()

            val source = dataMap.getString(WorkoutDataContract.KEY_SOURCE)
                    ?: "WATCH_MANUAL"

            val result = PhoneWorkoutResult(
                    id = id,
                    exercise = exercise,

                    startTime = startTime,
                    endTime = endTime,
                    durationSeconds = duration,

                    averageHeartRate = averageHeartRate,
                    maxHeartRate = maxHeartRate,

                    calories = calories,
                    steps = steps,
                    distanceKm = distance,

                    supportedMetrics = supportedMetrics,

                    source = source
                )

            serviceScope.launch {
                try {
                    WorkoutStorage.save(applicationContext, result)

                    val ackSuccess = WorkoutAckSender.send(
                            applicationContext,
                            result.id
                        )

                    if (ackSuccess) {
                        Wearable
                                .getDataClient(applicationContext)
                                .deleteDataItems(resultUri)
                                .await()
                    } else {
                        Log.e(TAG, "워치 ACK 등록 실패: ${result.id}")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "휴대폰 Room 저장 실패: ${result.id}", e)
                }
            }
        }
    }


    override fun onDestroy() {
        serviceScope.cancel()

        super.onDestroy()
    }


    companion object {
        private const val TAG = "HealthMonPhoneReceiver"
    }
}