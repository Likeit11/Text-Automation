package com.automation.textsnipper

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

object ProductSearchUrl {
    fun parse(value: String): HttpUrl? {
        val url = value.toHttpUrlOrNull() ?: return null
        if (!url.isHttps || url.host != "9tems.com" || url.port != 443 ||
            url.encodedPath != "/product/search.html" || url.username.isNotEmpty() ||
            url.password.isNotEmpty() || url.fragment != null) return null
        val model = url.queryParameter("keyword") ?: return null
        if (model.isBlank() || model.codePointCount(0, model.length) > 200) return null
        return url
    }
}
