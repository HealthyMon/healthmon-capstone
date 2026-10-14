package com.healthmon.app.mobile.wear

import android.util.Log

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.WearableListenerService
import com.google.android.gms.wearable.Wearable

import com.healthmon.app.mobile.data.local.WorkoutStorage
import com.healthmon.app.mobile.model.PhoneWorkoutResult

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class WorkoutDataLayerReceiver :
    WearableListenerService() {


    private val serviceScope =
        CoroutineScope(
            SupervisorJob() +
                    Dispatchers.IO
        )


    override fun onDataChanged(
        dataEvents: DataEventBuffer
    ) {

        super.onDataChanged(dataEvents)


        dataEvents.forEach { event ->

            /*
             * 생성/변경된 DataItem만 처리
             */
            if (
                event.type !=
                DataEvent.TYPE_CHANGED
            ) {
                return@forEach
            }


            val dataItem =
                event.dataItem


            val path =
                dataItem.uri.path
                    ?: return@forEach

            val resultUri =
                dataItem.uri
            /*
             * HealthMon 운동 결과만 처리
             */
            if (
                !path.startsWith(
                    WorkoutDataContract
                        .RESULT_PATH_PREFIX
                )
            ) {
                return@forEach
            }


            val dataMap =
                DataMapItem
                    .fromDataItem(
                        dataItem
                    )
                    .dataMap


            /*
             * 필수 데이터
             */
            val id =
                dataMap.getString(
                    WorkoutDataContract.KEY_ID
                )
                    ?: return@forEach


            val exercise =
                dataMap.getString(
                    WorkoutDataContract.KEY_EXERCISE
                )
                    ?: return@forEach


            val startTime =
                dataMap.getLong(
                    WorkoutDataContract.KEY_START_TIME
                )


            val endTime =
                dataMap.getLong(
                    WorkoutDataContract.KEY_END_TIME
                )


            val duration =
                dataMap.getLong(
                    WorkoutDataContract
                        .KEY_DURATION_SECONDS
                )


            /*
             * nullable 데이터
             */
            val averageHeartRate =
                if (
                    dataMap.containsKey(
                        WorkoutDataContract
                            .KEY_AVERAGE_HEART_RATE
                    )
                ) {

                    dataMap.getDouble(
                        WorkoutDataContract
                            .KEY_AVERAGE_HEART_RATE
                    )

                } else {

                    null
                }


            val maxHeartRate =
                if (
                    dataMap.containsKey(
                        WorkoutDataContract
                            .KEY_MAX_HEART_RATE
                    )
                ) {

                    dataMap.getDouble(
                        WorkoutDataContract
                            .KEY_MAX_HEART_RATE
                    )

                } else {

                    null
                }


            val calories =
                if (
                    dataMap.containsKey(
                        WorkoutDataContract
                            .KEY_CALORIES
                    )
                ) {

                    dataMap.getDouble(
                        WorkoutDataContract.KEY_CALORIES
                    )

                } else {

                    null
                }


            val steps =
                if (
                    dataMap.containsKey(
                        WorkoutDataContract
                            .KEY_STEPS
                    )
                ) {

                    dataMap.getLong(
                        WorkoutDataContract.KEY_STEPS
                    )

                } else {

                    null
                }


            val distance =
                if (
                    dataMap.containsKey(
                        WorkoutDataContract
                            .KEY_DISTANCE_KM
                    )
                ) {

                    dataMap.getDouble(
                        WorkoutDataContract
                            .KEY_DISTANCE_KM
                    )

                } else {

                    null
                }


            /*
             * 워치에서 지원했던 측정 항목 목록
             */
            val supportedMetrics =
                dataMap.getStringArrayList(
                    WorkoutDataContract
                        .KEY_SUPPORTED_METRICS
                )
                    ?.toList()
                    ?: emptyList()


            /*
             * 기록 출처
             */
            val source =
                dataMap.getString(
                    WorkoutDataContract.KEY_SOURCE
                )
                    ?: "WATCH_MANUAL"


            /*
             * 휴대폰에서 사용할 운동 결과 객체 생성
             */
            val result =
                PhoneWorkoutResult(

                    id =
                        id,

                    exercise =
                        exercise,

                    startTime =
                        startTime,

                    endTime =
                        endTime,

                    durationSeconds =
                        duration,

                    averageHeartRate =
                        averageHeartRate,

                    maxHeartRate =
                        maxHeartRate,

                    calories =
                        calories,

                    steps =
                        steps,

                    distanceKm =
                        distance,

                    supportedMetrics =
                        supportedMetrics,

                    source =
                        source
                )

            /*
            Log.d(
                TAG,
                "워치 운동 기록 수신: " +
                        "id=$id, " +
                        "exercise=$exercise, " +
                        "duration=${duration}s, " +
                        "avgHR=$averageHeartRate, " +
                        "maxHR=$maxHeartRate, " +
                        "calories=$calories, " +
                        "steps=$steps, " +
                        "distance=$distance"
            )
             */

            serviceScope.launch {

                try {

                    WorkoutStorage.save(
                        applicationContext,
                        result
                    )


                    //Log.d(TAG, "휴대폰 Room 저장 성공: ${result.id}")


                    /*
                     * Room 저장이 성공한 경우에만
                     * ACK 생성
                     */
                    val ackSuccess =
                        WorkoutAckSender.send(
                            applicationContext,
                            result.id
                        )


                    if (ackSuccess) {

                        //Log.d(TAG, "워치 ACK 등록 성공: ${result.id}")

                        val deletedCount =
                            Wearable
                                .getDataClient(
                                    applicationContext
                                )
                                .deleteDataItems(
                                    resultUri
                                )
                                .await()


                        //Log.d(TAG, "Workout Result DataItem 삭제 완료: " + "id=${result.id}, " + "count=$deletedCount")

                    } else {
                        Log.e(TAG, "워치 ACK 등록 실패: ${result.id}")
                    }


                    val workouts =
                        WorkoutStorage.getAll(
                            applicationContext
                        )


                    //Log.d(TAG, "휴대폰 Room 전체 기록 수: ${workouts.size}")

                } catch (e: Exception) {
                    Log.e(TAG, "휴대폰 Room 저장 실패: ${result.id}", e)
                }
            }
        }
    }


    override fun onDestroy() {
        serviceScope.cancel()

        super.onDestroy()
    }


    companion object {
        private const val TAG = "HealthMonPhoneReceiver"
    }
}