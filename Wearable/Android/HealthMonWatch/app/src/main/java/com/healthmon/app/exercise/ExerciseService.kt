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

import androidx.health.services.client.clearUpdateCallback
import androidx.health.services.client.endExercise
import androidx.health.services.client.ExerciseUpdateCallback
import androidx.health.services.client.getCapabilities
import androidx.health.services.client.HealthServices
import androidx.health.services.client.startExercise

import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.ExerciseConfig
import androidx.health.services.client.data.ExerciseLapSummary
import androidx.health.services.client.data.ExerciseState
import androidx.health.services.client.data.ExerciseUpdate

import com.healthmon.app.data.local.WorkoutStorage
import com.healthmon.app.data.transfer.WorkoutDataLayerSender
import com.healthmon.app.data.WorkoutRepository
import com.healthmon.app.model.LiveWorkoutState
import com.healthmon.app.model.LiveWorkoutStatus
import com.healthmon.app.model.WorkoutMetric
import com.healthmon.app.model.WorkoutResult
import com.healthmon.app.model.WorkoutType
import com.healthmon.app.R
import com.healthmon.app.data.transfer.LiveWorkoutMessageSender
import com.healthmon.app.data.transfer.LiveWorkoutRequestDispatcher

import kotlinx.coroutines.cancel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.SupervisorJob

import java.util.UUID


class ExerciseService : Service() {
    private val serviceScope = CoroutineScope(
            SupervisorJob() + Dispatchers.Main.immediate
        )
    private val exerciseClient by lazy {
        HealthServices.getClient(this).exerciseClient
    }
    private var currentWorkoutType: WorkoutType? = null
    private var currentStartTimeMillis: Long? = null
    private var currentSessionId: String? = null
    private var liveSnapshotJob: Job? = null
    private var liveSequence: Long = 0L

    private val exerciseUpdateCallback = object : ExerciseUpdateCallback {
            override fun onExerciseUpdateReceived(update: ExerciseUpdate) {
                val metrics = update.latestMetrics

                val heartRate = metrics
                        .getData(DataType.HEART_RATE_BPM)
                        .lastOrNull()?.value
                val heartRateStats = metrics
                        .getData(DataType.HEART_RATE_BPM_STATS)
                val averageHeartRate = heartRateStats
                        ?.average
                val maxHeartRate = heartRateStats
                        ?.max

                val steps = metrics
                        .getData(DataType.STEPS_TOTAL)
                        ?.total
                val calories = metrics
                        .getData(DataType.CALORIES_TOTAL)
                        ?.total
                val distance = metrics
                        .getData(DataType.DISTANCE_TOTAL)
                        ?.total

                val state = update
                        .exerciseStateInfo
                        .state
                val checkpoint = update
                    .activeDurationCheckpoint

                update.startTime?.let {
                    currentStartTimeMillis = it.toEpochMilli()
                }

                WorkoutRepository.updateTimer(
                    checkpointTimeMillis = checkpoint
                            ?.time
                            ?.toEpochMilli(),
                    activeDurationMillis = checkpoint
                            ?.activeDuration
                            ?.toMillis(),
                    isActive = state == ExerciseState.ACTIVE
                )

                WorkoutRepository.updateMetrics(
                    heartRate = heartRate,
                    averageHeartRate = averageHeartRate,
                    maxHeartRate = maxHeartRate,

                    steps = steps,
                    calories = calories,
                    distanceMeters = distance
                )
/*
                Log.d(
                    TAG,
                    "state=$state, " +
                            "HR=$heartRate, " +
                            "Steps=$steps, " +
                            "Calories=$calories, " +
                            "Distance=$distance"
                )
*/
                if (state == ExerciseState.ENDED) {
                    //Log.d(TAG, "운동 종료 완료")

                    stopLiveSnapshotLoop()
                    emitLiveWorkoutState(LiveWorkoutStatus.ENDED)

                    val workoutType = currentWorkoutType

                    val result =
                        if (workoutType != null) {
                            val finalState = WorkoutRepository
                                    .getCurrentState()

                            WorkoutResult(
                                id = currentSessionId ?: UUID.randomUUID().toString(),
                                exercise = workoutType,

                                startTime = currentStartTimeMillis ?: System.currentTimeMillis(),
                                endTime = System.currentTimeMillis(),
                                durationSeconds = finalState
                                        .getActiveDurationMillis()
                                        .div(1000),

                                averageHeartRate = finalState.averageHeartRate,
                                maxHeartRate = finalState.maxHeartRate,
                                calories = finalState.calories,
                                steps = finalState.steps,
                                distanceKm = finalState.distanceKm,

                                supportedMetrics = finalState.supportedMetrics
                            )
                        } else {
                            null
                        }

                    val callback = this

                    serviceScope.launch {
                        try {
                             //1. Room에 운동 기록 저장
                            if (result != null) {
                                WorkoutStorage.save(
                                    context = this@ExerciseService,
                                    result = result
                                )

                               //Log.d(TAG, "Room 저장 성공: ${result.id}")

                                WorkoutDataLayerSender
                                    .sendPendingWorkouts(this@ExerciseService)

                                //2. 저장이 끝난 뒤 결과 화면으로 전달
                                WorkoutRepository.completeWorkout(result)
                            }
                            //3. Health Services callback 제거
                            exerciseClient.clearUpdateCallback(callback)

                            //Log.d(TAG, "ExerciseUpdateCallback 제거 완료")
                        } catch (e: Exception) {
                            Log.e(TAG, "운동 종료 처리 실패", e)
                            //Room 저장 실패가 발생해도 결과 화면 자체는 보여준다.
                            if (result != null) {
                                WorkoutRepository
                                    .completeWorkout(result)
                            }
                        } finally {
                            stopLiveSnapshotLoop()

                            currentSessionId = null
                            currentWorkoutType = null
                            currentStartTimeMillis = null

                            stopForeground(STOP_FOREGROUND_REMOVE)
                            stopSelf()
                        }
                    }
                }
            }

            override fun onAvailabilityChanged(dataType: DataType<*, *>, availability: Availability) {
                //Log.d(TAG, "$dataType availability = $availability")
            }

            override fun onLapSummaryReceived(lapSummary: ExerciseLapSummary) {
                // 현재는 랩 기능 사용 안 함
            }

            override fun onRegistered() {
                //Log.d(TAG, "ExerciseUpdateCallback 등록 성공")
            }

            override fun onRegistrationFailed(throwable: Throwable) {
                Log.e(TAG, "ExerciseUpdateCallback 등록 실패", throwable)
            }
        }

    private suspend fun startTrackedExercise(workoutType: WorkoutType) {
        try {
            WorkoutRepository.reset()

            currentWorkoutType = workoutType
            currentSessionId = UUID.randomUUID().toString()
            liveSequence = 0L

            //Log.d("HealthMonExercise", "운동 세션 생성: $currentSessionId")

            val healthExerciseType = workoutType.toHealthServicesType()

            val capabilities = exerciseClient.getCapabilities()

            if (healthExerciseType !in capabilities.supportedExerciseTypes) {
                Log.e(TAG, "지원하지 않는 운동: $healthExerciseType")

                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()

                return
            }

            val exerciseCapabilities = capabilities
                    .getExerciseTypeCapabilities(healthExerciseType)

            val wantedDataTypes: Set<DataType<*, *>> =
                setOf(
                    DataType.HEART_RATE_BPM,
                    DataType.HEART_RATE_BPM_STATS,
                    DataType.STEPS_TOTAL,
                    DataType.CALORIES_TOTAL,
                    DataType.DISTANCE_TOTAL
                )


            val requestedDataTypes = wantedDataTypes
                .intersect(
                    exerciseCapabilities
                        .supportedDataTypes
                )

            val supportedMetrics =
                buildSet {
                    if (DataType.HEART_RATE_BPM in requestedDataTypes) {
                        add(WorkoutMetric.HEART_RATE)
                    }

                    if (DataType.CALORIES_TOTAL in requestedDataTypes) {
                        add(WorkoutMetric.CALORIES)
                    }

                    if (DataType.STEPS_TOTAL in requestedDataTypes) {
                        add(WorkoutMetric.STEPS)
                    }

                    if (DataType.DISTANCE_TOTAL in requestedDataTypes) {
                        add(WorkoutMetric.DISTANCE)
                    }
                }

            WorkoutRepository.setSupportedMetrics(
                supportedMetrics
            )

            //Log.d(TAG, "요청할 데이터: $requestedDataTypes")

            val config = ExerciseConfig(
                    exerciseType = healthExerciseType,
                    dataTypes = requestedDataTypes,
                    isAutoPauseAndResumeEnabled = false,
                    isGpsEnabled = false
                )

            // 운동 시작 전에 callback 등록
            exerciseClient.setUpdateCallback(exerciseUpdateCallback)
            exerciseClient.startExercise(config)

            //Log.d(TAG, "운동 시작 성공: $workoutType")

            emitLiveWorkoutState(LiveWorkoutStatus.STARTED)
            startLiveSnapshotLoop()
        } catch (e: Exception) {
            Log.e(TAG, "운동 시작 실패", e)

            currentSessionId = null
            currentWorkoutType = null
            currentStartTimeMillis = null


            stopForeground(
                STOP_FOREGROUND_REMOVE
            )

            stopSelf()
        }
    }

    private suspend fun endTrackedExercise() {
        try {
            //호출 즉시 서비스를 죽이지 않음.
            //최종 ExerciseState.ENDED가 callback으로 들어올 때까지 기다린다.
            emitLiveWorkoutState(LiveWorkoutStatus.ENDING)
            exerciseClient.endExercise()

            //Log.d(TAG, "운동 종료 요청 완료")
        } catch (e: Exception) {
            Log.e(TAG, "운동 종료 요청 실패", e)
        }
    }

    private fun startAsForeground() {
        val notification = NotificationCompat
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

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
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

    @Synchronized
    private fun createLiveWorkoutState(status: LiveWorkoutStatus): LiveWorkoutState? {
        val sessionId = currentSessionId ?: return null
        val workoutType = currentWorkoutType ?: return null

        val state = WorkoutRepository.getCurrentState()

        liveSequence++

        return LiveWorkoutState(
            sessionId = sessionId,
            exercise = workoutType,
            status = status,

            durationSeconds =
                state.getActiveDurationMillis() / 1000,

            heartRate = state.heartRate,
            averageHeartRate = state.averageHeartRate,
            maxHeartRate = state.maxHeartRate,

            calories = state.calories,
            steps = state.steps,
            distanceKm = state.distanceKm,

            timestamp = System.currentTimeMillis(),
            sequence = liveSequence
        )
    }

    private fun emitLiveWorkoutState(status: LiveWorkoutStatus) {
        val state = createLiveWorkoutState(status) ?: return

        Log.d(
            LIVE_TAG,
            "session=${state.sessionId}, " +
                    "sequence=${state.sequence}, " +
                    "status=${state.status}, " +
                    "duration=${state.durationSeconds}s, " +
                    "HR=${state.heartRate}, " +
                    "avgHR=${state.averageHeartRate}, " +
                    "maxHR=${state.maxHeartRate}, " +
                    "calories=${state.calories}, " +
                    "steps=${state.steps}, " +
                    "distance=${state.distanceKm}"
        )

        serviceScope.launch {
            LiveWorkoutMessageSender.send(
                this@ExerciseService,
                state
            )
        }
    }

    private fun startLiveSnapshotLoop() {
        liveSnapshotJob?.cancel()

        liveSnapshotJob = serviceScope.launch {
            var lastTick = android.os.SystemClock.elapsedRealtime()
            try {
                while (isActive) {
                    delay(1000)

                    val now = android.os.SystemClock.elapsedRealtime()
                    val gap = now - lastTick
                    lastTick = now

                    Log.d("HM_TEST", "TICK gap=${gap}ms")

                    emitLiveWorkoutState(
                        LiveWorkoutStatus.ACTIVE
                    )
                }
            } finally {
                Log.d("HM_TEST", "LOOP_END")
            }
        }
    }

    private fun stopLiveSnapshotLoop() {
        liveSnapshotJob?.cancel()
        liveSnapshotJob = null
    }

    override fun onCreate() {
        super.onCreate()

        createNotificationChannel()
        LiveWorkoutRequestDispatcher.register {
            serviceScope.launch {
                if (currentSessionId != null && currentWorkoutType != null) {
                    //Log.d(TAG, "현재 운동 상태 재전송 요청 처리")

                    emitLiveWorkoutState(LiveWorkoutStatus.ACTIVE)
                }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                //ForegroundService는 빠르게 startForeground 상태로 전환해야 함
                startAsForeground()

                val workoutTypeName = intent
                    .getStringExtra(EXTRA_WORKOUT_TYPE)

                val workoutType =
                    try {
                        WorkoutType.valueOf(
                            workoutTypeName ?: WorkoutType.WALKING.name
                        )
                    } catch (e: Exception) {
                        WorkoutType.WALKING
                    }

                serviceScope.launch {
                    startTrackedExercise(workoutType)
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

    override fun onDestroy() {
        serviceScope.cancel()
        LiveWorkoutRequestDispatcher.unregister()

        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    companion object {
        private const val TAG = "HealthMonExercise"
        private const val LIVE_TAG = "HealthMonLive"
        private const val CHANNEL_ID = "healthmon_exercise"
        private const val NOTIFICATION_ID = 1001

        private const val ACTION_START = "com.healthmon.app.START_EXERCISE"
        private const val ACTION_END = "com.healthmon.app.END_EXERCISE"
        private const val EXTRA_WORKOUT_TYPE = "workout_type"

        fun start(context: Context, workoutType: WorkoutType) {
            val intent = Intent(context, ExerciseService::class.java).apply {
                    action = ACTION_START

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

        fun end(context: Context) {
            val intent =
                Intent(
                    context,
                    ExerciseService::class.java
                ).apply {
                    action = ACTION_END
                }

            context.startService(
                intent
            )
        }
    }
}