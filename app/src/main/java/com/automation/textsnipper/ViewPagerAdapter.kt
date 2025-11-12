package com.automation.textsnipper

import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter

class ViewPagerAdapter(fragmentActivity: FragmentActivity) : FragmentStateAdapter(fragmentActivity) {

    override fun getItemCount(): Int = 3

    override fun createFragment(position: Int): Fragment {
        return when (position) {
            0 -> ConnectionFragment()
            1 -> KeywordFragment()
            2 -> SettingsFragment()
            else -> throw IllegalStateException("Invalid position: $position")
        }
    }
}
