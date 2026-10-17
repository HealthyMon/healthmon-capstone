package com.healthmon.app.mobile.data.local

import android.content.Context

import androidx.room3.Database
import androidx.room3.Room
import androidx.room3.RoomDatabase
import androidx.sqlite.driver.AndroidSQLiteDriver


@Database(
    entities = [
        WorkoutEntity::class
    ],
    version = 1,
    exportSchema = false
)
abstract class HealthMonPhoneDatabase :
    RoomDatabase() {


    abstract fun workoutDao():
            WorkoutDao


    companion object {

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
                            .build()
                            .also {

                                INSTANCE = it
                            }
                }
        }
    }
}