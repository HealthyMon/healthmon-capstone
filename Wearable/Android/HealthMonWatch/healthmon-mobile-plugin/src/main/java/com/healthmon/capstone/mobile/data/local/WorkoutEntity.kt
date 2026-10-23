package com.healthmon.capstone.mobile.data.local

import androidx.room3.Entity
import androidx.room3.PrimaryKey


@Entity(
    tableName = "workout"
)
data class WorkoutEntity(

    @PrimaryKey
    val id: String,

    val exerciseType: String,

    val startTime: Long,

    val endTime: Long,

    val durationSeconds: Long,

    val averageHeartRate: Double?,

    val maxHeartRate: Double?,

    val calories: Double?,

    val steps: Long?,

    val distanceKm: Double?,

    val supportedMetrics: String,

    val source: String,

    /*
     * Unity가 이 기록을 가져갔는지 여부
     *
     * false = Unity가 아직 처리하지 않음
     * true  = Unity 처리 완료
     */
    val consumedByUnity: Boolean = false,

    /*
     * 휴대폰이 기록을 받은 시각
     */
    val receivedAt: Long
)