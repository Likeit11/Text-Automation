package com.automation.textsnipper

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION) {
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            for (smsMessage in messages) {
                val messageBody = smsMessage.messageBody
                val sender = smsMessage.originatingAddress

                // 여기에 수신된 메시지를 처리하는 로직을 추가합니다.
                Log.d("SmsReceiver", "From: $sender, Message: $messageBody")

                // SharedPreferences에서 서버 URL, 포트, Webhook 경로 가져오기
                val sharedPreferences = context.getSharedPreferences("MyPrefs", Context.MODE_PRIVATE)
                val serverUrl = sharedPreferences.getString("server_url", "")
                val serverPort = sharedPreferences.getString("server_port", "")
                val webhookPath = sharedPreferences.getString("webhook_path", "")

                if (serverUrl!!.isNotEmpty() && serverPort!!.isNotEmpty() && webhookPath!!.isNotEmpty()) {
                    sendToServer(serverUrl, serverPort, webhookPath, messageBody)
                }
            }
        }
    }

    private fun sendToServer(serverUrl: String, serverPort: String, webhookPath: String, message: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val url = URL("$serverUrl:$serverPort/$webhookPath")
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json")
                connection.doOutput = true

                val json = "{\"message\":\"$message\"}"

                val writer = OutputStreamWriter(connection.outputStream)
                writer.write(json)
                writer.flush()

                val responseCode = connection.responseCode
                Log.d("SmsReceiver", "Server response code: $responseCode")

            } catch (e: Exception) {
                Log.e("SmsReceiver", "Error sending to server: ${e.message}")
            }
        }
    }
}
