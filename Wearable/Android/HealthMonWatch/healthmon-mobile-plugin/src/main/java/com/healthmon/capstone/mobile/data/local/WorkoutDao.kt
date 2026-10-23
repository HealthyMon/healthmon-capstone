package com.healthmon.capstone.mobile.data.local

import androidx.room3.Dao
import androidx.room3.Insert
import androidx.room3.OnConflictStrategy
import androidx.room3.Query


@Dao
interface WorkoutDao {


    /*
     * 같은 운동 ID가 이미 있다면 무시한다.
     *
     * 워치에서 같은 DataItem이 다시 전달되더라도
     * 휴대폰에 중복 기록이 생기지 않는다.
     */
    @Insert(
        onConflict =
            OnConflictStrategy.IGNORE
    )
    suspend fun saveWorkout(
        workout: WorkoutEntity
    )


    @Query(
        """
        SELECT *
        FROM workout
        ORDER BY startTime DESC
        """
    )
    suspend fun getAllWorkouts():
            List<WorkoutEntity>


    @Query(
        """
        SELECT *
        FROM workout
        WHERE consumedByUnity = 0
        ORDER BY startTime ASC
        """
    )
    suspend fun getPendingForUnity():
            List<WorkoutEntity>


    @Query(
        """
        SELECT *
        FROM workout
        WHERE id = :id
        LIMIT 1
        """
    )
    suspend fun getWorkout(
        id: String
    ): WorkoutEntity?


    @Query(
        """
        UPDATE workout
        SET consumedByUnity = 1
        WHERE id = :id
        """
    )
    suspend fun markConsumedByUnity(
        id: String
    )


    @Query(
        """
        SELECT COUNT(*)
        FROM workout
        """
    )
    suspend fun getWorkoutCount():
            Int
}