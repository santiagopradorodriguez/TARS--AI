package com.tars.assistant

import android.Manifest
import android.annotation.SuppressLint
import android.annotation.TargetApi
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.LayoutInflater
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
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

    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (filePathCallback == null) return@registerForActivityResult
        val uris: Array<Uri>? = if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            val data = result.data
            if (data?.clipData != null) {
                val count = data.clipData!!.itemCount
                val list = mutableListOf<Uri>()
                for (i in 0 until count) {
                    list.add(data.clipData!!.getItemAt(i).uri)
                }
                list.toTypedArray()
            } else if (data?.data != null) {
                arrayOf(data.data!!)
            } else {
                null
            }
        } else {
            null
        }
        filePathCallback?.onReceiveValue(uris)
        filePathCallback = null
    }

    private var pageLoadWatchdogJob: Job? = null

    companion object {
        private const val PREFS_NAME = "tars_app_config"
        private const val KEY_LOCAL_IP = "local_ip"
        private const val KEY_TS_DOMAIN = "ts_domain"
        private const val TARS_MSG_NOTIFICATION_ID = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        loadingLayout = findViewById(R.id.loadingLayout)
        loadingText = findViewById(R.id.loadingText)

        findViewById<View>(R.id.btnCancelConnecting)?.setOnClickListener {
            pageLoadWatchdogJob?.cancel()
            loadingLayout.visibility = View.GONE
            val savedLocal = prefs.getString(KEY_LOCAL_IP, "") ?: ""
            val savedTs = prefs.getString(KEY_TS_DOMAIN, "") ?: ""
            showConnectionFailedDialog(if (savedLocal.isNotBlank()) savedLocal else savedTs)
        }

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
        s.setSupportMultipleWindows(true)
        s.javaScriptCanOpenWindowsAutomatically = true
        s.userAgentString = s.userAgentString + " TARS-Android-Shell/1.0"

        webView.addJavascriptInterface(AndroidBridge(this), "AndroidBridge")

        webView.setDownloadListener { url, _, _, _, _ ->
            openExternalIntent(url)
        }

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
                    pageLoadWatchdogJob?.cancel()
                    loadingLayout.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                }
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback

                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "*/*"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    fileChooserLauncher.launch(intent)
                    return true
                } catch (e: Exception) {
                    this@MainActivity.filePathCallback?.onReceiveValue(null)
                    this@MainActivity.filePathCallback = null
                    return false
                }
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                val tempWebView = WebView(this@MainActivity)
                tempWebView.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                        val url = request?.url?.toString() ?: return false
                        openExternalIntent(url)
                        return true
                    }

                    @Deprecated("Deprecated in Java")
                    override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                        if (url == null) return false
                        openExternalIntent(url)
                        return true
                    }
                }
                transport.webView = tempWebView
                resultMsg.sendToTarget()
                return true
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
                pageLoadWatchdogJob?.cancel()
                loadingLayout.visibility = View.GONE
                swipeRefresh.isRefreshing = false
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                return handleUriNavigation(uri)
            }

            @Deprecated("Deprecated in Java")
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                if (url == null) return false
                return handleUriNavigation(Uri.parse(url))
            }

            override fun onReceivedError(view: WebView?, errorCode: Int, description: String?, failingUrl: String?) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                pageLoadWatchdogJob?.cancel()
                loadingLayout.visibility = View.GONE
                swipeRefresh.isRefreshing = false
                showConnectionFailedDialog(failingUrl ?: "")
            }

            @TargetApi(Build.VERSION_CODES.M)
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    pageLoadWatchdogJob?.cancel()
                    loadingLayout.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                    showConnectionFailedDialog(request.url?.toString() ?: "")
                }
            }
        }
    }

    private fun resolveAbsoluteUrl(rawUrl: String): String {
        var clean = rawUrl.trim()
        if (clean.startsWith("file:///api/")) {
            clean = "/" + clean.removePrefix("file://").removePrefix("/")
        }
        if (clean.startsWith("http://") || clean.startsWith("https://")) {
            return clean
        }
        val currentBase = webView.url ?: ""
        return if (clean.startsWith("/")) {
            try {
                val baseUri = Uri.parse(currentBase)
                "${baseUri.scheme}://${baseUri.authority}$clean"
            } catch (e: Exception) {
                clean
            }
        } else {
            clean
        }
    }

    private fun openExternalIntent(rawUrl: String) {
        val url = resolveAbsoluteUrl(rawUrl)
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        } catch (e: Exception) {
            try {
                val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                startActivity(browserIntent)
            } catch (e2: Exception) {
                Toast.makeText(this@MainActivity, "No se pudo abrir el enlace: ${e2.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun handleUriNavigation(uri: Uri): Boolean {
        val urlStr = uri.toString()
        val scheme = uri.scheme?.lowercase() ?: return false
        if (scheme == "intent") {
            try {
                val intent = Intent.parseUri(urlStr, Intent.URI_INTENT_SCHEME)
                startActivity(intent)
                return true
            } catch (e: Exception) {
                return true
            }
        }
        if (urlStr.endsWith(".apk") || uri.path?.contains("/api/download") == true) {
            openExternalIntent(urlStr)
            return true
        }
        val host = uri.host ?: ""
        val isTarsHost = host.contains("192.168.") ||
                host.contains("100.") ||
                host.contains("127.0.0.1") ||
                host.contains("localhost") ||
                host.contains("ts.net")
        if (!isTarsHost && (scheme == "http" || scheme == "https")) {
            openExternalIntent(urlStr)
            return true
        }
        return false
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
        fun clearNotifications() {
            runOnUiThread {
                val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                notificationManager.cancelAll()
            }
        }

        @JavascriptInterface
        fun isNotificationPermissionGranted(): Boolean {
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (!notificationManager.areNotificationsEnabled()) {
                return false
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = notificationManager.getNotificationChannel("tars_messages_channel")
                if (channel != null && channel.importance == NotificationManager.IMPORTANCE_NONE) {
                    return false
                }
            }
            return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            } else {
                true
            }
        }

        @JavascriptInterface
        fun requestNotificationPermission() {
            runOnUiThread {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                        ActivityCompat.requestPermissions(
                            this@MainActivity,
                            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                            RECORD_AUDIO_PERMISSION_CODE + 1
                        )
                    }
                }
            }
        }

        @JavascriptInterface
        fun openNotificationSettings() {
            runOnUiThread {
                try {
                    val intent = Intent().apply {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            action = android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS
                            putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, packageName)
                        } else {
                            action = "android.settings.APP_NOTIFICATION_SETTINGS"
                            putExtra("app_package", packageName)
                            putExtra("app_uid", applicationInfo.uid)
                        }
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    }
                    startActivity(intent)
                } catch (e: Exception) {
                    try {
                        val intent = Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                            data = Uri.fromParts("package", packageName, null)
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        }
                        startActivity(intent)
                    } catch (e2: Exception) {}
                }
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

        @JavascriptInterface
        fun openUrl(url: String) {
            runOnUiThread {
                openExternalIntent(url)
            }
        }

        @JavascriptInterface
        fun downloadFile(url: String, filename: String) {
            runOnUiThread {
                openExternalIntent(url)
            }
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

            notificationManager.notify(TARS_MSG_NOTIFICATION_ID, notification)
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

        pageLoadWatchdogJob?.cancel()
        loadingLayout.visibility = View.VISIBLE
        loadingText.text = getString(R.string.connecting)

        activityScope.launch {
            val chosenUrl = withContext(Dispatchers.IO) {
                // Lista de candidatos ordenada
                val candidates = mutableListOf<String>()
                if (targetLocal.isNotBlank()) candidates.add(targetLocal)
                if (targetTs.isNotBlank() && !candidates.contains(targetTs)) candidates.add(targetTs)

                val known = listOf(
                    "https://192.168.1.19:8443", // Lenovo Yoga Local
                    "https://100.115.244.2:8443", // Lenovo Yoga Tailscale
                    "https://192.168.1.59:8443", // Pop!_OS Local
                    "https://100.118.12.94:8443"  // Pop!_OS Tailscale
                )
                for (k in known) {
                    if (!candidates.contains(k)) candidates.add(k)
                }

                // Sondeo concurrente en paralelo para conexión ultrarrápida (<500ms)
                val deferredProbes = candidates.map { url ->
                    async {
                        val isLocal = url.contains("192.168.") || url.contains("127.0.0.1")
                        val timeout = if (isLocal) 500 else 750
                        if (testEndpointReachable(url, timeoutMs = timeout)) url else null
                    }
                }

                val reachable = deferredProbes.awaitAll().filterNotNull()
                if (reachable.isEmpty()) return@withContext null

                // Preferencias: 1) local guardado si respondió, 2) TS guardado si respondió, 3) primer local disponible, 4) primer TS
                if (targetLocal in reachable) return@withContext targetLocal
                if (targetTs in reachable) return@withContext targetTs

                val firstLocal = reachable.firstOrNull { it.contains("192.168.") }
                firstLocal ?: reachable.first()
            }

            if (chosenUrl != null && chosenUrl.isNotBlank()) {
                webView.loadUrl(chosenUrl)
                // Watchdog: si después de 3.5s sigue el cartel de conectando, forzar escape
                pageLoadWatchdogJob?.cancel()
                pageLoadWatchdogJob = activityScope.launch {
                    kotlinx.coroutines.delay(3500)
                    if (loadingLayout.visibility == View.VISIBLE) {
                        loadingLayout.visibility = View.GONE
                        swipeRefresh.isRefreshing = false
                        val curUrl = webView.url ?: ""
                        if (curUrl.isBlank() || curUrl == "about:blank") {
                            showConnectionFailedDialog(chosenUrl)
                        }
                    }
                }
            } else {
                loadingLayout.visibility = View.GONE
                showConnectionFailedDialog(if (targetLocal.isNotBlank()) targetLocal else targetTs)
            }
        }
    }

    private fun showConnectionFailedDialog(failedUrl: String) {
        if (isFinishing || isDestroyed) return

        val cleanFailed = if (failedUrl.isNotBlank()) failedUrl else "el servidor"
        val options = arrayOf(
            "💻 Lenovo Yoga (Wi-Fi: 192.168.1.19)",
            "🌐 Lenovo Yoga (Tailscale: 100.115.244.2)",
            "🖥️ Pop!_OS (Wi-Fi: 192.168.1.59)",
            "🌐 Pop!_OS (Tailscale: 100.118.12.94)",
            "🔍 Escanear red Wi-Fi automáticamente",
            "⚙️ Ingresar IP o dominio manualmente"
        )

        MaterialAlertDialogBuilder(this)
            .setTitle("Error al conectar con TARS")
            .setMessage("No se pudo conectar a $cleanFailed.\nElige a qué PC conectar:")
            .setItems(options) { dialog, which ->
                dialog.dismiss()
                when (which) {
                    0 -> saveAndConnect("https://192.168.1.19:8443", "100.115.244.2:8443")
                    1 -> saveAndConnect("192.168.1.19:8443", "https://100.115.244.2:8443")
                    2 -> saveAndConnect("https://192.168.1.59:8443", "100.118.12.94:8443")
                    3 -> saveAndConnect("192.168.1.59:8443", "https://100.118.12.94:8443")
                    4 -> autoScanWifiAndConnect()
                    5 -> showSettingsDialog(isFirstRun = false)
                }
            }
            .setPositiveButton("Reintentar") { dialog, _ ->
                dialog.dismiss()
                val savedLocal = prefs.getString(KEY_LOCAL_IP, "") ?: ""
                val savedTs = prefs.getString(KEY_TS_DOMAIN, "") ?: ""
                connectToBestNetwork(savedLocal, savedTs)
            }
            .setNegativeButton("Ajustes") { dialog, _ ->
                dialog.dismiss()
                showSettingsDialog(isFirstRun = false)
            }
            .setCancelable(false)
            .show()
    }

    private fun saveAndConnect(localIp: String, tsDomain: String) {
        prefs.edit()
            .putString(KEY_LOCAL_IP, localIp)
            .putString(KEY_TS_DOMAIN, tsDomain)
            .apply()
        connectToBestNetwork(localIp, tsDomain)
    }

    private fun autoScanWifiAndConnect() {
        val localIp = getLocalWifiIpAddress()
        if (localIp == null) {
            Toast.makeText(this, "Conecta el Wi-Fi para buscar servidores TARS.", Toast.LENGTH_LONG).show()
            showSettingsDialog(isFirstRun = false)
            return
        }
        loadingLayout.visibility = View.VISIBLE
        loadingText.text = "Escaneando red Wi-Fi..."
        val baseSubnet = localIp.substringBeforeLast(".") + "."

        scanSubnetForTars(
            baseSubnet,
            onFound = { foundUrl ->
                loadingLayout.visibility = View.GONE
                Toast.makeText(this@MainActivity, "TARS encontrado: $foundUrl", Toast.LENGTH_SHORT).show()
                saveAndConnect(foundUrl, prefs.getString(KEY_TS_DOMAIN, "") ?: "")
            },
            onFinished = { found ->
                if (!found) {
                    loadingLayout.visibility = View.GONE
                    Toast.makeText(this@MainActivity, "No se encontró ningún TARS activo en $baseSubnet*", Toast.LENGTH_LONG).show()
                    showConnectionFailedDialog("la red $baseSubnet*")
                }
            }
        )
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
