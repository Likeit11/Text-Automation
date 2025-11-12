package com.automation.textsnipper

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class SmsBroadcastReceiver : BroadcastReceiver() {

    private val client = OkHttpClient()

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION) {
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            for (smsMessage in messages) {
                val messageBody = smsMessage.messageBody
                val sender = smsMessage.originatingAddress

                Log.d("SmsReceiver", "From: $sender, Message: $messageBody")

                val sharedPreferences = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
                val hostAddress = sharedPreferences.getString("host_address", null)

                if (hostAddress != null && hostAddress.isNotEmpty()) {
                    sendToServer(hostAddress, sender, messageBody)
                }
            }
        }
    }

    private fun sendToServer(url: String, sender: String?, message: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val correctedUrl = if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    "http://$url"
                } else {
                    url
                }

                val json = JSONObject()
                json.put("sender", sender)
                json.put("message", message)

                val requestBody = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())

                val request = Request.Builder()
                    .url(correctedUrl)
                    .post(requestBody)
                    .build()

                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        Log.e("SmsReceiver", "Server error: ${response.code} ${response.message}")
                    } else {
                        Log.d("SmsReceiver", "Server response: ${response.body?.string()}")
                    }
                }
            } catch (e: Exception) {
                Log.e("SmsReceiver", "Error sending to server: ${e.message}")
            }
        }
    }
}
