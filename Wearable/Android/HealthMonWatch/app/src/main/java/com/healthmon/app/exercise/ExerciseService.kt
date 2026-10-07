package com.healthmon.app.exercise

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log

import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

import androidx.health.services.client.ExerciseUpdateCallback
import androidx.health.services.client.HealthServices
import androidx.health.services.client.clearUpdateCallback
import androidx.health.services.client.endExercise
import androidx.health.services.client.getCapabilities
import androidx.health.services.client.startExercise

import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.ExerciseConfig
import androidx.health.services.client.data.ExerciseLapSummary
import androidx.health.services.client.data.ExerciseState
import androidx.health.services.client.data.ExerciseUpdate

import com.healthmon.app.R
import com.healthmon.app.model.WorkoutMetric
import com.healthmon.app.model.WorkoutType
import com.healthmon.app.data.WorkoutRepository
import com.healthmon.app.model.WorkoutResult
import com.healthmon.app.data.local.WorkoutStorage
import com.healthmon.app.data.transfer.WorkoutDataLayerSender

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.util.UUID


class ExerciseService : Service() {
    private val serviceScope =
        CoroutineScope(
            SupervisorJob() +
                    Dispatchers.Main.immediate
        )
    private val exerciseClient by lazy {

        HealthServices
            .getClient(this)
            .exerciseClient
    }
    private var currentWorkoutType:
            WorkoutType? = null
    private var currentStartTimeMillis:
            Long? = null

    /*
     * Health Services가 운동 데이터를 보내는 callback
     */
    private val exerciseUpdateCallback =
        object : ExerciseUpdateCallback {

            override fun onExerciseUpdateReceived(
                update: ExerciseUpdate
            ) {
                val metrics = update.latestMetrics
                // 현재 심박수
                val heartRate =
                    metrics
                        .getData(
                            DataType.HEART_RATE_BPM
                        )
                        .lastOrNull()
                        ?.value
                val heartRateStats =
                    metrics
                        .getData(
                            DataType.HEART_RATE_BPM_STATS
                        )

                val averageHeartRate =
                    heartRateStats
                        ?.average


                val maxHeartRate =
                    heartRateStats
                        ?.max

                // 운동 시작 이후 누적 걸음 수
                val steps =
                    metrics
                        .getData(
                            DataType.STEPS_TOTAL
                        )
                        ?.total


                // 운동 시작 이후 누적 칼로리
                val calories =
                    metrics
                        .getData(
                            DataType.CALORIES_TOTAL
                        )
                        ?.total


                // 운동 시작 이후 누적 거리(m)
                val distance =
                    metrics
                        .getData(
                            DataType.DISTANCE_TOTAL
                        )
                        ?.total

                val state =
                    update
                        .exerciseStateInfo
                        .state
                val checkpoint =
                    update.activeDurationCheckpoint

                update.startTime?.let {

                    currentStartTimeMillis =
                        it.toEpochMilli()
                }

                WorkoutRepository.updateTimer(

                    checkpointTimeMillis =
                        checkpoint
                            ?.time
                            ?.toEpochMilli(),

                    activeDurationMillis =
                        checkpoint
                            ?.activeDuration
                            ?.toMillis(),

                    isActive =
                        state == ExerciseState.ACTIVE
                )

                WorkoutRepository.updateMetrics(
                    heartRate =
                        heartRate,

                    averageHeartRate =
                        averageHeartRate,

                    maxHeartRate =
                        maxHeartRate,

                    steps =
                        steps,

                    calories =
                        calories,

                    distanceMeters =
                        distance
                )

                Log.d(
                    TAG,
                    "state=$state, " +
                            "HR=$heartRate, " +
                            "Steps=$steps, " +
                            "Calories=$calories, " +
                            "Distance=$distance"
                )


                /*
                 * 운동이 완전히 끝난 뒤에만
                 * Foreground Service 종료
                 */
                if (
                    state == ExerciseState.ENDED
                ) {

                    Log.d(
                        TAG,
                        "운동 종료 완료"
                    )


                    val workoutType =
                        currentWorkoutType


                    val result =
                        if (workoutType != null) {

                            val finalState =
                                WorkoutRepository
                                    .getCurrentState()


                            WorkoutResult(

                                id =
                                    UUID
                                        .randomUUID()
                                        .toString(),

                                exercise =
                                    workoutType,

                                startTime =
                                    currentStartTimeMillis
                                        ?: System.currentTimeMillis(),

                                endTime =
                                    System.currentTimeMillis(),

                                durationSeconds =
                                    finalState
                                        .getActiveDurationMillis()
                                        .div(1000),

                                averageHeartRate =
                                    finalState.averageHeartRate,

                                maxHeartRate =
                                    finalState.maxHeartRate,

                                calories =
                                    finalState.calories,

                                steps =
                                    finalState.steps,

                                distanceKm =
                                    finalState.distanceKm,

                                supportedMetrics =
                                    finalState.supportedMetrics
                            )

                        } else {

                            null
                        }


                    val callback =
                        this


                    serviceScope.launch {

                        try {

                            /*
                             * 1. Room에 운동 기록 저장
                             */
                            if (result != null) {

                                WorkoutStorage.save(
                                    context =
                                        this@ExerciseService,

                                    result =
                                        result
                                )


                                Log.d(
                                    TAG,
                                    "Room 저장 성공: ${result.id}"
                                )

                                WorkoutDataLayerSender
                                    .sendPendingWorkouts(
                                        this@ExerciseService
                                    )

                                /*
                                 * 2. 저장이 끝난 뒤
                                 * 결과 화면으로 전달
                                 */
                                WorkoutRepository
                                    .completeWorkout(
                                        result
                                    )
                            }


                            /*
                             * 3. Health Services callback 제거
                             */
                            exerciseClient
                                .clearUpdateCallback(
                                    callback
                                )


                            Log.d(
                                TAG,
                                "ExerciseUpdateCallback 제거 완료"
                            )


                        } catch (e: Exception) {

                            Log.e(
                                TAG,
                                "운동 종료 처리 실패",
                                e
                            )


                            /*
                             * Room 저장 실패가 발생해도
                             * 결과 화면 자체는 보여준다.
                             */
                            if (
                                result != null
                            ) {

                                WorkoutRepository
                                    .completeWorkout(
                                        result
                                    )
                            }


                        } finally {

                            stopForeground(
                                STOP_FOREGROUND_REMOVE
                            )

                            stopSelf()
                        }
                    }
                }
            }


            override fun onAvailabilityChanged(
                dataType: DataType<*, *>,
                availability: Availability
            ) {

                Log.d(
                    TAG,
                    "$dataType availability = $availability"
                )
            }


            override fun onLapSummaryReceived(
                lapSummary: ExerciseLapSummary
            ) {
                // 현재는 랩 기능 사용 안 함
            }


            override fun onRegistered() {

                Log.d(
                    TAG,
                    "ExerciseUpdateCallback 등록 성공"
                )
            }


            override fun onRegistrationFailed(
                throwable: Throwable
            ) {

                Log.e(
                    TAG,
                    "ExerciseUpdateCallback 등록 실패",
                    throwable
                )
            }
        }


    override fun onCreate() {

        super.onCreate()

        createNotificationChannel()
    }


    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int
    ): Int {

        when (intent?.action) {

            ACTION_START -> {

                /*
                 * ForegroundService는 빠르게
                 * startForeground 상태로 전환해야 함
                 */
                startAsForeground()


                val workoutTypeName =
                    intent.getStringExtra(
                        EXTRA_WORKOUT_TYPE
                    )


                val workoutType =
                    try {

                        WorkoutType.valueOf(
                            workoutTypeName
                                ?: WorkoutType.WALKING.name
                        )

                    } catch (e: Exception) {

                        WorkoutType.WALKING
                    }


                serviceScope.launch {

                    startTrackedExercise(
                        workoutType
                    )
                }
            }


            ACTION_END -> {

                serviceScope.launch {

                    endTrackedExercise()
                }
            }
        }


        return START_STICKY
    }


    private suspend fun startTrackedExercise(
        workoutType: WorkoutType
    ) {
        try {
            WorkoutRepository.reset()
            currentWorkoutType = workoutType

            val healthExerciseType =
                workoutType.toHealthServicesType()


            val capabilities =
                exerciseClient.getCapabilities()


            if (
                healthExerciseType !in
                capabilities.supportedExerciseTypes
            ) {

                Log.e(
                    TAG,
                    "지원하지 않는 운동: $healthExerciseType"
                )

                stopForeground(
                    STOP_FOREGROUND_REMOVE
                )

                stopSelf()

                return
            }


            val exerciseCapabilities =
                capabilities
                    .getExerciseTypeCapabilities(
                        healthExerciseType
                    )


            val wantedDataTypes:
                    Set<DataType<*, *>> =
                setOf(
                    DataType.HEART_RATE_BPM,
                    DataType.HEART_RATE_BPM_STATS,
                    DataType.STEPS_TOTAL,
                    DataType.CALORIES_TOTAL,
                    DataType.DISTANCE_TOTAL
                )


            val requestedDataTypes =
                wantedDataTypes.intersect(
                    exerciseCapabilities
                        .supportedDataTypes
                )

            val supportedMetrics =
                buildSet {

                    if (
                        DataType.HEART_RATE_BPM
                        in requestedDataTypes
                    ) {

                        add(
                            WorkoutMetric.HEART_RATE
                        )
                    }


                    if (
                        DataType.CALORIES_TOTAL
                        in requestedDataTypes
                    ) {

                        add(
                            WorkoutMetric.CALORIES
                        )
                    }


                    if (
                        DataType.STEPS_TOTAL
                        in requestedDataTypes
                    ) {

                        add(
                            WorkoutMetric.STEPS
                        )
                    }


                    if (
                        DataType.DISTANCE_TOTAL
                        in requestedDataTypes
                    ) {

                        add(
                            WorkoutMetric.DISTANCE
                        )
                    }
                }


            WorkoutRepository.setSupportedMetrics(
                supportedMetrics
            )

            Log.d(
                TAG,
                "요청할 데이터: $requestedDataTypes"
            )


            val config =
                ExerciseConfig(
                    exerciseType =
                        healthExerciseType,

                    dataTypes =
                        requestedDataTypes,

                    isAutoPauseAndResumeEnabled =
                        false,

                    isGpsEnabled =
                        false
                )


            // 운동 시작 전에 callback 등록
            exerciseClient
                .setUpdateCallback(
                    exerciseUpdateCallback
                )


            exerciseClient
                .startExercise(
                    config
                )


            Log.d(
                TAG,
                "운동 시작 성공: $workoutType"
            )

        } catch (e: Exception) {

            Log.e(
                TAG,
                "운동 시작 실패",
                e
            )

            stopForeground(
                STOP_FOREGROUND_REMOVE
            )

            stopSelf()
        }
    }

    private suspend fun endTrackedExercise() {

        try {

            /*
             * 호출 즉시 서비스를 죽이지 않음.
             *
             * 최종 ExerciseState.ENDED가
             * callback으로 들어올 때까지 기다린다.
             */
            exerciseClient
                .endExercise()


            Log.d(
                TAG,
                "운동 종료 요청 완료"
            )

        } catch (e: Exception) {

            Log.e(
                TAG,
                "운동 종료 요청 실패",
                e
            )
        }
    }


    private fun startAsForeground() {

        val notification =
            NotificationCompat
                .Builder(
                    this,
                    CHANNEL_ID
                )
                .setSmallIcon(
                    R.mipmap.ic_launcher
                )
                .setContentTitle(
                    "헬스몬 운동 기록"
                )
                .setContentText(
                    "운동 데이터를 측정하고 있습니다."
                )
                .setOngoing(true)
                .build()


        if (
            Build.VERSION.SDK_INT >=
            Build.VERSION_CODES.UPSIDE_DOWN_CAKE
        ) {

            // Android 14(API 34) 이상
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            )

        } else {

            // Android 13 이하
            startForeground(
                NOTIFICATION_ID,
                notification
            )
        }
    }


    private fun createNotificationChannel() {

        val channel =
            NotificationChannel(
                CHANNEL_ID,
                "운동 기록",
                NotificationManager
                    .IMPORTANCE_LOW
            )


        val notificationManager =
            getSystemService(
                NotificationManager::class.java
            )


        notificationManager
            .createNotificationChannel(
                channel
            )
    }


    override fun onDestroy() {

        /*
         * Callback 제거 요청
         */
        serviceScope.cancel()

        super.onDestroy()
    }


    override fun onBind(
        intent: Intent?
    ): IBinder? {

        return null
    }


    companion object {

        private const val TAG =
            "HealthMonExercise"

        private const val CHANNEL_ID =
            "healthmon_exercise"

        private const val NOTIFICATION_ID =
            1001


        private const val ACTION_START =
            "com.healthmon.app.START_EXERCISE"

        private const val ACTION_END =
            "com.healthmon.app.END_EXERCISE"

        private const val EXTRA_WORKOUT_TYPE =
            "workout_type"


        fun start(
            context: Context,
            workoutType: WorkoutType
        ) {

            val intent =
                Intent(
                    context,
                    ExerciseService::class.java
                ).apply {

                    action =
                        ACTION_START

                    putExtra(
                        EXTRA_WORKOUT_TYPE,
                        workoutType.name
                    )
                }


            ContextCompat
                .startForegroundService(
                    context,
                    intent
                )
        }


        fun end(
            context: Context
        ) {

            val intent =
                Intent(
                    context,
                    ExerciseService::class.java
                ).apply {

                    action =
                        ACTION_END
                }


            context.startService(
                intent
            )
        }
    }
}