package com.healthmon.app.data.local

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
     * 휴대폰 전송 상태
     *
     * PENDING = 아직 전송하지 않음
     * SENT    = 전송 완료
     */
    val syncState: String
)