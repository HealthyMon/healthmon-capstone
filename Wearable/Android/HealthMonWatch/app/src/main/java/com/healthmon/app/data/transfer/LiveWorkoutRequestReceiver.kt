package com.healthmon.app.data.transfer

import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService

class LiveWorkoutRequestReceiver :
    WearableListenerService() {
    override fun onMessageReceived(messageEvent: MessageEvent) {
        super.onMessageReceived(
            messageEvent
        )

        if (messageEvent.path != LiveWorkoutContract.LIVE_REQUEST_PATH) {
            return
        }

        //Log.d(TAG, "스마트폰에서 현재 상태 요청 수신")

        LiveWorkoutRequestDispatcher.request()
    }

    companion object {
        private const val TAG = "HealthMonLiveRequestReceiver"
    }
}