package com.healthmon.app.mobile

import android.database.sqlite.SQLiteDatabase
import androidx.room3.Room
import androidx.sqlite.driver.AndroidSQLiteDriver
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.healthmon.app.mobile.data.local.HealthMonPhoneDatabase
import com.healthmon.app.mobile.data.local.WorkoutEntity
import com.healthmon.app.mobile.data.local.WorkoutUploadEntity
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

/** Runs only against a unique disposable test DB; never opens installed healthmon_phone.db. */
@RunWith(AndroidJUnit4::class)
class WorkoutUploadPersistenceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private fun open(name: String) = Room.databaseBuilder<HealthMonPhoneDatabase>(context, name)
        .setDriver(AndroidSQLiteDriver()).addMigrations(HealthMonPhoneDatabase.MIGRATION_1_2).build()

    @Test fun migrationPreservesV1WorkoutAndUnityConsumption() = runBlocking {
        val name = "upload-migration-${UUID.randomUUID()}.db"
        val path = context.getDatabasePath(name)
        path.parentFile!!.mkdirs()
        SQLiteDatabase.openOrCreateDatabase(path, null).use { old ->
            old.execSQL("""CREATE TABLE workout (
                id TEXT NOT NULL PRIMARY KEY,exerciseType TEXT NOT NULL,startTime INTEGER NOT NULL,
                endTime INTEGER NOT NULL,durationSeconds INTEGER NOT NULL,averageHeartRate REAL,
                maxHeartRate REAL,calories REAL,steps INTEGER,distanceKm REAL,supportedMetrics TEXT NOT NULL,
                source TEXT NOT NULL,consumedByUnity INTEGER NOT NULL,receivedAt INTEGER NOT NULL)""")
            old.execSQL("INSERT INTO workout VALUES ('old','SQUAT',1000,61000,60,NULL,NULL,NULL,NULL,NULL,'','WATCH_MANUAL',1,62000)")
            old.version = 1
        }
        try {
            val db = open(name)
            val workout = db.workoutDao().getWorkout("old")!!
            assertTrue(workout.consumedByUnity)
            assertNull(workout.steps)
            assertEquals(1, db.uploadDao().unbound("server-a", "owner-a").size)
            assertTrue(db.uploadDao().forWorkout("old").isEmpty())
            db.close()
        } finally { context.deleteDatabase(name) }
    }

    @Test fun confirmedUploadsRecoverAfterReopenAndNeverTransferAccounts() = runBlocking {
        val name = "upload-recovery-${UUID.randomUUID()}.db"
        try {
            var db = open(name)
            db.workoutDao().saveWorkout(WorkoutEntity("id", "RUNNING", 1000, 61000, 60,
                null,null,null,null,null,"","WATCH_MANUAL",false,62000))
            // Process could die here before WorkManager enqueue: original remains recoverable.
            assertEquals(1, db.uploadDao().unbound("server-a", "owner-a").size)
            assertTrue(db.uploadDao().confirm(WorkoutUploadEntity("id", "server-a", "owner-a", "pet-a", confirmedAt=63000)))
            db.close()
            db = open(name)
            assertEquals("pending", db.uploadDao().forDestination("server-a", "owner-a", "pet-a").single().status)
            assertFalse(db.workoutDao().getWorkout("id")!!.consumedByUnity)
            assertFalse(db.uploadDao().confirm(WorkoutUploadEntity("id", "server-a", "owner-b", "pet-b", confirmedAt=64000)))
            assertFalse(db.uploadDao().confirm(WorkoutUploadEntity("id", "server-b", "owner-b", "pet-b", confirmedAt=64000)))
            assertTrue(db.uploadDao().unbound("server-b", "owner-b").isEmpty())
            // Same owner, new server requires another explicit binding; never reuses sync success.
            db.uploadDao().setResult("id", "server-a", "owner-a", "pet-a", "synced", 65000, 200)
            assertTrue(db.uploadDao().confirm(WorkoutUploadEntity("id", "server-b", "owner-a", "pet-a", confirmedAt=66000)))
            assertEquals("pending", db.uploadDao().forDestination("server-b", "owner-a", "pet-a").single().status)
            db.workoutDao().markConsumedByUnity("id")
            assertEquals("pending", db.uploadDao().forDestination("server-b", "owner-a", "pet-a").single().status)
            db.close()
        } finally { context.deleteDatabase(name) }
    }
}
