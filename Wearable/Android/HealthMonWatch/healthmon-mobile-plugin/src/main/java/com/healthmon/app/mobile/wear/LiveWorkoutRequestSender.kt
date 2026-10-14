package com.healthmon.app.mobile.wear

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
                    Log.d(TAG, "연결된 워치 없음")
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
                        .addOnSuccessListener {
                            //Log.d(TAG, "현재 운동 상태 요청 성공: " + "node=${node.displayName}")
                        }
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