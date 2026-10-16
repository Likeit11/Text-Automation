package com.automation.textsnipper

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object SmsApi {
    private val client = OkHttpClient.Builder()
        .callTimeout(4, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    fun isValidKey(key: String): Boolean {
        return key.codePointCount(0, key.length) in 4..128 &&
            key.none { it.isWhitespace() || it.code < 32 || it.code == 127 }
    }

    fun serverUrl(host: String): String {
        val address = host.trim()
        val url = (if ("://" in address) address else "https://$address").toHttpUrlOrNull()
        require(url != null && url.isHttps) { "올바른 서버 도메인 주소를 입력하세요." }
        return url.toString().trimEnd('/')
    }

    // Call from an IO coroutine. Never send a keyed SMS to an old broadcast server.
    fun send(host: String, key: String, sender: String?, message: String) {
        require(isValidKey(key)) { "연결키를 확인하세요. 공백 없이 4~128자로 입력하세요." }
        val url = serverUrl(host)

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
