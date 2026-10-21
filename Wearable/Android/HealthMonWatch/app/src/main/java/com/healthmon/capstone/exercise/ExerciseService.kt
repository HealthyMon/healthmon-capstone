package com.healthmon.capstone.exercise

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
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
import androidx.wear.ongoing.OngoingActivity

import com.healthmon.capstone.data.local.WorkoutStorage
import com.healthmon.capstone.data.transfer.WorkoutDataLayerSender
import com.healthmon.capstone.data.WorkoutRepository
import com.healthmon.capstone.model.LiveWorkoutState
import com.healthmon.capstone.model.LiveWorkoutStatus
import com.healthmon.capstone.model.WorkoutMetric
import com.healthmon.capstone.model.WorkoutResult
import com.healthmon.capstone.model.WorkoutType
import com.healthmon.capstone.R
import com.healthmon.capstone.data.transfer.LiveWorkoutMessageSender
import com.healthmon.capstone.data.transfer.LiveWorkoutRequestDispatcher
import com.healthmon.capstone.presentation.MainActivity

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

                if (state == ExerciseState.ENDED) {
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

                            WorkoutRepository.clearActiveWorkout()

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

            val healthExerciseType = workoutType.toHealthServicesType()

            val capabilities = exerciseClient.getCapabilities()

            if (healthExerciseType !in capabilities.supportedExerciseTypes) {
                Log.w(TAG, "지원하지 않는 운동: $healthExerciseType")

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

            val config = ExerciseConfig(
                    exerciseType = healthExerciseType,
                    dataTypes = requestedDataTypes,
                    isAutoPauseAndResumeEnabled = false,
                    isGpsEnabled = false
                )

            exerciseClient.setUpdateCallback(exerciseUpdateCallback)
            exerciseClient.startExercise(config)
            WorkoutRepository.setActiveWorkout(workoutType)
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

            WorkoutRepository.clearActiveWorkout()
        }
    }

    private suspend fun endTrackedExercise() {
        try {
            stopLiveSnapshotLoop()

            emitLiveWorkoutState(LiveWorkoutStatus.ENDING)
            exerciseClient.endExercise()

        } catch (e: Exception) {
            Log.e(TAG, "운동 종료 요청 실패", e)
        }
    }

    private fun startAsForeground() {
        val openAppIntent = Intent(this, MainActivity::class.java)
            .apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP
            }

        val pendingIntent = PendingIntent
            .getActivity(this, 0, openAppIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or
                        PendingIntent.FLAG_IMMUTABLE
            )

        val notificationBuilder = NotificationCompat
                .Builder(this, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("헬스몬 운동 기록")
                .setContentText("운동 데이터를 측정하고 있습니다.")
                .setCategory(NotificationCompat.CATEGORY_WORKOUT)
                .setContentIntent(pendingIntent)
                .setOngoing(true)

        val ongoingActivity = OngoingActivity.Builder(
                this,
                NOTIFICATION_ID,
                notificationBuilder
            )
                .setTouchIntent(
                    pendingIntent
                )
                .build()

        ongoingActivity.apply(this)

        val notification = notificationBuilder.build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            )
        } else {
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
            while (isActive) {
                delay(1000)
                emitLiveWorkoutState(LiveWorkoutStatus.ACTIVE)
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

        return START_NOT_STICKY
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
        private const val CHANNEL_ID = "healthmon_exercise"
        private const val NOTIFICATION_ID = 1001

        private const val ACTION_START = "com.healthmon.capstone.START_EXERCISE"
        private const val ACTION_END = "com.healthmon.capstone.END_EXERCISE"
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