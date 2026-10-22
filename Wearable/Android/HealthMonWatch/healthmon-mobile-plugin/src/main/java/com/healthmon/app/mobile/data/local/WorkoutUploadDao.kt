package com.healthmon.app.mobile.data.local

import androidx.room3.Dao
import androidx.room3.Insert
import androidx.room3.OnConflictStrategy
import androidx.room3.Query
import androidx.room3.Transaction

@Dao
abstract class WorkoutUploadDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insert(binding: WorkoutUploadEntity)

    @Query("SELECT * FROM workout_upload WHERE workoutId=:id")
    abstract suspend fun forWorkout(id: String): List<WorkoutUploadEntity>

    @Query("SELECT * FROM workout_upload WHERE serverInstanceId=:server AND ownerId=:owner AND petId=:pet ORDER BY confirmedAt,workoutId")
    abstract suspend fun forDestination(server: String, owner: String, pet: String): List<WorkoutUploadEntity>

    // Records bound to ANY owner on this server are never offered to a different login/pet.
    @Query("SELECT * FROM workout WHERE NOT EXISTS (SELECT 1 FROM workout_upload u WHERE u.workoutId=workout.id AND (u.serverInstanceId=:server OR u.ownerId!=:owner)) ORDER BY startTime,id")
    abstract suspend fun unbound(server: String, owner: String): List<WorkoutEntity>

    @Transaction
    open suspend fun confirm(binding: WorkoutUploadEntity): Boolean {
        val old = forWorkout(binding.workoutId)
        if (old.any { it.ownerId != binding.ownerId ||
                    (it.serverInstanceId == binding.serverInstanceId && it.petId != binding.petId) }) return false
        insert(binding)
        return true
    }

    @Query("UPDATE workout_upload SET status=:status,syncedAt=:syncedAt,lastHttpStatus=:code WHERE workoutId=:id AND serverInstanceId=:server AND ownerId=:owner AND petId=:pet")
    abstract suspend fun setResult(id: String, server: String, owner: String, pet: String,
                                  status: String, syncedAt: Long?, code: Int?)

    @Query("UPDATE workout_upload SET status='pending',lastHttpStatus=NULL WHERE serverInstanceId=:server AND ownerId=:owner AND petId=:pet AND status='auth_required'")
    abstract suspend fun resumeAfterLogin(server: String, owner: String, pet: String)
}
