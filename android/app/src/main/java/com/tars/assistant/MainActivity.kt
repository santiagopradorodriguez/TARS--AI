package com.tars.assistant

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.http.SslError
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.URL
import java.security.SecureRandom
import java.security.cert.X509Certificate
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.webkit.JavascriptInterface
import androidx.core.app.NotificationCompat
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var loadingLayout: LinearLayout
    private lateinit var loadingText: TextView
    private lateinit var prefs: SharedPreferences

    private var speechRecognizer: SpeechRecognizer? = null
    private var recognitionIntent: Intent? = null
    private var isWakeWordListening = false
    private val mainHandler = Handler(Looper.getMainLooper())

    private val activityScope = CoroutineScope(Dispatchers.Main + Job())
    private val RECORD_AUDIO_PERMISSION_CODE = 101

    companion object {
        private const val PREFS_NAME = "tars_app_config"
        private const val KEY_LOCAL_IP = "local_ip"
        private const val KEY_TS_DOMAIN = "ts_domain"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        loadingLayout = findViewById(R.id.loadingLayout)
        loadingText = findViewById(R.id.loadingText)

        setupWebView()
        setupBackNavigation()
        setupSwipeRefresh()
        requestAppPermissions()

        val savedLocal = prefs.getString(KEY_LOCAL_IP, "") ?: ""
        val savedTs = prefs.getString(KEY_TS_DOMAIN, "") ?: ""

        if (savedLocal.isBlank() && savedTs.isBlank()) {
            showSettingsDialog(isFirstRun = true)
        } else {
            connectToBestNetwork(savedLocal, savedTs)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val s = webView.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.databaseEnabled = true
        s.mediaPlaybackRequiresUserGesture = false
        s.allowFileAccess = true
        s.cacheMode = WebSettings.LOAD_DEFAULT
        s.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        s.userAgentString = s.userAgentString + " TARS-Android-Shell/1.0"

        webView.addJavascriptInterface(AndroidBridge(this), "AndroidBridge")

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.let {
                    val resources = it.resources
                    for (r in resources) {
                        if (r == PermissionRequest.RESOURCE_AUDIO_CAPTURE) {
                            it.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                            return
                        }
                    }
                    it.grant(resources)
                }
            }

            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress >= 85) {
                    loadingLayout.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                }
            }
        }

        webView.webViewClient = object : WebViewClient() {
            @SuppressLint("WebViewClientOnReceivedSslError")
            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                // Proceder en conexiones locales o seguras de TARS sin bloquear por certificado autofirmado
                handler?.proceed()
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                loadingLayout.visibility = View.GONE
                swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    showExitOrSettingsDialog()
                }
            }
        })
    }

    private fun setupSwipeRefresh() {
        swipeRefresh.setColorSchemeResources(R.color.primary)
        // Deshabilitar pull-to-refresh para que el usuario pueda scrollear libremente hacia arriba en el chat
        swipeRefresh.isEnabled = false
        swipeRefresh.setOnRefreshListener {
            webView.reload()
        }
    }

    private fun requestAppPermissions() {
        val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val needed = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (needed.isNotEmpty()) {
            ActivityCompat.requestPermissions(
                this,
                needed.toTypedArray(),
                RECORD_AUDIO_PERMISSION_CODE
            )
        }
    }

    inner class AndroidBridge(private val context: Context) {
        @JavascriptInterface
        fun showNotification(title: String, message: String) {
            runOnUiThread {
                triggerNativeNotification(title, message)
            }
        }

        @JavascriptInterface
        fun isSpeechAvailable(): Boolean {
            return SpeechRecognizer.isRecognitionAvailable(context)
        }

        @JavascriptInterface
        fun startWakeWord(): Boolean {
            runOnUiThread {
                startNativeWakeWord()
            }
            return true
        }

        @JavascriptInterface
        fun stopWakeWord(): Boolean {
            runOnUiThread {
                stopNativeWakeWord()
            }
            return true
        }
    }

    private fun initNativeSpeechRecognizer() {
        if (speechRecognizer != null) return
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onError(error: Int) {
                    if (isWakeWordListening) {
                        mainHandler.postDelayed({
                            if (isWakeWordListening) {
                                try {
                                    speechRecognizer?.startListening(recognitionIntent)
                                } catch (e: Exception) {}
                            }
                        }, 500)
                    }
                }
                override fun onResults(results: Bundle?) {
                    handleSpeechRecognition(results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION), isFinal = true)
                }
                override fun onPartialResults(partialResults: Bundle?) {
                    handleSpeechRecognition(partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION), isFinal = false)
                }
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
        }

        recognitionIntent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-AR")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }
    }

    private fun handleSpeechRecognition(matches: ArrayList<String>?, isFinal: Boolean) {
        if (matches.isNullOrEmpty() || !isWakeWordListening) return
        for (phrase in matches) {
            val lower = phrase.lowercase().trim()
            val regex = Regex("""\b(?:hola\s+|che\s+|oye\s+|ey\s+)?(?:tars|tas|tar|tor|star|task)\b(.*)""", RegexOption.IGNORE_CASE)
            val match = regex.find(lower)
            if (match != null) {
                val command = match.groupValues.getOrNull(1)?.trim() ?: ""
                val escaped = command.replace("\\", "\\\\").replace("'", "\\'").replace("\"", "\\\"").replace("\n", " ")
                stopNativeWakeWord()
                webView.post {
                    webView.evaluateJavascript("window.onNativeWakeWordDetected('$escaped');", null)
                }
                return
            }
        }
        if (isFinal && isWakeWordListening) {
            mainHandler.postDelayed({
                if (isWakeWordListening) {
                    try {
                        speechRecognizer?.startListening(recognitionIntent)
                    } catch (e: Exception) {}
                }
            }, 350)
        }
    }

    private fun startNativeWakeWord() {
        isWakeWordListening = true
        initNativeSpeechRecognizer()
        try {
            speechRecognizer?.startListening(recognitionIntent)
        } catch (e: Exception) {}
    }

    private fun stopNativeWakeWord() {
        isWakeWordListening = false
        try {
            speechRecognizer?.stopListening()
        } catch (e: Exception) {}
    }

    private fun triggerNativeNotification(title: String, message: String) {
        try {
            val channelId = "tars_messages_channel"
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = NotificationChannel(
                    channelId,
                    "Mensajes de TARS",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Notificaciones de respuestas de TARS"
                    enableVibration(true)
                    vibrationPattern = longArrayOf(0, 250, 100, 250)
                }
                notificationManager.createNotificationChannel(channel)
            }

            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(this, channelId)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(if (title.isNotBlank()) title else "TARS")
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .build()

            notificationManager.notify(System.currentTimeMillis().toInt(), notification)
        } catch (e: Exception) {
            // Manejo seguro si la notificacion no puede ser despachada
        }
    }

    private fun normalizeUrl(raw: String, defaultPort: Int = 8443): String {
        var input = raw.trim().trimEnd('/')
        if (input.isBlank()) return ""
        if (!input.startsWith("http://") && !input.startsWith("https://")) {
            input = "https://$input"
        }
        val uri = URL(input)
        return if (uri.port == -1) {
            "${uri.protocol}://${uri.host}:$defaultPort"
        } else {
            input
        }
    }

    private fun connectToBestNetwork(localIp: String, tsDomain: String) {
        val targetLocal = normalizeUrl(localIp)
        val targetTs = normalizeUrl(tsDomain)

        loadingLayout.visibility = View.VISIBLE
        loadingText.text = getString(R.string.connecting)

        activityScope.launch {
            val chosenUrl = withContext(Dispatchers.IO) {
                var canUseLocal = false
                if (targetLocal.isNotBlank()) {
                    canUseLocal = testEndpointReachable(targetLocal, timeoutMs = 450)
                }
                if (canUseLocal) {
                    targetLocal
                } else if (targetTs.isNotBlank()) {
                    targetTs
                } else {
                    targetLocal
                }
            }

            if (chosenUrl.isNotBlank()) {
                webView.loadUrl(chosenUrl)
            } else {
                loadingLayout.visibility = View.GONE
                showSettingsDialog(isFirstRun = true)
            }
        }
    }

    private fun testEndpointReachable(baseUrl: String, timeoutMs: Int): Boolean {
        try {
            val probeUrl = "$baseUrl/api/connection_mode"
            val url = URL(probeUrl)
            val conn = url.openConnection() as HttpURLConnection

            if (conn is HttpsURLConnection) {
                val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
                    override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
                    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
                    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
                })
                val sc = SSLContext.getInstance("SSL")
                sc.init(null, trustAllCerts, SecureRandom())
                conn.sslSocketFactory = sc.socketFactory
                conn.setHostnameVerifier { _, _ -> true }
            }

            conn.connectTimeout = timeoutMs
            conn.readTimeout = timeoutMs
            conn.requestMethod = "GET"
            conn.instanceFollowRedirects = false
            conn.connect()
            val code = conn.responseCode
            conn.disconnect()
            return code in 200..399
        } catch (e: Exception) {
            return false
        }
    }

    private fun getLocalWifiIpAddress(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
            for (intf in interfaces) {
                if (intf.isLoopback || !intf.isUp) continue
                for (addr in intf.inetAddresses) {
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        val host = addr.hostAddress ?: ""
                        if (host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.")) {
                            return host
                        }
                    }
                }
            }
        } catch (e: Exception) {}
        return null
    }

    private fun scanSubnetForTars(baseSubnet: String, onFound: (String) -> Unit, onFinished: (Boolean) -> Unit) {
        activityScope.launch(Dispatchers.IO) {
            var found = false
            val candidateIps = (1..254).map { "$baseSubnet$it" }
            val sortedIps = candidateIps.sortedBy { ip ->
                val lastOctet = ip.substringAfterLast(".").toIntOrNull() ?: 0
                when {
                    lastOctet in 50..99 -> 0
                    lastOctet in 1..30 -> 1
                    lastOctet in 100..200 -> 2
                    else -> 3
                }
            }

            for (chunk in sortedIps.chunked(25)) {
                if (found) break
                val jobs = chunk.map { ip ->
                    async {
                        val testUrl = "https://$ip:8443"
                        if (testEndpointReachable(testUrl, timeoutMs = 350)) {
                            testUrl
                        } else null
                    }
                }
                val results = jobs.awaitAll()
                val detected = results.firstOrNull { it != null }
                if (detected != null) {
                    found = true
                    withContext(Dispatchers.Main) {
                        onFound(detected)
                    }
                    break
                }
            }
            withContext(Dispatchers.Main) {
                onFinished(found)
            }
        }
    }

    private fun showSettingsDialog(isFirstRun: Boolean = false) {
        val inflater = LayoutInflater.from(this)
        val dialogView = inflater.inflate(R.layout.dialog_settings, null)
        val editLocal = dialogView.findViewById<EditText>(R.id.editLocalIp)
        val editTs = dialogView.findViewById<EditText>(R.id.editTsDomain)
        val btnScan = dialogView.findViewById<View>(R.id.btnScanLan)
        val progressScan = dialogView.findViewById<View>(R.id.progressScanLan)
        val textStatus = dialogView.findViewById<TextView>(R.id.textScanStatus)

        editLocal.setText(prefs.getString(KEY_LOCAL_IP, ""))
        editTs.setText(prefs.getString(KEY_TS_DOMAIN, ""))

        btnScan?.setOnClickListener {
            val localIp = getLocalWifiIpAddress()
            if (localIp == null) {
                textStatus?.text = "Conecta el Wi-Fi para buscar."
                return@setOnClickListener
            }
            val baseSubnet = localIp.substringBeforeLast(".") + "."
            btnScan.isEnabled = false
            progressScan?.visibility = View.VISIBLE
            textStatus?.text = "Buscando en $baseSubnet*..."

            scanSubnetForTars(
                baseSubnet,
                onFound = { foundUrl ->
                    editLocal.setText(foundUrl)
                    textStatus?.text = "Detectado: $foundUrl"
                    Toast.makeText(this@MainActivity, "Servidor TARS detectado", Toast.LENGTH_SHORT).show()
                },
                onFinished = { found ->
                    btnScan.isEnabled = true
                    progressScan?.visibility = View.GONE
                    if (!found) {
                        textStatus?.text = "No se encontro servidor en $baseSubnet*"
                    }
                }
            )
        }

        if (isFirstRun && editLocal.text.isBlank()) {
            dialogView.postDelayed({
                btnScan?.performClick()
            }, 400)
        }

        val builder = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.settings_title)
            .setView(dialogView)
            .setCancelable(!isFirstRun)
            .setPositiveButton(R.string.btn_save) { dialog, _ ->
                val newLocal = editLocal.text.toString().trim()
                val newTs = editTs.text.toString().trim()

                prefs.edit()
                    .putString(KEY_LOCAL_IP, newLocal)
                    .putString(KEY_TS_DOMAIN, newTs)
                    .apply()

                dialog.dismiss()
                connectToBestNetwork(newLocal, newTs)
            }

        if (!isFirstRun) {
            builder.setNegativeButton(R.string.btn_cancel) { dialog, _ ->
                dialog.dismiss()
            }
        }

        builder.show()
    }

    private fun showExitOrSettingsDialog() {
        MaterialAlertDialogBuilder(this)
            .setTitle("TARS")
            .setMessage("¿Deseas salir o reconfigurar las direcciones de red?")
            .setPositiveButton("Salir") { _, _ ->
                finish()
            }
            .setNeutralButton("Ajustes de Red") { _, _ ->
                showSettingsDialog(isFirstRun = false)
            }
            .setNegativeButton("Continuar", null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopNativeWakeWord()
        try {
            speechRecognizer?.destroy()
        } catch (e: Exception) {}
    }
}
