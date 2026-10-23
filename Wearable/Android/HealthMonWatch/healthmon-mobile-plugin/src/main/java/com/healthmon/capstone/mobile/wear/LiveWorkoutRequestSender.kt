package com.healthmon.capstone.mobile.wear

import android.content.Context
import android.util.Log
import com.google.android.gms.wearable.Wearable

object LiveWorkoutRequestSender {
    private const val TAG = "HealthMonLiveRequestSender"

    fun send(context: Context) {
        Wearable
            .getNodeClient(context)
            .connectedNodes
            .addOnSuccessListener { nodes ->
                if (nodes.isEmpty()) {
                    return@addOnSuccessListener
                }

                nodes.forEach { node ->
                    Wearable
                        .getMessageClient(context)
                        .sendMessage(
                            node.id,
                            LiveWorkoutContract.LIVE_REQUEST_PATH,
                            ByteArray(0)
                        )
                        .addOnFailureListener { e ->
                            Log.e(TAG, "현재 운동 상태 요청 실패", e)
                        }
                }
            }
            .addOnFailureListener { e ->
                Log.e(TAG, "연결 노드 조회 실패", e)
            }
    }
}