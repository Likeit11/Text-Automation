package com.automation.textsnipper

import android.app.KeyguardManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.NotificationCompat
import io.socket.client.IO
import io.socket.client.Socket
import org.json.JSONObject

class ProductSearchService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private var socket: Socket? = null
    private var connection: Pair<String, String>? = null
    private var ready = false
    private val connect = Runnable { connectToServer() }

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL, "PC 상품 검색 연결", NotificationManager.IMPORTANCE_LOW))
            manager.createNotificationChannel(NotificationChannel(SEARCH_CHANNEL, "잠금 중 상품 검색", NotificationManager.IMPORTANCE_LOW))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(101, statusNotification())
        handler.removeCallbacks(connect)
        handler.postDelayed(connect, 500)
        return START_STICKY
    }

    private fun connectToServer() {
        val preferences = getSharedPreferences("settings", Context.MODE_PRIVATE)
        val key = preferences.getString("pairing_key", "") ?: ""
        val host = try {
            SmsApi.serverUrl(preferences.getString("host_address", "") ?: "")
        } catch (_: IllegalArgumentException) {
            stopSelf()
            return
        }
        if (!SmsApi.isValidKey(key)) {
            stopSelf()
            return
        }
        if (connection == (host to key) && socket != null) return
        socket?.off()
        socket?.disconnect()
        ready = false
        connection = host to key
        val options = IO.Options().apply {
            auth = mapOf("key" to key, "role" to "phone")
            reconnection = true
            forceNew = true
            timeout = 10000
        }
        val client = IO.socket(host, options)
        socket = client
        client.on("routing_ready") { args ->
            val data = args.filterIsInstance<JSONObject>().firstOrNull()
            handler.post {
                if (socket === client) {
                    ready = data != null && data.optInt("version") == 1 && data.optString("mode") == "keyed" && data.optString("role") == "phone"
                    updateStatus(if (ready) "연결됨 · PC 검색 수신 대기" else "서버 업데이트가 필요합니다")
                }
            }
        }
        client.on(Socket.EVENT_DISCONNECT) {
            handler.post {
                if (socket === client) {
                    ready = false
                    updateStatus("연결 끊김 · 재연결 중")
                }
            }
        }
        client.on(Socket.EVENT_CONNECT_ERROR) {
            handler.post { if (socket === client) updateStatus("연결 실패 · 서버 주소와 연결키를 확인하세요") }
        }
        client.on("open_product_search") { args ->
            val value = args.filterIsInstance<JSONObject>().firstOrNull()?.optString("url") ?: return@on
            handler.post { if (socket === client && ready) openSearch(value) }
        }
        updateStatus("연결 중")
        client.connect()
    }

    private fun openSearch(value: String) {
        val url = ProductSearchUrl.parse(value) ?: return
        val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url.toString())).apply {
            addCategory(Intent.CATEGORY_BROWSABLE)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val manager = getSystemService(NotificationManager::class.java)
        val locked = getSystemService(KeyguardManager::class.java).isKeyguardLocked
        val interactive = getSystemService(PowerManager::class.java).isInteractive
        if (locked || !interactive) {
            val pending = PendingIntent.getActivity(this, 102, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val notification = NotificationCompat.Builder(this, SEARCH_CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_search)
                .setContentTitle("PC에서 보낸 상품 검색")
                .setContentText("잠금을 풀고 눌러서 9tems 검색 결과 열기")
                .setContentIntent(pending)
                .setAutoCancel(true)
                .build()
            manager.notify(102, notification)
        } else if (Settings.canDrawOverlays(this)) {
            manager.cancel(102)
            try {
                startActivity(intent)
            } catch (_: android.content.ActivityNotFoundException) {
                updateStatus("웹 브라우저 앱을 설치하세요")
            } catch (_: SecurityException) {
                updateStatus("자동 열기 제한됨 · 자동 열기 권한을 확인하세요")
            }
        } else {
            updateStatus("자동 열기 권한을 허용하세요")
        }
    }

    private fun statusNotification(): android.app.Notification {
        val pending = PendingIntent.getActivity(this, 101, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setContentTitle("PC 연결 유지 서비스")
            .setContentIntent(pending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    private fun updateStatus(status: String) {
        getSharedPreferences("settings", Context.MODE_PRIVATE).edit().putString("search_connection_status", status).apply()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        socket?.off()
        socket?.disconnect()
        getSharedPreferences("settings", Context.MODE_PRIVATE).edit().putString("search_connection_status", "수신 중지됨 · 앱을 다시 열어 주세요").apply()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL = "pc_product_search"
        private const val SEARCH_CHANNEL = "pc_product_search_locked"
    }
}
