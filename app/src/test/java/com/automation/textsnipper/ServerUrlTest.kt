package com.automation.textsnipper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ServerUrlTest {
    @Test
    fun addsHttpsToDomainAndTrimsWhitespace() {
        assertEquals("https://sms.netras.org", SmsApi.serverUrl(" sms.netras.org/ "))
        assertEquals("https://example.com:8443/sms", SmsApi.serverUrl("example.com:8443/sms/"))
    }

    @Test
    fun acceptsExistingHttpsAddress() {
        assertEquals("https://sms.netras.org", SmsApi.serverUrl("https://sms.netras.org/"))
    }

    @Test
    fun rejectsHttpAndInvalidAddresses() {
        for (address in listOf("http://sms.netras.org", "", "not a domain", "ftp://example.com")) {
            assertThrows(IllegalArgumentException::class.java) { SmsApi.serverUrl(address) }
        }
    }
}
