package com.healthmon.app.mobile.unity

import com.healthmon.app.mobile.model.PhoneLiveWorkoutState

object LiveWorkoutStateHolder {
    @Volatile
    private var latestState: PhoneLiveWorkoutState? = null

    @Synchronized
    fun update(state: PhoneLiveWorkoutState) {
        val current = latestState

        if (current == null ||
            current.sessionId != state.sessionId ||
            state.sequence > current.sequence) {
            latestState = state
        }
    }

    fun getLatest(): PhoneLiveWorkoutState? {
        return latestState
    }

    @Synchronized
    fun clear() {
        latestState = null
    }
}