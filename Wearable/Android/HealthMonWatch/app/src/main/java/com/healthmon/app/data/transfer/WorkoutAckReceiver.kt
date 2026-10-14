package com.healthmon.app.data.transfer

import android.util.Log

import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.WearableListenerService
import com.google.android.gms.wearable.Wearable

import com.healthmon.app.data.local.WorkoutStorage

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class WorkoutAckReceiver :
    WearableListenerService() {


    private val serviceScope =
        CoroutineScope(
            SupervisorJob() +
                    Dispatchers.IO
        )


    override fun onDataChanged(
        dataEvents: DataEventBuffer
    ) {

        super.onDataChanged(
            dataEvents
        )


        dataEvents.forEach { event ->

            if (
                event.type !=
                DataEvent.TYPE_CHANGED
            ) {
                return@forEach
            }


            val dataItem =
                event.dataItem

            val ackUri =
                dataItem.uri

            val path =
                dataItem.uri.path
                    ?: return@forEach


            if (
                !path.startsWith(
                    WorkoutDataContract
                        .ACK_PATH_PREFIX
                )
            ) {
                return@forEach
            }


            val dataMap =
                DataMapItem
                    .fromDataItem(
                        dataItem
                    )
                    .dataMap


            val workoutId =
                dataMap.getString(
                    WorkoutDataContract.KEY_ID
                )
                    ?: return@forEach

            //Log.d(TAG, "ACK 수신: $workoutId")

            serviceScope.launch {

                try {
                    WorkoutStorage.markAsSent(
                        applicationContext,
                        workoutId
                    )

                    //Log.d(TAG, "Workout SENT 처리 완료: $workoutId")

                    val deletedCount =
                        Wearable
                            .getDataClient(
                                applicationContext
                            )
                            .deleteDataItems(
                                ackUri
                            )
                            .await()


                    //Log.d(TAG, "ACK DataItem 삭제 완료: " + "id=$workoutId, " + "count=$deletedCount")
                } catch (e: Exception) {
                    Log.e(TAG, "Workout SENT 처리 실패: $workoutId", e)
                }
            }
        }
    }


    override fun onDestroy() {

        serviceScope.cancel()

        super.onDestroy()
    }


    companion object {

        private const val TAG =
            "HealthMonAck"
    }
}