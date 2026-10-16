package com.automation.textsnipper

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingKeyTest {
    @Test
    fun acceptsFourTo128Characters() {
        for (key in listOf("1234", "abcd", "가나다라", "\uD83D\uDE00".repeat(4), "가".repeat(128))) {
            assertTrue(SmsApi.isValidKey(key))
        }
    }

    @Test
    fun rejectsShortLongAndWhitespaceKeys() {
        for (key in listOf("", "abc", "가나", "x".repeat(129), "ab cd", "abcd\n")) {
            assertFalse(SmsApi.isValidKey(key))
        }
    }
}
