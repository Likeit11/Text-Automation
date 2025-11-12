package com.automation.textsnipper

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import com.automation.textsnipper.databinding.FragmentKeywordBinding

class KeywordFragment : Fragment() {

    private var _binding: FragmentKeywordBinding? = null
    private val binding get() = _binding!!

    private lateinit var keywordAdapter: ArrayAdapter<String>
    private val keywordList = mutableListOf<String>()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentKeywordBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setupListView()
        loadKeywords()

        binding.addKeywordFab.setOnClickListener {
            showAddKeywordDialog()
        }

        binding.keywordListView.setOnItemLongClickListener { _, _, position, _ ->
            showDeleteKeywordDialog(position)
            true
        }
    }

    private fun setupListView() {
        keywordAdapter = ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, keywordList)
        binding.keywordListView.adapter = keywordAdapter
    }

    private fun loadKeywords() {
        val sharedPreferences = requireActivity().getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val keywords = sharedPreferences.getStringSet("keywords", emptySet()) ?: emptySet()
        keywordList.clear()
        keywordList.addAll(keywords)
        keywordAdapter.notifyDataSetChanged()
    }

    private fun saveKeywords() {
        val sharedPreferences = requireActivity().getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        sharedPreferences.edit().putStringSet("keywords", keywordList.toSet()).apply()
    }

    private fun showAddKeywordDialog() {
        val editText = EditText(requireContext())
        AlertDialog.Builder(requireContext())
            .setTitle("새 키워드 추가")
            .setView(editText)
            .setPositiveButton("추가") { _, _ ->
                val keyword = editText.text.toString()
                if (keyword.isNotEmpty()) {
                    keywordList.add(keyword)
                    keywordAdapter.notifyDataSetChanged()
                    saveKeywords()
                } else {
                    Toast.makeText(requireContext(), "키워드를 입력하세요.", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("취소", null)
            .show()
    }

    private fun showDeleteKeywordDialog(position: Int) {
        AlertDialog.Builder(requireContext())
            .setTitle("키워드 삭제")
            .setMessage("'${keywordList[position]}' 키워드를 삭제하시겠습니까?")
            .setPositiveButton("삭제") { _, _ ->
                keywordList.removeAt(position)
                keywordAdapter.notifyDataSetChanged()
                saveKeywords()
            }
            .setNegativeButton("취소", null)
            .show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
