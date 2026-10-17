package com.healthmon.app.data.local

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
abstract class HealthMonDatabase :
    RoomDatabase() {


    abstract fun workoutDao():
            WorkoutDao


    companion object {

        @Volatile
        private var INSTANCE:
                HealthMonDatabase? = null


        fun getInstance(
            context: Context
        ): HealthMonDatabase {

            return INSTANCE
                ?: synchronized(this) {

                    val instance =
                        Room
                            .databaseBuilder(
                                context.applicationContext,
                                HealthMonDatabase::class.java,
                                "healthmon.db"
                            )
                            .setDriver(
                                AndroidSQLiteDriver()
                            )
                            .build()


                    INSTANCE =
                        instance


                    instance
                }
        }
    }
}