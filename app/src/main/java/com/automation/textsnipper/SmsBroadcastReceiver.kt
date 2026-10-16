package com.automation.textsnipper

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

open class SmsBroadcastReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION) {
            val preferences = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
            if (!preferences.getBoolean("service_enabled", false)) return
            val host = preferences.getString("host_address", "") ?: ""
            val key = preferences.getString("pairing_key", "") ?: ""
            if (host.isEmpty() || !SmsApi.isValidKey(key)) {
                Log.w("SmsReceiver", "SMS forwarding skipped: HTTPS host and valid pairing key required")
                return
            }
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            if (messages.isEmpty()) return
            val pending = goAsync()
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    SmsApi.send(host, key, messages.first().originatingAddress,
                        messages.joinToString("") { it.messageBody })
                } catch (e: Exception) {
                    Log.e("SmsReceiver", "SMS forwarding failed: ${e.javaClass.simpleName}")
                } finally {
                    pending.finish()
                }
            }
        }
    }
}
