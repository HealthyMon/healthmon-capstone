package com.healthmon.capstone.mobile.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.healthmon.capstone.mobile.data.local.HealthMonPhoneDatabase
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

class WorkoutUploadWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val destination = ServerSyncSettings.load(applicationContext) ?: return@withContext Result.success()
        if (ServerSyncSettings.status(applicationContext) != "ready") return@withContext Result.success()
        val dao = HealthMonPhoneDatabase.getInstance(applicationContext).uploadDao()
        val http = SyncHttpClient()
        try {
            // Detect DNS/address reuse by another DB and verify account before touching its queue.
            val info = http.request(destination, "/server-info")
            if (info.code != 200) return@withContext Result.retry()
            if (JSONObject(info.body).getString("server_instance_id") != destination.serverInstanceId) {
                ServerSyncSettings.setCurrentStatus(applicationContext, destination, "server_changed")
                return@withContext Result.success()
            }
            val identity = http.request(destination, "/identity")
            if (identity.code == 401) {
                pauseForAuthentication(destination)
                return@withContext Result.success()
            }
            if (identity.code != 200) return@withContext Result.retry()
            if (JSONObject(identity.body).getString("owner_id") != destination.ownerId) {
                ServerSyncSettings.setCurrentStatus(applicationContext, destination, "identity_changed")
                return@withContext Result.success()
            }
            val pending = dao.forDestination(destination.serverInstanceId, destination.ownerId, destination.petId)
                .filter { it.status == "pending" }
            var retry = false
            for (upload in pending) {
                if (isStopped || !ServerSyncSettings.current(applicationContext, destination)) return@withContext Result.success()
                val workout = HealthMonPhoneDatabase.getInstance(applicationContext).workoutDao().getWorkout(upload.workoutId)
                    ?: continue
                val payload = try { WorkoutUploadPolicy.payload(workout) } catch (_: IllegalArgumentException) {
                    dao.setResult(upload.workoutId, destination.serverInstanceId, destination.ownerId, destination.petId,
                        "needs_correction", null, null)
                    continue
                }
                val response = http.request(destination, "/pets/${destination.petId}/workouts", payload)
                val outcome = WorkoutUploadPolicy.outcome(response.code,
                    WorkoutUploadPolicy.acknowledged(response.body, workout.id))
                when (outcome) {
                    WorkoutUploadPolicy.Outcome.SYNCED -> dao.setResult(upload.workoutId, destination.serverInstanceId,
                        destination.ownerId, destination.petId, "synced", System.currentTimeMillis(), response.code)
                    WorkoutUploadPolicy.Outcome.AUTH_REQUIRED -> {
                        pauseForAuthentication(destination)
                        return@withContext Result.success()
                    }
                    WorkoutUploadPolicy.Outcome.NEEDS_CORRECTION -> dao.setResult(upload.workoutId, destination.serverInstanceId,
                        destination.ownerId, destination.petId, "needs_correction", null, response.code)
                    WorkoutUploadPolicy.Outcome.RETRY -> {
                        dao.setResult(upload.workoutId, destination.serverInstanceId, destination.ownerId,
                            destination.petId, "pending", null, response.code)
                        retry = true
                    }
                }
            }
            if (retry) Result.retry() else Result.success()
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { Result.retry() }
    }

    private suspend fun pauseForAuthentication(destination: SyncDestination) {
        val dao = HealthMonPhoneDatabase.getInstance(applicationContext).uploadDao()
        dao.forDestination(destination.serverInstanceId, destination.ownerId, destination.petId)
            .filter { it.status == "pending" }.forEach {
                dao.setResult(it.workoutId, destination.serverInstanceId, destination.ownerId,
                    destination.petId, "auth_required", null, 401)
            }
        ServerSyncSettings.setCurrentStatus(applicationContext, destination, "auth_required")
    }
}
