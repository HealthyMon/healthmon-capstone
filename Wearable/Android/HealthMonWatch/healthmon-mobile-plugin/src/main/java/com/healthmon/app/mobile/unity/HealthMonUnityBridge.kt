package com.healthmon.app.mobile.unity

import android.content.Context
import android.util.Log

import com.healthmon.app.mobile.data.local.WorkoutStorage

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking

import org.json.JSONArray
import org.json.JSONObject


object HealthMonUnityBridge {

    private const val TAG =
        "HealthMonUnityBridge"


    /*
     * Unity에서 전달받은 Android Context
     *
     * Activity 자체를 오래 보관하면 안 되므로
     * applicationContext만 저장한다.
     */
    @Volatile
    private var appContext: Context? =
        null


    /*
     * Unity 앱 시작 시 한 번 호출한다.
     */
    @JvmStatic
    fun initialize(
        context: Context
    ) {

        appContext =
            context.applicationContext


        Log.d(
            TAG,
            "HealthMonUnityBridge 초기화 완료"
        )
    }


    /*
     * Unity가 아직 처리하지 않은
     * 운동 기록을 JSON 배열로 반환한다.
     */
    @JvmStatic
    fun getPendingWorkoutResults():
            String {

        val context =
            appContext
                ?: run {

                    Log.e(
                        TAG,
                        "Bridge가 초기화되지 않음"
                    )

                    return "[]"
                }


        return try {

            val workouts =
                runBlocking(
                    Dispatchers.IO
                ) {

                    WorkoutStorage
                        .getPendingForUnity(
                            context
                        )
                }


            val jsonArray =
                JSONArray()


            workouts.forEach { workout ->

                val json =
                    JSONObject()


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


                /*
                 * nullable 값은 JSON null로 보낸다.
                 */
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
                val metricsArray =
                    JSONArray()


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


            Log.d(
                TAG,
                "Unity 전달 대기 운동 수: ${workouts.size}"
            )


            jsonArray.toString()

        } catch (e: Exception) {

            Log.e(
                TAG,
                "운동 기록 조회 실패",
                e
            )


            "[]"
        }
    }


    /*
     * Unity가 해당 운동을 게임에
     * 정상적으로 반영한 뒤 호출한다.
     */
    @JvmStatic
    fun markWorkoutConsumed(
        workoutId: String
    ): Boolean {

        val context =
            appContext
                ?: return false


        if (
            workoutId.isBlank()
        ) {
            return false
        }


        return try {

            runBlocking(
                Dispatchers.IO
            ) {

                WorkoutStorage
                    .markConsumed(
                        context,
                        workoutId
                    )
            }


            Log.d(
                TAG,
                "Unity 처리 완료: $workoutId"
            )


            true

        } catch (e: Exception) {

            Log.e(
                TAG,
                "Unity 처리 완료 저장 실패: $workoutId",
                e
            )


            false
        }
    }


    /*
     * 테스트 및 상태 확인용.
     *
     * 나중에 없어도 되지만 현재는 유용하다.
     */
    @JvmStatic
    fun getPendingWorkoutCount():
            Int {

        val context =
            appContext
                ?: return 0


        return try {

            runBlocking(
                Dispatchers.IO
            ) {

                WorkoutStorage
                    .getPendingForUnity(
                        context
                    )
                    .size
            }

        } catch (e: Exception) {

            Log.e(
                TAG,
                "Pending 운동 개수 조회 실패",
                e
            )


            0
        }
    }
}