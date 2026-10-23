package com.healthmon.capstone.data.local

import androidx.room3.Dao
import androidx.room3.Query
import androidx.room3.Upsert


@Dao
interface WorkoutDao {

    /*
     * 운동 결과 저장
     *
     * 동일한 id가 없으면 INSERT
     * 동일한 id가 있으면 UPDATE
     */
    @Upsert
    suspend fun saveWorkout(
        workout: WorkoutEntity
    )


    /*
     * 저장된 전체 운동 기록 조회
     *
     * 최신 기록부터 반환
     */
    @Query(
        """
        SELECT *
        FROM workout
        ORDER BY startTime DESC
        """
    )
    suspend fun getAllWorkouts():
            List<WorkoutEntity>


    /*
     * 특정 운동 조회
     */
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


    /*
     * 아직 휴대폰으로 보내지 않은 운동
     */
    @Query(
        """
        SELECT *
        FROM workout
        WHERE syncState = 'PENDING'
        ORDER BY startTime ASC
        """
    )
    suspend fun getPendingWorkouts():
            List<WorkoutEntity>


    /*
     * 휴대폰으로 전송 완료한 운동
     */
    @Query(
        """
        UPDATE workout
        SET syncState = 'SENT'
        WHERE id = :id
        """
    )
    suspend fun markAsSent(
        id: String
    )
}