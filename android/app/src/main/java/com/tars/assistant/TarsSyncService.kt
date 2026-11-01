package com.tars.assistant

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class TarsSyncService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + Job())
    private var syncJob: Job? = null
    private lateinit var prefs: SharedPreferences

    companion object {
        private const val PREFS_NAME = "tars_app_config"
        private const val KEY_LAST_WORKING_URL = "last_working_url"
        private const val CHANNEL_FOREGROUND_ID = "tars_sync_service_channel"
        private const val CHANNEL_MESSAGE_ID = "tars_messages_channel"
        private const val NOTIFICATION_FOREGROUND_ID = 9001
        private const val NOTIFICATION_MSG_ID = 1001

        fun startService(context: Context) {
            val intent = Intent(context, TarsSyncService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopService(context: Context) {
            val intent = Intent(context, TarsSyncService::class.java)
            context.stopService(intent)
        }
    }

    private var lastNotifiedIndex = 0

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        createNotificationChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = createForegroundNotification()
        startForeground(NOTIFICATION_FOREGROUND_ID, notification)

        if (syncJob == null || syncJob?.isActive == false) {
            startSyncLoop()
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        syncJob?.cancel()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            val fgChannel = NotificationChannel(
                CHANNEL_FOREGROUND_ID,
                "TARS Conexión en Segundo Plano",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Mantiene a TARS conectado para recibir respuestas al instante"
                setShowBadge(false)
            }
            notificationManager.createNotificationChannel(fgChannel)

            val msgChannel = NotificationChannel(
                CHANNEL_MESSAGE_ID,
                "Mensajes de TARS",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificaciones de respuestas de TARS"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 250, 100, 250)
            }
            notificationManager.createNotificationChannel(msgChannel)
        }
    }

    private fun createForegroundNotification(): android.app.Notification {
        val launchIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_FOREGROUND_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("TARS en línea")
            .setContentText("Sincronización activa en segundo plano")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()
    }

    private fun startSyncLoop() {
        syncJob = serviceScope.launch {
            initLastIndex()

            while (isActive) {
                try {
                    val currentUrl = prefs.getString(KEY_LAST_WORKING_URL, "") ?: ""
                    if (currentUrl.isNotBlank()) {
                        pollSync(currentUrl)
                    }
                } catch (e: Exception) {
                    // Manejo silencioso de reconexión
                }
                delay(2000)
            }
        }
    }

    private suspend fun initLastIndex() {
        try {
            val currentUrl = prefs.getString(KEY_LAST_WORKING_URL, "") ?: ""
            if (currentUrl.isBlank()) return
            val syncEndpoint = "${currentUrl.trimEnd('/')}/api/sync?last_index=999999"
            val responseText = executeHttpRequest(syncEndpoint, timeoutMs = 3000)
            if (responseText != null) {
                val json = JSONObject(responseText)
                lastNotifiedIndex = json.optInt("step_index", 0)
            }
        } catch (e: Exception) {}
    }

    private fun pollSync(baseUrl: String) {
        val syncEndpoint = "${baseUrl.trimEnd('/')}/api/sync?last_index=$lastNotifiedIndex"
        val responseText = executeHttpRequest(syncEndpoint, timeoutMs = 3500) ?: return

        val json = JSONObject(responseText)
        val hasNew = json.optBoolean("has_new", false)
        val stepIndex = json.optInt("step_index", 0)
        val content = json.optString("content", "").trim()
        val procInfo = json.optJSONObject("processing_info")
        val isProcessing = procInfo?.optBoolean("is_processing", false) ?: false

        if (hasNew && stepIndex > lastNotifiedIndex && !isProcessing && content.isNotEmpty()) {
            lastNotifiedIndex = stepIndex
            showIncomingMessageNotification("TARS • Antigravity", content)
        } else if (stepIndex > lastNotifiedIndex && isProcessing) {
            // El modelo sigue respondiendo
        } else if (stepIndex > lastNotifiedIndex && !isProcessing) {
            lastNotifiedIndex = stepIndex
        }
    }

    private fun showIncomingMessageNotification(title: String, message: String) {
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val launchIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_MESSAGE_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        notificationManager.notify(NOTIFICATION_MSG_ID, notification)
    }

    private fun executeHttpRequest(urlString: String, timeoutMs: Int): String? {
        var conn: HttpURLConnection? = null
        return try {
            val url = URL(urlString)
            if (url.protocol.equals("https", ignoreCase = true)) {
                val trustAll = arrayOf<TrustManager>(object : X509TrustManager {
                    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                    override fun checkClientTrusted(certs: Array<X509Certificate>, authType: String) {}
                    override fun checkServerTrusted(certs: Array<X509Certificate>, authType: String) {}
                })
                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, trustAll, SecureRandom())
                val httpsConn = url.openConnection() as HttpsURLConnection
                httpsConn.sslSocketFactory = sslContext.socketFactory
                httpsConn.setHostnameVerifier { _, _ -> true }
                conn = httpsConn
            } else {
                conn = url.openConnection() as HttpURLConnection
            }

            conn.connectTimeout = timeoutMs
            conn.readTimeout = timeoutMs
            conn.requestMethod = "GET"
            conn.setRequestProperty("User-Agent", "TARS-Android-SyncService/1.0")

            if (conn.responseCode == 200) {
                BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
            } else {
                null
            }
        } catch (e: Exception) {
            null
        } finally {
            conn?.disconnect()
        }
    }
}
