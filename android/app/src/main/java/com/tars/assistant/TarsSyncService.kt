package com.tars.assistant

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.Manifest
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection

class TarsSyncService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var syncJob: Job? = null
    private lateinit var prefs: SharedPreferences

    companion object {
        private const val PREFS_NAME = "tars_app_config"
        private const val KEY_LAST_WORKING_URL = "last_working_url"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val CHANNEL_FOREGROUND_ID = "tars_sync_service_channel"
        private const val CHANNEL_MESSAGE_ID = "tars_messages_channel"
        private const val NOTIFICATION_FOREGROUND_ID = 9001
        private const val NOTIFICATION_MSG_ID = 1001
        private const val ACTION_SET_CALL_MODE = "com.tars.assistant.ACTION_SET_CALL_MODE"
        private const val EXTRA_CALL_ACTIVE = "extra_call_active"

        fun setCallActive(context: Context, active: Boolean) {
            try {
                val intent = Intent(context, TarsSyncService::class.java).apply {
                    action = ACTION_SET_CALL_MODE
                    putExtra(EXTRA_CALL_ACTIVE, active)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (e: Exception) {}
        }

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
    private var lastSyncedUrl = ""
    private var isCallActive = false

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        createNotificationChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_SET_CALL_MODE) {
            isCallActive = intent.getBooleanExtra(EXTRA_CALL_ACTIVE, false)
        }
        val notification = createForegroundNotification(isCallActive)
        val hasMicPerm = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        val fgsType = when {
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && isCallActive && hasMicPerm ->
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ->
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            else -> 0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_FOREGROUND_ID, notification, fgsType)

        if (syncJob == null || syncJob?.isActive == false) {
            startSyncLoop()
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        syncJob?.cancel()
        serviceScope.cancel()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            val fgChannel = NotificationChannel(
                CHANNEL_FOREGROUND_ID,
                "TARS Conexion en Segundo Plano",
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

    private fun createForegroundNotification(inCall: Boolean = false): android.app.Notification {
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
            .setContentTitle(if (inCall) "TARS en llamada de voz" else "TARS en linea")
            .setContentText(if (inCall) "Audio bidireccional activo en segundo plano" else "Sincronizacion activa en segundo plano")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()
    }

    private fun startSyncLoop() {
        syncJob = serviceScope.launch {
            while (isActive) {
                try {
                    val currentUrl = (prefs.getString(KEY_LAST_WORKING_URL, "") ?: "").trim()
                    if (currentUrl.isNotBlank()) {
                        if (currentUrl != lastSyncedUrl) {
                            if (initLastIndex(currentUrl)) {
                                lastSyncedUrl = currentUrl
                            }
                        } else {
                            pollSync(currentUrl)
                        }
                    }
                } catch (e: Exception) {
                    // Manejo silencioso de reconexion
                }
                delay(2000)
            }
        }
    }

    private suspend fun initLastIndex(baseUrl: String): Boolean {
        return try {
            if (baseUrl.isBlank()) return false
            val syncEndpoint = "${baseUrl.trimEnd('/')}/api/sync?last_index=999999"
            val responseText = executeHttpRequest(syncEndpoint, timeoutMs = 3000)
            if (responseText != null) {
                val json = JSONObject(responseText)
                lastNotifiedIndex = json.optInt("step_index", 0)
                true
            } else {
                false
            }
        } catch (e: Exception) {
            false
        }
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
            showIncomingMessageNotification("TARS - Antigravity", content)
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
            if (!url.protocol.equals("https", ignoreCase = true)) {
                return null
            }
            if (!TarsTlsPinning.isAllowedTarsHost(url.host)) {
                return null
            }
            val httpsConn = url.openConnection() as HttpsURLConnection
            TarsTlsPinning.applyPinnedTls(httpsConn, prefs)
            conn = httpsConn

            conn.connectTimeout = timeoutMs
            conn.readTimeout = timeoutMs
            conn.requestMethod = "GET"
            conn.setRequestProperty("User-Agent", "TARS-Android-SyncService/1.0")
            val tok = prefs.getString(KEY_AUTH_TOKEN, "") ?: ""
            if (tok.isNotBlank()) {
                conn.setRequestProperty("X-TARS-Token", tok)
            }

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
