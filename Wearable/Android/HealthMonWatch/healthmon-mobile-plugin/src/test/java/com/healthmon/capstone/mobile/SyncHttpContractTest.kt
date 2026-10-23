package com.healthmon.capstone.mobile

import com.healthmon.capstone.mobile.sync.SyncDestination
import com.healthmon.capstone.mobile.sync.SyncHttpClient
import com.healthmon.capstone.mobile.sync.WorkoutUploadPolicy
import com.sun.net.httpserver.HttpServer
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.net.InetSocketAddress
import java.util.concurrent.atomic.AtomicInteger

/** Actual HTTP requests to a loopback contract double, not watch/device validation. */
class SyncHttpContractTest {
    @Test fun bearerIsScopedToAuthenticatedRoutesAndRedirectIsNotFollowed() {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        val redirected = AtomicInteger()
        server.createContext("/server-info") { exchange ->
            assertNull(exchange.requestHeaders.getFirst("Authorization"))
            val bytes = "{\"server_instance_id\":\"test-instance\",\"environment\":\"test\"}".toByteArray()
            exchange.sendResponseHeaders(200, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.createContext("/pets/pet/workouts") { exchange ->
            assertEquals("Bearer contract-fixture", exchange.requestHeaders.getFirst("Authorization"))
            val request = JSONObject(exchange.requestBody.bufferedReader().readText())
            assertEquals("stable-id", request.getString("event_id"))
            val bytes = JSONObject().put("event_id", request.getString("event_id"))
                .put("revision", 1).put("stored", true).put("evaluation_status", "recorded_unscored")
                .toString().toByteArray()
            exchange.sendResponseHeaders(201, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.createContext("/identity") { exchange ->
            exchange.responseHeaders.add("Location", "/unexpected")
            exchange.sendResponseHeaders(302, -1)
            exchange.close()
        }
        server.createContext("/unexpected") { exchange ->
            redirected.incrementAndGet()
            exchange.sendResponseHeaders(200, -1)
            exchange.close()
        }
        server.start()
        try {
            val destination = SyncDestination("http://127.0.0.1:${server.address.port}", "contract-fixture", "pet", "test-instance", "owner", "test")
            val client = SyncHttpClient()
            assertEquals(200, client.request(destination, "/server-info").code)
            val response = client.request(destination, "/pets/pet/workouts", JSONObject().put("event_id", "stable-id"))
            assertTrue(WorkoutUploadPolicy.acknowledged(response.body, "stable-id"))
            assertEquals(302, client.request(destination, "/identity").code)
            assertEquals(0, redirected.get())
        } finally { server.stop(0) }
    }
}
