package com.healthmon.app.data.transfer

object LiveWorkoutRequestDispatcher {
    @Volatile
    private var listener: (() -> Unit)? = null

    fun register(listener: () -> Unit) {
        this.listener = listener
    }

    fun unregister() {
        listener = null
    }

    fun request() {
        listener?.invoke()
    }
}