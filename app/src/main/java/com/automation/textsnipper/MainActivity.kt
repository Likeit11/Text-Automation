package com.automation.textsnipper

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.automation.textsnipper.databinding.ActivityMainBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private val PERMISSIONS_REQUEST_CODE = 100
    private val REQUIRED_PERMISSIONS = if (Build.VERSION.SDK_INT >= 33) {
        arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.POST_NOTIFICATIONS)
    } else {
        arrayOf(Manifest.permission.RECEIVE_SMS)
    }
    private val searchStatusListener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == "search_connection_status") updateSearchStatus()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val sharedPreferences = getSharedPreferences("settings", Context.MODE_PRIVATE)

        // 저장된 호스트 주소 및 연결키 불러오기
        binding.hostAddressInput.setText(sharedPreferences.getString("host_address", ""))
        binding.pairingKeyInput.setText(sharedPreferences.getString("pairing_key", ""))
        enableSmsReceiver()
        updateBackgroundStatus()

        // 호스트 주소 자동 저장
        binding.hostAddressInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                with(sharedPreferences.edit()) {
                    putString("host_address", s.toString())
                    apply()
                }
                syncSearchService()
            }
        })

        binding.pairingKeyInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                sharedPreferences.edit().putString("pairing_key", s.toString()).apply()
                syncSearchService()
            }
        })

        binding.backgroundSwitch.setOnCheckedChangeListener { _, isChecked ->
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            if (isChecked == powerManager.isIgnoringBatteryOptimizations(packageName)) {
                return@setOnCheckedChangeListener
            }
            if (isChecked) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:$packageName")))
            } else {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            }
            updateBackgroundStatus()
        }

        binding.allowAutoOpen.setOnClickListener {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        }

        // 테스트 버튼 클릭 리스너
        binding.testButton.setOnClickListener {
            val hostAddress = sharedPreferences.getString("host_address", null)
            if (!hostAddress.isNullOrEmpty()) {
                sendToServer(hostAddress, "Test", "[Test] 200000")
            } else {
                Toast.makeText(this, "Host address is not set", Toast.LENGTH_SHORT).show()
            }
        }

        // 권한 확인 및 요청
        checkAndRequestPermissions()
    }

    override fun onResume() {
        super.onResume()
        updateBackgroundStatus()
        getSharedPreferences("settings", Context.MODE_PRIVATE).registerOnSharedPreferenceChangeListener(searchStatusListener)
        syncSearchService()
        updateSearchStatus()
    }

    override fun onPause() {
        getSharedPreferences("settings", Context.MODE_PRIVATE).unregisterOnSharedPreferenceChangeListener(searchStatusListener)
        super.onPause()
    }

    private fun syncSearchService() {
        val preferences = getSharedPreferences("settings", Context.MODE_PRIVATE)
        val key = preferences.getString("pairing_key", "") ?: ""
        val host = preferences.getString("host_address", "") ?: ""
        val validHost = try { SmsApi.serverUrl(host); true } catch (_: IllegalArgumentException) { false }
        if (validHost && SmsApi.isValidKey(key)) {
            ContextCompat.startForegroundService(this, Intent(this, ProductSearchService::class.java))
        } else {
            stopService(Intent(this, ProductSearchService::class.java))
        }
    }

    private fun updateSearchStatus() {
        val status = getSharedPreferences("settings", Context.MODE_PRIVATE)
            .getString("search_connection_status", "서버 주소와 연결키를 입력하세요")
        binding.searchStatus.text = "PC 검색 연결: $status"
        binding.allowAutoOpen.text = if (Settings.canDrawOverlays(this)) {
            "자동 열기 허용됨 · 권한 설정"
        } else {
            "휴대폰 자동 열기 권한 설정"
        }
    }

    private fun enableSmsReceiver() {
        val receiver = ComponentName(this, SmsBroadcastReceiver::class.java)
        packageManager.setComponentEnabledSetting(
            receiver,
            PackageManager.COMPONENT_ENABLED_STATE_DEFAULT,
            PackageManager.DONT_KILL_APP
        )
    }

    private fun sendToServer(url: String, sender: String, message: String) {
        val key = getSharedPreferences("settings", Context.MODE_PRIVATE).getString("pairing_key", "") ?: ""
        CoroutineScope(Dispatchers.IO).launch {
            try {
                SmsApi.send(url, key, sender, message)
                runOnUiThread { Toast.makeText(this@MainActivity, "Test successful", Toast.LENGTH_SHORT).show() }
            } catch (e: Exception) {
                Log.e("MainActivity", "SMS test failed: ${e.javaClass.simpleName}")
                runOnUiThread { Toast.makeText(this@MainActivity, "연결키, 서버 주소, 서버 버전을 확인하세요.", Toast.LENGTH_LONG).show() }
            }
        }
    }

    private fun updateBackgroundStatus() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        val allowed = powerManager.isIgnoringBatteryOptimizations(packageName)
        binding.backgroundSwitch.isChecked = allowed
        binding.backgroundStatus.text = if (allowed) {
            "허용됨 · 배터리 최적화 제외 상태입니다."
        } else {
            "제한됨 · 스위치를 켜서 배터리 최적화 제외를 허용하세요."
        }
    }

    fun checkAndRequestPermissions() {
        val permissionsToRequest = mutableListOf<String>()
        for (permission in REQUIRED_PERMISSIONS) {
            if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
                permissionsToRequest.add(permission)
            }
        }

        if (permissionsToRequest.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, permissionsToRequest.toTypedArray(), PERMISSIONS_REQUEST_CODE)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == PERMISSIONS_REQUEST_CODE) {
            val allPermissionsGranted = grantResults.all { it == PackageManager.PERMISSION_GRANTED }
            if (allPermissionsGranted) {
                Toast.makeText(this, "모든 권한이 허용되었습니다.", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "앱 기능 사용을 위해 권한이 필요합니다.", Toast.LENGTH_LONG).show()
            }
        }
    }
}
