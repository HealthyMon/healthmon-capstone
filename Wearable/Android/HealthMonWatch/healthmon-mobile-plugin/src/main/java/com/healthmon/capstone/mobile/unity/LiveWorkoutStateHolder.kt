package com.healthmon.capstone.mobile.unity

import com.healthmon.capstone.mobile.model.PhoneLiveWorkoutState

object LiveWorkoutStateHolder {
    @Volatile
    private var latestState: PhoneLiveWorkoutState? = null

    @Synchronized
    fun update(state: PhoneLiveWorkoutState): Boolean {
        val current = latestState

        val accepted =
            when {
                current == null -> { true }

                current.sessionId == state.sessionId -> {
                    state.sequence > current.sequence
                }

                else -> {
                    state.timestamp > current.timestamp
                }
            }

        if (accepted) {
            latestState = state
        }

        return accepted
    }

    fun getLatest(): PhoneLiveWorkoutState? {
        return latestState
    }

    @Synchronized
    fun clear() {
        latestState = null
    }
}