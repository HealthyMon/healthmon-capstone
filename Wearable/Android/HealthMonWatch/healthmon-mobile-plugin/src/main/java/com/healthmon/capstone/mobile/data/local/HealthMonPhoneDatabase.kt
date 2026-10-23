package com.healthmon.capstone.mobile.data.local

import android.content.Context

import androidx.room3.Database
import androidx.room3.Room
import androidx.room3.RoomDatabase
import androidx.sqlite.driver.AndroidSQLiteDriver
import androidx.sqlite.SQLiteConnection
import androidx.room3.migration.Migration


@Database(
    entities = [
        WorkoutEntity::class,
        WorkoutUploadEntity::class
    ],
    version = 2,
    exportSchema = true
)
abstract class HealthMonPhoneDatabase :
    RoomDatabase() {


    abstract fun workoutDao():
            WorkoutDao

    abstract fun uploadDao(): WorkoutUploadDao


    companion object {

        /** Room 3 uses suspend migrations and SQLiteConnection, not SupportSQLiteDatabase. */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override suspend fun migrate(connection: SQLiteConnection) {
                connection.prepare("""
                    CREATE TABLE IF NOT EXISTS workout_upload (
                        workoutId TEXT NOT NULL, serverInstanceId TEXT NOT NULL,
                        ownerId TEXT NOT NULL, petId TEXT NOT NULL, status TEXT NOT NULL,
                        confirmedAt INTEGER NOT NULL, syncedAt INTEGER, lastHttpStatus INTEGER,
                        PRIMARY KEY(workoutId,serverInstanceId,ownerId,petId),
                        FOREIGN KEY(workoutId) REFERENCES workout(id) ON UPDATE NO ACTION ON DELETE CASCADE
                    )
                """.trimIndent()).use { it.step() }
                connection.prepare("CREATE INDEX IF NOT EXISTS index_workout_upload_workoutId ON workout_upload(workoutId)").use { it.step() }
            }
        }

        @Volatile
        private var INSTANCE:
                HealthMonPhoneDatabase? =
            null


        fun getInstance(
            context: Context
        ): HealthMonPhoneDatabase {

            return INSTANCE
                ?: synchronized(this) {

                    INSTANCE
                        ?: Room
                            .databaseBuilder<
                                    HealthMonPhoneDatabase
                                    >(
                                context.applicationContext,
                                "healthmon_phone.db"
                            )
                            .setDriver(
                                AndroidSQLiteDriver()
                            )
                            .addMigrations(MIGRATION_1_2)
                            .build()
                            .also {

                                INSTANCE = it
                            }
                }
        }
    }
}
