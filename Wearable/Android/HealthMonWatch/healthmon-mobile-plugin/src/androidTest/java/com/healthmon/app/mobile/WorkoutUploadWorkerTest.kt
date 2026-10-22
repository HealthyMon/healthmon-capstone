package com.healthmon.app.mobile

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.ListenableWorker
import androidx.work.testing.TestListenableWorkerBuilder
import com.healthmon.app.mobile.data.local.HealthMonPhoneDatabase
import com.healthmon.app.mobile.data.local.WorkoutEntity
import com.healthmon.app.mobile.data.local.WorkoutUploadEntity
import com.healthmon.app.mobile.sync.ServerSyncSettings
import com.healthmon.app.mobile.sync.ServerWorkoutSync
import com.healthmon.app.mobile.sync.SyncDestination
import com.healthmon.app.mobile.sync.WorkoutUploadWorker
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.net.ServerSocket
import java.net.SocketException
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

@RunWith(AndroidJUnit4::class)
class WorkoutUploadWorkerTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    /** Minimal real HTTP server on the emulator itself; no public service or personal data. */
    private class Fixture : AutoCloseable {
        private val listener = ServerSocket(0)
        val url = "http://127.0.0.1:${listener.localPort}"
        val server = UUID.randomUUID().toString()
        val owner = UUID.randomUUID().toString()
        @Volatile var reportedServer = server
        @Volatile var reportedOwner = owner
        @Volatile var identityCode = 200
        @Volatile var workoutCode = 429
        val posts = AtomicInteger()
        @Volatile var lastEventId: String? = null
        private val thread = Thread {
            while (!listener.isClosed) {
                try {
                    listener.accept().use { socket ->
                        val reader = socket.getInputStream().bufferedReader()
                        val path = reader.readLine().split(' ')[1]
                        var length = 0
                        while (true) {
                            val line = reader.readLine() ?: break
                            if (line.isEmpty()) break
                            if (line.startsWith("Content-Length:", ignoreCase=true)) length = line.substringAfter(':').trim().toInt()
                        }
                        val bodyChars = CharArray(length)
                        var offset = 0
                        while (offset < length) {
                            val count = reader.read(bodyChars, offset, length-offset)
                            if (count < 0) break
                            offset += count
                        }
                        val (code, body) = when (path) {
                            "/server-info" -> 200 to JSONObject().put("server_instance_id", reportedServer).put("environment", "test").toString()
                            "/identity" -> identityCode to JSONObject().put("owner_id", reportedOwner).toString()
                            else -> {
                                posts.incrementAndGet()
                                val input = JSONObject(String(bodyChars))
                                lastEventId = input.getString("event_id")
                                workoutCode to JSONObject().put("event_id", lastEventId).put("revision",1)
                                    .put("stored",workoutCode==200).put("evaluation_status","scored").toString()
                            }
                        }
                        val bytes = body.toByteArray(Charsets.UTF_8)
                        socket.getOutputStream().use { out ->
                            out.write("HTTP/1.1 $code Test\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n\r\n".toByteArray())
                            out.write(bytes)
                        }
                    }
                } catch (_: SocketException) { break }
            }
        }.apply { start() }
        override fun close() { listener.close(); thread.join(2000) }
    }

    @Test fun workerRetriesAuthWaitCorrectionAndDurableSuccessWithStableId() = runBlocking {
        Fixture().use { fixture ->
            val db = HealthMonPhoneDatabase.getInstance(context)
            val id = "worker-${UUID.randomUUID()}"
            db.workoutDao().saveWorkout(WorkoutEntity(id,"RUNNING",1000,1_801_000,1800,
                null,null,null,null,null,"","WATCH_MANUAL",false,1_801_010))
            val destination = SyncDestination(fixture.url,"instrumentation-fixture","pet",fixture.server,fixture.owner,"test")
            fun login() {
                val attempt = ServerSyncSettings.clear(context)
                assertTrue(ServerSyncSettings.save(context,destination,attempt))
            }
            suspend fun runWorker() = TestListenableWorkerBuilder<WorkoutUploadWorker>(context).build().doWork()
            suspend fun status() = db.uploadDao().forDestination(fixture.server,fixture.owner,"pet").single().status
            try {
                login()
                db.uploadDao().confirm(WorkoutUploadEntity(id,fixture.server,fixture.owner,"pet",confirmedAt=1_801_020))
                assertEquals(ListenableWorker.Result.retry(), runWorker()) // 429
                assertEquals("pending",status())
                fixture.workoutCode = 503
                assertEquals(ListenableWorker.Result.retry(),runWorker())
                fixture.identityCode = 401
                assertEquals(ListenableWorker.Result.success(),runWorker())
                assertEquals("auth_required",status())
                val before = fixture.posts.get()
                assertEquals(ListenableWorker.Result.success(),runWorker())
                assertEquals(before,fixture.posts.get()) // no blind authentication retry
                fixture.identityCode = 200
                login()
                db.uploadDao().resumeAfterLogin(fixture.server,fixture.owner,"pet")
                fixture.workoutCode = 409
                assertEquals(ListenableWorker.Result.success(),runWorker())
                assertEquals("needs_correction",status())
                // Simulates an explicit corrected/approved retry, never performed automatically.
                db.uploadDao().setResult(id,fixture.server,fixture.owner,"pet","pending",null,null)
                fixture.workoutCode = 200
                assertEquals(ListenableWorker.Result.success(),runWorker())
                assertEquals("synced",status())
                assertEquals(id,fixture.lastEventId)
                assertNotNull(db.uploadDao().forWorkout(id).single().syncedAt)
                assertFalse(db.workoutDao().getWorkout(id)!!.consumedByUnity)
                val after = fixture.posts.get()
                assertEquals(ListenableWorker.Result.success(),runWorker())
                assertEquals(after,fixture.posts.get())
                fixture.reportedServer = "different-database"
                runWorker()
                assertEquals("server_changed",ServerSyncSettings.status(context))
                login()
                fixture.reportedServer = fixture.server
                fixture.reportedOwner = "different-account"
                runWorker()
                assertEquals("identity_changed",ServerSyncSettings.status(context))
                ServerWorkoutSync.clear(context)
                assertNull(ServerSyncSettings.load(context))
            } finally { ServerSyncSettings.clear(context) }
        }
    }

    @Test fun supersededConfigureCannotRestoreCredentialsAfterLogout() {
        val oldAttempt = ServerSyncSettings.clear(context)
        ServerSyncSettings.clear(context)
        val value = SyncDestination("https://example.invalid","fixture","pet","server","owner","test")
        assertFalse(ServerSyncSettings.save(context,value,oldAttempt))
        assertNull(ServerSyncSettings.load(context))
    }
}
