package com.automation.textsnipper

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import com.automation.textsnipper.databinding.FragmentSettingsBinding

class SettingsFragment : Fragment() {

    private var _binding: FragmentSettingsBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentSettingsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val sharedPreferences = requireActivity().getSharedPreferences("settings", Context.MODE_PRIVATE)

        // 저장된 호스트 주소 표시
        binding.hostAddress.text = sharedPreferences.getString("host_address", "Click to set address")

        // 호스트 주소 클릭 리스너
        binding.hostAddress.setOnClickListener {
            showHostAddressDialog()
        }

        // 버전 정보 표시
        try {
            val packageInfo = requireActivity().packageManager.getPackageInfo(requireActivity().packageName, 0)
            val versionName = packageInfo.versionName
            binding.versionInfo.text = versionName
        } catch (e: Exception) {
            binding.versionInfo.text = "N/A"
        }
    }

    private fun showHostAddressDialog() {
        val editText = EditText(requireContext()).apply {
            setText(binding.hostAddress.text)
        }

        AlertDialog.Builder(requireContext())
            .setTitle("Enter Host Address")
            .setView(editText)
            .setPositiveButton("Save") { _, _ ->
                val newHostAddress = editText.text.toString()
                binding.hostAddress.text = newHostAddress

                // SharedPreferences에 저장
                val sharedPreferences = requireActivity().getSharedPreferences("settings", Context.MODE_PRIVATE)
                with(sharedPreferences.edit()) {
                    putString("host_address", newHostAddress)
                    apply()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
