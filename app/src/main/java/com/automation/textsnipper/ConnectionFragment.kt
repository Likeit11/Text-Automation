package com.automation.textsnipper

import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.automation.textsnipper.databinding.FragmentConnectionBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.OutputStreamWriter
import java.net.Socket

class ConnectionFragment : Fragment() {

    private var _binding: FragmentConnectionBinding? = null
    private val binding get() = _binding!!

    private lateinit var sharedPreferences: SharedPreferences
    private val fragmentScope = CoroutineScope(Dispatchers.IO)

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentConnectionBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        sharedPreferences = requireActivity().getSharedPreferences("app_prefs", Context.MODE_PRIVATE)

        val savedIp = sharedPreferences.getString("pc_ip_address", "")
        binding.ipAddressInput.setText(savedIp)

        binding.saveButton.setOnClickListener {
            val ipAddress = binding.ipAddressInput.text.toString()
            if (ipAddress.isNotEmpty()) {
                sharedPreferences.edit().putString("pc_ip_address", ipAddress).apply()
                Toast.makeText(requireContext(), "IP 주소가 저장되었습니다.", Toast.LENGTH_SHORT).show()
            }
        }

        binding.testButton.setOnClickListener {
            val ipAddress = binding.ipAddressInput.text.toString()
            if (ipAddress.isNotEmpty()) {
                Toast.makeText(requireContext(), "연결 테스트 중...", Toast.LENGTH_SHORT).show()
                fragmentScope.launch {
                    sendTestMessage(ipAddress, "200000")
                }
            } else {
                Toast.makeText(requireContext(), "IP 주소를 먼저 입력하고 저장하세요.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun sendTestMessage(ip: String, message: String) {
        try {
            val pcPort = 9999
            Socket(ip, pcPort).use { socket ->
                OutputStreamWriter(socket.getOutputStream(), "UTF-8").use { writer ->
                    writer.write(message)
                    writer.flush()
                }
            }
            activity?.runOnUiThread {
                Toast.makeText(requireContext(), "클라이언트에 연결되었습니다.", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            Log.e("ConnectionFragment", "클라이언트 연결 실패", e)
            activity?.runOnUiThread {
                Toast.makeText(requireContext(), "클라이언트 연결에 실패했습니다.", Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
