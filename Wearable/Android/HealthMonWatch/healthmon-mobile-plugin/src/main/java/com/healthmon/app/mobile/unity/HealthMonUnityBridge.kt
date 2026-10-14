package com.healthmon.app.mobile.unity

import android.content.Context
import android.util.Log

import com.healthmon.app.mobile.data.local.WorkoutStorage
import com.healthmon.app.mobile.wear.LiveWorkoutRequestSender

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking

import org.json.JSONArray
import org.json.JSONObject


object HealthMonUnityBridge {
    private const val TAG = "HealthMonUnityBridge"

    @Volatile
    private lateinit var appContext: Context

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

    /*
     * Unity 앱 시작 시 한 번 호출한다.
     */
    @JvmStatic
    fun initialize(context: Context) {
        appContext = context.applicationContext

        //Log.d(TAG, "HealthMonUnityBridge 초기화 완료")
    }

    @JvmStatic
    fun getPendingWorkoutResults(): String {
        val context = appContext
                ?: run {
                    Log.e(TAG, "Bridge가 초기화되지 않음")
                    return "[]"
                }

        return try {
            val workouts = runBlocking(Dispatchers.IO) {
                    WorkoutStorage
                        .getPendingForUnity(
                            context
                        )
                }

            val jsonArray = JSONArray()

            workouts.forEach { workout ->
                val json = JSONObject()

                json.put(
                    "id",
                    workout.id
                )
                json.put(
                    "exercise",
                    workout.exerciseType
                )
                json.put(
                    "startTime",
                    workout.startTime
                )
                json.put(
                    "endTime",
                    workout.endTime
                )
                json.put(
                    "durationSeconds",
                    workout.durationSeconds
                )
                json.put(
                    "averageHeartRate",
                    workout.averageHeartRate
                        ?: JSONObject.NULL
                )
                json.put(
                    "maxHeartRate",
                    workout.maxHeartRate
                        ?: JSONObject.NULL
                )
                json.put(
                    "calories",
                    workout.calories
                        ?: JSONObject.NULL
                )
                json.put(
                    "steps",
                    workout.steps
                        ?: JSONObject.NULL
                )
                json.put(
                    "distanceKm",
                    workout.distanceKm
                        ?: JSONObject.NULL
                )
                /*
                 * DB에서는
                 * "HEART_RATE,CALORIES,STEPS"
                 *
                 * 형태로 저장되어 있으므로
                 * JSON 배열로 다시 변환한다.
                 */
                val metricsArray = JSONArray()

                workout.supportedMetrics
                    .split(",")
                    .filter {
                        it.isNotBlank()
                    }
                    .forEach {
                        metricsArray.put(
                            it
                        )
                    }

                json.put(
                    "supportedMetrics",
                    metricsArray
                )
                json.put(
                    "source",
                    workout.source
                )
                json.put(
                    "receivedAt",
                    workout.receivedAt
                )
                jsonArray.put(
                    json
                )
            }

            //Log.d(TAG, "Unity 전달 대기 운동 수: ${workouts.size}")

            jsonArray.toString()

        } catch (e: Exception) {
            Log.e(TAG, "운동 기록 조회 실패", e)
            "[]"
        }
    }

    @JvmStatic
    fun markWorkoutConsumed(workoutId: String): Boolean {
        val context = appContext ?: return false

        if (workoutId.isBlank()) {
            return false
        }

        return try {
            runBlocking(Dispatchers.IO) {
                WorkoutStorage
                    .markConsumed(
                        context,
                        workoutId
                    )
            }

            //Log.d(TAG, "Unity 처리 완료: $workoutId")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Unity 처리 완료 저장 실패: $workoutId", e)
            false
        }
    }

    @JvmStatic
    fun getPendingWorkoutCount(): Int {
        val context = appContext ?: return 0

        return try {
            runBlocking(Dispatchers.IO) {
                WorkoutStorage
                    .getPendingForUnity(
                        context
                    )
                    .size
            }
        } catch (e: Exception) {
            Log.e(TAG, "Pending 운동 개수 조회 실패", e)
            0
        }
    }

    @JvmStatic
    fun getLatestLiveWorkoutState(): String {
        val state = LiveWorkoutStateHolder.getLatest() ?: return ""

        return JSONObject().apply {
            put(
                "sessionId",
                state.sessionId
            )
            put(
                "exercise",
                state.exercise
            )
            put(
                "status",
                state.status
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
        }.toString()
    }

    @JvmStatic
    fun requestLiveWorkoutState(): Boolean {
        if (!::appContext.isInitialized) {
            return false
        }

        LiveWorkoutRequestSender.send(
            appContext
        )

        return true
    }
}