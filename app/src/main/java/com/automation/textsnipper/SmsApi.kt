package com.automation.textsnipper

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.TimeUnit

object SmsApi {
    private val client = OkHttpClient.Builder()
        .callTimeout(4, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    fun isValidKey(key: String): Boolean {
        return key.toByteArray(Charsets.UTF_8).size in 16..128 &&
            key.none { it.isWhitespace() || it.code < 32 || it.code == 127 }
    }

    // Call from an IO coroutine. Never send a keyed SMS to an old broadcast server.
    fun send(host: String, key: String, sender: String?, message: String) {
        require(isValidKey(key)) { "연결키는 공백·제어문자 없이 UTF-8 기준 16~128바이트여야 합니다." }
        val url = host.trim().trimEnd('/')
        require(URI(url).scheme == "https") { "연결키 모드에는 https:// 서버 주소가 필요합니다." }

        val capabilityRequest = Request.Builder().url("$url/capabilities").get().build()
        client.newCall(capabilityRequest).execute().use { response ->
            check(response.isSuccessful &&
                JSONObject(response.body?.string() ?: "{}").optInt("key_routing_version") == 1) {
                "연결키 수신을 지원하는 서버인지 확인할 수 없습니다. 서버 업데이트를 확인하세요."
            }
        }

        val json = JSONObject()
            .put("sender", sender)
            .put("message", message)
            .put("key", key)
        val request = Request.Builder()
            .url(url)
            .post(json.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()
        client.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "서버 전송 실패 (HTTP ${response.code})" }
        }
    }
}
