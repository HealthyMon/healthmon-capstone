package com.healthmon.app.mobile.sync

import android.content.Context
import android.content.pm.ApplicationInfo
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.healthmon.app.mobile.data.local.HealthMonPhoneDatabase
import com.healthmon.app.mobile.data.local.WorkoutUploadEntity
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.TimeUnit

object ServerWorkoutSync {
    const val WORK_NAME = "healthmon.room-workout-upload.v1"
    private val http = SyncHttpClient()

    /** Call after Room commit, on app start, after binding and on manual sync.
     * APPEND_OR_REPLACE closes the "insert while previous worker finishes" race. */
    fun schedule(context: Context) {
        val request = OneTimeWorkRequestBuilder<WorkoutUploadWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
    }

    fun clear(context: Context) {
        ServerSyncSettings.clear(context)
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }

    /** Network calls are intentionally outside any Room transaction. */
    suspend fun configure(context: Context, baseUrl: String, bearer: String, petId: String): String {
        val attempt = ServerSyncSettings.clear(context)
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        // A failed/new login must never continue sending as the previous account.
        return try {
            val uri = URI(baseUrl.trim().trimEnd('/'))
            require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null)
            require(uri.host != null && (uri.path.isNullOrEmpty() || uri.path == "/"))
            val debug = context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
            require(uri.scheme == "https" || (uri.scheme == "http" && debug)) { "https_required" }
            require(bearer.isNotBlank() && !bearer.contains('\n') && !bearer.contains('\r'))
            require(petId.matches(Regex("[A-Za-z0-9_-]{1,128}")))
            val provisional = SyncDestination(uri.toString().trimEnd('/'), bearer, petId, "", "", "")
            val info = http.request(provisional, "/server-info")
            val identity = http.request(provisional, "/identity")
            if (identity.code == 401) {
                ServerSyncSettings.setAttemptStatus(context, attempt, "auth_required")
                return JSONObject().put("status", "auth_required").toString()
            }
            require(info.code == 200 && identity.code == 200) { "identity_lookup_failed" }
            val server = JSONObject(info.body)
            val owner = JSONObject(identity.body).getString("owner_id")
            val serverId = server.getString("server_instance_id")
            val environment = server.getString("environment")
            require(serverId.isNotBlank() && owner.isNotBlank() && environment.isNotBlank())
            // Pet selection is authorized by the server, not by a body owner_id claim.
            require(http.request(provisional, "/pets/$petId/state").code == 200) { "pet_access_denied" }
            val destination = provisional.copy(serverInstanceId = serverId, ownerId = owner, environment = environment)
            if (!ServerSyncSettings.save(context, destination, attempt))
                return JSONObject().put("status", "configuration_superseded").toString()
            HealthMonPhoneDatabase.getInstance(context).uploadDao().resumeAfterLogin(serverId, owner, petId)
            schedule(context)
            JSONObject().put("status", "ready").put("server_instance_id", serverId)
                .put("owner_id", owner).put("pet_id", petId).put("environment", environment).toString()
        } catch (_: Exception) {
            ServerSyncSettings.setAttemptStatus(context, attempt, "error")
            JSONObject().put("status", "error").put("message", "connection_or_configuration_invalid").toString()
        }
    }

    /** The UI must obtain a deliberate confirmation for THIS record and destination.
     * No bulk rebinding, no account-change heuristic, no reuse of another pet's upload flag. */
    suspend fun confirm(context: Context, workoutId: String): Boolean {
        val destination = ServerSyncSettings.load(context) ?: return false
        if (ServerSyncSettings.status(context) != "ready") return false
        val db = HealthMonPhoneDatabase.getInstance(context)
        if (db.workoutDao().getWorkout(workoutId) == null) return false
        val inserted = db.uploadDao().confirm(WorkoutUploadEntity(workoutId,
            destination.serverInstanceId, destination.ownerId, destination.petId,
            confirmedAt = System.currentTimeMillis()))
        if (inserted && ServerSyncSettings.current(context, destination)) schedule(context)
        return inserted
    }

    suspend fun status(context: Context): String {
        val destination = ServerSyncSettings.load(context)
        val result = JSONObject().put("status", ServerSyncSettings.status(context))
        if (destination == null) return result.put("unbound_count", 0)
            .put("unbound", JSONArray()).put("uploads", JSONArray()).toString()
        val dao = HealthMonPhoneDatabase.getInstance(context).uploadDao()
        val unbound = dao.unbound(destination.serverInstanceId, destination.ownerId)
        val uploads = dao.forDestination(destination.serverInstanceId, destination.ownerId, destination.petId)
        return result.put("server_instance_id", destination.serverInstanceId)
            .put("owner_id", destination.ownerId).put("pet_id", destination.petId)
            .put("environment", destination.environment).put("unbound_count", unbound.size)
            .put("unbound", JSONArray().apply {
                unbound.forEach { put(JSONObject().put("id", it.id).put("exercise", it.exerciseType)
                    .put("start_time", it.startTime).put("end_time", it.endTime)) }
            }).put("uploads", JSONArray().apply {
                uploads.forEach { put(JSONObject().put("workout_id", it.workoutId).put("status", it.status)
                    .put("last_http_status", it.lastHttpStatus ?: JSONObject.NULL)
                    .put("synced_at", it.syncedAt ?: JSONObject.NULL)) }
            }).toString()
    }
}
