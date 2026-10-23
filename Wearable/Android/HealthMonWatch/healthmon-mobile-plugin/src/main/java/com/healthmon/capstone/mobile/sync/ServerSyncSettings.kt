package com.healthmon.capstone.mobile.sync

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class SyncDestination(
    val baseUrl: String, val bearer: String, val petId: String,
    val serverInstanceId: String, val ownerId: String, val environment: String,
    val generation: String = UUID.randomUUID().toString()
) {
    override fun toString(): String = "SyncDestination(credentials=redacted)"
}

/** Entire destination + bearer encrypted with a non-exportable Android Keystore key.
 * No token in WorkManager InputData, logs, Unity prefs or backups. */
object ServerSyncSettings {
    private const val ALIAS = "healthmon.server-sync.v1"
    private fun prefs(context: Context) = context.getSharedPreferences("healthmon.server-sync", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").run {
            init(KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
            generateKey()
        }
    }

    @Synchronized fun save(context: Context, value: SyncDestination, attempt: String): Boolean {
        if (prefs(context).getString("attempt", null) != attempt) return false
        val plaintext = JSONObject().apply {
            put("url", value.baseUrl); put("bearer", value.bearer); put("pet", value.petId)
            put("server", value.serverInstanceId); put("owner", value.ownerId)
            put("environment", value.environment); put("generation", value.generation)
        }.toString().toByteArray(Charsets.UTF_8)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val encrypted = cipher.doFinal(plaintext)
        check(prefs(context).edit().putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("value", Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .putString("status", "ready").commit()) { "credential_storage_failed" }
        return true
    }

    @Synchronized fun load(context: Context): SyncDestination? {
        val encrypted = prefs(context).getString("value", null) ?: return null
        return try {
            val iv = Base64.decode(prefs(context).getString("iv", ""), Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
            }
            val json = JSONObject(String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)), Charsets.UTF_8))
            SyncDestination(json.getString("url"), json.getString("bearer"), json.getString("pet"),
                json.getString("server"), json.getString("owner"), json.getString("environment"),
                json.getString("generation"))
        } catch (_: Exception) {
            // Restored preferences cannot decrypt on a new device: force runtime login.
            clear(context); setStatus(context, "auth_required"); null
        }
    }

    @Synchronized fun clear(context: Context): String {
        val attempt = UUID.randomUUID().toString()
        check(prefs(context).edit().clear().putString("attempt", attempt).commit())
        return attempt
    }
    @Synchronized fun setAttemptStatus(context: Context, attempt: String, value: String) {
        if (prefs(context).getString("attempt", null) == attempt) setStatus(context, value)
    }
    @Synchronized fun setCurrentStatus(context: Context, destination: SyncDestination, value: String) {
        if (current(context, destination)) setStatus(context, value)
    }
    fun setStatus(context: Context, value: String) { prefs(context).edit().putString("status", value).commit() }
    fun status(context: Context): String = prefs(context).getString("status", "not_configured") ?: "not_configured"
    fun current(context: Context, value: SyncDestination): Boolean = load(context)?.generation == value.generation
}
