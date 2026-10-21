package com.healthmon.capstone.data.transfer

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

        LiveWorkoutRequestDispatcher.request()
    }
}