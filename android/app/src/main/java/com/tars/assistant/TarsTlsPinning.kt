package com.tars.assistant

import android.content.SharedPreferences
import android.net.Uri
import android.net.http.SslCertificate
import android.net.http.SslError
import android.os.Build
import java.io.ByteArrayInputStream
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

object TarsTlsPinning {
    const val KEY_CERT_FP = "pinned_cert_sha256"

    private val SHA256_HEX_RE = Regex("^[0-9a-fA-F]{64}$")
    private val IPV4_RE = Regex("""^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$""")
    private val TS_DOMAIN_RE = Regex("""^[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net$""")

    fun isValidFingerprint(fp: String?): Boolean {
        return !fp.isNullOrBlank() && SHA256_HEX_RE.matches(fp.trim())
    }

    fun savePinnedFingerprint(prefs: SharedPreferences, fp: String?) {
        val clean = fp?.trim()?.lowercase() ?: ""
        if (isValidFingerprint(clean)) {
            prefs.edit().putString(KEY_CERT_FP, clean).apply()
        }
    }

    fun getPinnedFingerprint(prefs: SharedPreferences): String {
        val fp = prefs.getString(KEY_CERT_FP, "")?.trim()?.lowercase() ?: ""
        return if (isValidFingerprint(fp)) fp else ""
    }

    fun isAllowedTarsHost(hostRaw: String?): Boolean {
        val host = hostRaw?.lowercase()?.trim() ?: return false
        if (host == "localhost" || host == "127.0.0.1") return true
        if (TS_DOMAIN_RE.matches(host)) return true
        val match = IPV4_RE.matchEntire(host) ?: return false
        val octets = match.groupValues.drop(1).mapNotNull { it.toIntOrNull() }
        if (octets.size != 4 || octets.any { it < 0 || it > 255 }) return false
        val (a, b, _, _) = octets
        // RFC1918 LAN privada y CGNAT Tailscale (100.64.0.0/10)
        if (a == 192 && b == 168) return true
        if (a == 10) return true
        if (a == 172 && b in 16..31) return true
        if (a == 100 && b in 64..127) return true
        return false
    }

    fun isAllowedTarsOrigin(origin: Uri?): Boolean {
        if (origin == null) return false
        val scheme = origin.scheme?.lowercase() ?: return false
        return scheme == "https" && isAllowedTarsHost(origin.host)
    }

    fun sha256Hex(cert: X509Certificate): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(cert.encoded)
        val sb = StringBuilder(digest.size * 2)
        for (b in digest) {
            sb.append(String.format("%02x", b))
        }
        return sb.toString()
    }

    fun constantTimeEqualsHex(a: String, b: String): Boolean {
        if (a.length != b.length || a.isEmpty()) return false
        return MessageDigest.isEqual(
            a.lowercase().toByteArray(Charsets.US_ASCII),
            b.lowercase().toByteArray(Charsets.US_ASCII)
        )
    }

    fun extractX509Certificate(sslCert: SslCertificate?): X509Certificate? {
        if (sslCert == null) return null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            sslCert.x509Certificate?.let { return it }
        }
        return try {
            val bundle = SslCertificate.saveState(sslCert)
            val bytes = bundle.getByteArray("x509-certificate") ?: return null
            val factory = CertificateFactory.getInstance("X.509")
            factory.generateCertificate(ByteArrayInputStream(bytes)) as? X509Certificate
        } catch (e: Exception) {
            null
        }
    }

    fun matchesPinnedSslError(error: SslError?, prefs: SharedPreferences): Boolean {
        if (error == null) return false
        val uri = try {
            Uri.parse(error.url)
        } catch (e: Exception) {
            return false
        }
        if (!isAllowedTarsOrigin(uri)) return false
        val pinned = getPinnedFingerprint(prefs)
        if (pinned.isEmpty()) return false
        val x509 = extractX509Certificate(error.certificate) ?: return false
        return constantTimeEqualsHex(sha256Hex(x509), pinned)
    }

    fun applyPinnedTls(conn: HttpsURLConnection, prefs: SharedPreferences) {
        val pinned = getPinnedFingerprint(prefs)
        if (pinned.isEmpty()) {
            return
        }
        try {
            val tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
            tmf.init(null as KeyStore?)
            val systemTm = tmf.trustManagers.filterIsInstance<X509TrustManager>().firstOrNull()

            val pinningTm = object : X509TrustManager {
                override fun checkClientTrusted(chain: Array<X509Certificate>?, authType: String?) {
                    systemTm?.checkClientTrusted(chain, authType)
                }

                override fun checkServerTrusted(chain: Array<X509Certificate>?, authType: String?) {
                    if (chain.isNullOrEmpty()) {
                        throw CertificateException("Cadena de certificados vacia")
                    }
                    try {
                        systemTm?.checkServerTrusted(chain, authType)
                        return
                    } catch (systemEx: CertificateException) {
                        val leafFp = sha256Hex(chain[0])
                        if (constantTimeEqualsHex(leafFp, pinned)) {
                            return
                        }
                        throw systemEx
                    }
                }

                override fun getAcceptedIssuers(): Array<X509Certificate> {
                    return systemTm?.acceptedIssuers ?: emptyArray()
                }
            }

            val sslContext = SSLContext.getInstance("TLS")
            sslContext.init(null, arrayOf<TrustManager>(pinningTm), SecureRandom())
            conn.sslSocketFactory = sslContext.socketFactory

            val defaultVerifier = HttpsURLConnection.getDefaultHostnameVerifier()
            conn.hostnameVerifier = HostnameVerifier { hostname, session ->
                if (defaultVerifier.verify(hostname, session)) {
                    return@HostnameVerifier true
                }
                if (!isAllowedTarsHost(hostname)) {
                    return@HostnameVerifier false
                }
                try {
                    val peerCert = session.peerCertificates.firstOrNull() as? X509Certificate
                        ?: return@HostnameVerifier false
                    constantTimeEqualsHex(sha256Hex(peerCert), pinned)
                } catch (e: Exception) {
                    false
                }
            }
        } catch (e: Exception) {
            // Si falla la configuracion de pinning, se mantiene validacion TLS por defecto del sistema
        }
    }
}
