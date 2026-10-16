package com.automation.textsnipper

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
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
    private val REQUIRED_PERMISSIONS = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.POST_NOTIFICATIONS)
    } else {
        arrayOf(Manifest.permission.RECEIVE_SMS)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val sharedPreferences = getSharedPreferences("settings", Context.MODE_PRIVATE)

        // 저장된 호스트 주소 및 스위치 상태 불러오기
        binding.hostAddressInput.setText(sharedPreferences.getString("host_address", ""))
        binding.pairingKeyInput.setText(sharedPreferences.getString("pairing_key", ""))
        binding.serviceSwitch.isChecked = sharedPreferences.getBoolean("service_enabled", false)

        // 호스트 주소 자동 저장
        binding.hostAddressInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                with(sharedPreferences.edit()) {
                    putString("host_address", s.toString())
                    apply()
                }
            }
        })

        binding.pairingKeyInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                sharedPreferences.edit().putString("pairing_key", s.toString()).apply()
            }
        })

        // 스위치 리스너
        binding.serviceSwitch.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && !SmsApi.isValidKey(sharedPreferences.getString("pairing_key", "") ?: "")) {
                binding.serviceSwitch.isChecked = false
                Toast.makeText(this, "먼저 연결키를 입력하세요. 공백 없이 16~128바이트가 필요합니다.", Toast.LENGTH_LONG).show()
                return@setOnCheckedChangeListener
            }
            with(sharedPreferences.edit()) {
                putBoolean("service_enabled", isChecked)
                apply()
            }
            toggleSmsReceiver(isChecked)
            val status = if (isChecked) "started" else "stopped"
            Toast.makeText(this, "Background service $status", Toast.LENGTH_SHORT).show()
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
        // 배터리 최적화 예외 요청
        requestIgnoreBatteryOptimizations()
    }

    private fun toggleSmsReceiver(enable: Boolean) {
        val receiver = ComponentName(this, SmsBroadcastReceiver::class.java)
        packageManager.setComponentEnabledSetting(
            receiver,
            if (enable) PackageManager.COMPONENT_ENABLED_STATE_ENABLED else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
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
                runOnUiThread { Toast.makeText(this@MainActivity, "연결키, HTTPS 주소, 서버 버전을 확인하세요.", Toast.LENGTH_LONG).show() }
            }
        }
    }

    fun requestIgnoreBatteryOptimizations() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            val packageName = packageName
            if (!powerManager.isIgnoringBatteryOptimizations(packageName)) {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                intent.data = Uri.parse("package:$packageName")
                startActivity(intent)
            }
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
