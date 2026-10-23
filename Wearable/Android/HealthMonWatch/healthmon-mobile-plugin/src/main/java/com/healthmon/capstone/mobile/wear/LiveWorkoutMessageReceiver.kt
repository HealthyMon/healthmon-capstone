package com.healthmon.capstone.mobile.wear

import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService
import com.healthmon.capstone.mobile.model.PhoneLiveWorkoutState
import com.healthmon.capstone.mobile.unity.LiveWorkoutStateHolder
import org.json.JSONObject

class LiveWorkoutMessageReceiver : WearableListenerService() {
    override fun onMessageReceived(messageEvent: MessageEvent) {
        super.onMessageReceived(messageEvent)

        if (messageEvent.path != LiveWorkoutContract.LIVE_STATE_PATH) {
            return
        }

        try {
            val jsonString = messageEvent
                    .data
                    .toString(Charsets.UTF_8)

            val json = JSONObject(jsonString)
            val state = PhoneLiveWorkoutState(
                    sessionId = json.getString("sessionId"),
                    exercise = json.getString("exercise"),
                    status = json.getString("status"),

                    durationSeconds = json.getLong("durationSeconds"),

                    heartRate = json.getNullableDouble("heartRate"),
                    averageHeartRate = json.getNullableDouble("averageHeartRate"),
                    maxHeartRate = json.getNullableDouble("maxHeartRate"),

                    calories = json.getNullableDouble("calories"),
                    steps = json.getNullableLong("steps"),
                    distanceKm = json.getNullableDouble("distanceKm"),

                    timestamp = json.getLong("timestamp"),
                    sequence = json.getLong("sequence")
                )

            LiveWorkoutStateHolder.update(state)

        } catch (e: Exception) {
            Log.e(TAG, "실시간 메시지 파싱 실패")
        }
    }

    private fun JSONObject.getNullableDouble(key: String): Double? {
        return if (!has(key) || isNull(key)) {
            null
        } else {
            getDouble(key)
        }
    }

    private fun JSONObject.getNullableLong(key: String): Long? {
        return if (!has(key) || isNull(key)) {
            null
        } else {
            getLong(key)
        }
    }


    companion object {
        private const val TAG = "HealthMonLiveReceiver"
    }
}