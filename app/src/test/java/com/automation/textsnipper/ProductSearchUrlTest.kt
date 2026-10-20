package com.automation.textsnipper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProductSearchUrlTest {
    @Test
    fun acceptsOnly9temsSearchResults() {
        val url = ProductSearchUrl.parse("https://9tems.com/product/search.html?banner_action=&keyword=MODEL+%26%2B%23")
        assertEquals("MODEL &+#", url?.queryParameter("keyword"))
    }

    @Test
    fun rejectsOtherOriginsPathsAndEmptySearches() {
        for (url in listOf(
            "http://9tems.com/product/search.html?keyword=MODEL",
            "https://9tems.com.evil.example/product/search.html?keyword=MODEL",
            "https://9tems.com:8443/product/search.html?keyword=MODEL",
            "https://9tems.com/other?keyword=MODEL",
            "https://user@9tems.com/product/search.html?keyword=MODEL",
            "https://9tems.com/product/search.html?keyword=",
            "javascript:alert(1)"
        )) assertNull(ProductSearchUrl.parse(url))
    }
}
