package com.healthmon.app.mobile.wear

import android.content.Context
import android.util.Log

import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable

import kotlinx.coroutines.tasks.await


object WorkoutAckSender {
    private const val TAG = "HealthMonPhoneAck"

    suspend fun send(context: Context, workoutId: String): Boolean {
        val path = WorkoutDataContract.ACK_PATH_PREFIX + workoutId

        val request = PutDataMapRequest
                .create(path)
                .apply {
                    dataMap.putString(
                        WorkoutDataContract.KEY_ID,
                        workoutId
                    )
                    /*
                     * DataItem 내용을 명확히 변경시키기 위한
                     * ACK 생성 시각
                     */
                    dataMap.putLong(
                        "ack_time",
                        System.currentTimeMillis()
                    )
                }
                .asPutDataRequest()
                .setUrgent()

        return try {
            val dataItem = Wearable
                    .getDataClient(context)
                    .putDataItem(request)
                    .await()
            //Log.d(TAG, "ACK DataItem 등록 성공: ${dataItem.uri}")
            true

        } catch (e: Exception) {
            Log.e(TAG, "ACK DataItem 등록 실패: $workoutId", e)
            false
        }
    }
}