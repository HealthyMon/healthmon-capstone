package com.healthmon.capstone.mobile.data.local

import androidx.room3.Entity
import androidx.room3.ForeignKey
import androidx.room3.Index

/** A confirmed destination, independent of the existing Unity consumption flag. */
@Entity(
    tableName = "workout_upload",
    primaryKeys = ["workoutId", "serverInstanceId", "ownerId", "petId"],
    foreignKeys = [ForeignKey(
        entity = WorkoutEntity::class, parentColumns = ["id"],
        childColumns = ["workoutId"], onDelete = ForeignKey.CASCADE
    )],
    indices = [Index(value = ["workoutId"]) ]
)
data class WorkoutUploadEntity(
    val workoutId: String,
    val serverInstanceId: String,
    val ownerId: String,
    val petId: String,
    val status: String = "pending",
    val confirmedAt: Long,
    val syncedAt: Long? = null,
    val lastHttpStatus: Int? = null
)
