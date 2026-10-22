package com.healthmon.app.mobile.sync

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI

data class SyncHttpResponse(val code: Int, val body: String)

class SyncHttpClient {
    fun request(destination: SyncDestination, path: String, body: JSONObject? = null): SyncHttpResponse {
        val connection = URI(destination.baseUrl + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 10_000
            connection.readTimeout = 20_000
            connection.instanceFollowRedirects = false // Never forward a bearer to another origin.
            connection.setRequestProperty("Accept", "application/json")
            if (path != "/server-info") connection.setRequestProperty("Authorization", "Bearer ${destination.bearer}")
            if (body != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            // Bound a malformed/error response instead of loading an untrusted server body into RAM.
            val bytes = stream?.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (output.size() <= 1_048_576) {
                    val count = input.read(buffer, 0, minOf(buffer.size, 1_048_577 - output.size()))
                    if (count < 0) break
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: byteArrayOf()
            require(bytes.size <= 1_048_576) { "response_too_large" }
            return SyncHttpResponse(code, String(bytes, Charsets.UTF_8))
        } finally { connection.disconnect() }
    }
}
