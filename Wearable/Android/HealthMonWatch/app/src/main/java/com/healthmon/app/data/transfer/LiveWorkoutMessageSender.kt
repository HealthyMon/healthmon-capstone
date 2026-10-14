package com.healthmon.app.data.transfer

import android.content.Context
import android.util.Log

import com.google.android.gms.wearable.Wearable
import com.healthmon.app.model.LiveWorkoutState

import kotlinx.coroutines.tasks.await

import org.json.JSONObject

object LiveWorkoutMessageSender {
    private const val TAG = "HealthMonLiveSender"

    suspend fun send(context: Context, state: LiveWorkoutState) {
        try {
            Log.d("HM_TEST", "SEND seq=${state.sequence}")

            val json = JSONObject().apply {
                put(
                    "sessionId",
                    state.sessionId
                )
                put(
                    "exercise",
                    state.exercise.name
                )
                put(
                    "status",
                    state.status.name
                )
                put(
                    "durationSeconds",
                    state.durationSeconds
                )

                putNullable(
                    "heartRate",
                    state.heartRate
                )
                putNullable(
                    "averageHeartRate",
                    state.averageHeartRate
                )
                putNullable(
                    "maxHeartRate",
                    state.maxHeartRate
                )
                putNullable(
                    "calories",
                    state.calories
                )
                putNullable(
                    "steps",
                    state.steps
                )
                putNullable(
                    "distanceKm",
                    state.distanceKm
                )

                put(
                    "timestamp",
                    state.timestamp
                )
                put(
                    "sequence",
                    state.sequence
                )
            }

            val payload = json.toString().toByteArray(Charsets.UTF_8)
            val nodes = Wearable.getNodeClient(context).connectedNodes.await()
            if (nodes.isEmpty()) {
                //Log.d(TAG, "연결된 스마트폰 없음")
                Log.w("HM_TEST", "NO_NODE seq=${state.sequence}")
                return
            }

            nodes.forEach { node ->
                Wearable
                    .getMessageClient(context)
                    .sendMessage(
                        node.id,
                        LiveWorkoutContract.LIVE_STATE_PATH,
                        payload
                    )
                    .await()
                /*
                Log.d(
                    TAG,
                    "실시간 전송 성공: " +
                            "node=${node.displayName}, " +
                            "session=${state.sessionId}, " +
                            "seq=${state.sequence}, " +
                            "status=${state.status}"
                )
                 */
                Log.d("HM_TEST", "OK seq=${state.sequence}")
            }
        } catch (e: Exception) {
            //Log.e(TAG, "실시간 전송 실패", e)
            Log.e("HM_TEST", "FAIL seq=${state.sequence}", e)
        }
    }

    private fun JSONObject.putNullable(key: String, value: Any?) {
        if (value == null) {
            put(
                key,
                JSONObject.NULL
            )
        } else {
            put(
                key,
                value
            )
        }
    }
}