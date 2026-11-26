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
import android.os.PowerManager
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.LayoutInflater
import android.view.View
import android.webkit.CookieManager
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
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.Socket
import java.net.URL
import org.json.JSONObject
import javax.net.ssl.HttpsURLConnection

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
    private var callWakeLock: PowerManager.WakeLock? = null

    private val activityScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
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
    private var activeSettingsDialog: androidx.appcompat.app.AlertDialog? = null

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            startQrScannerInternal()
        } else {
            Toast.makeText(this, "Se requiere permiso de camara para escanear el codigo QR.", Toast.LENGTH_LONG).show()
        }
    }

    private fun launchQrScanner() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startQrScannerInternal()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun startQrScannerInternal() {
        val opts = ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            setPrompt("Apunta al codigo QR de TARS en tu PC")
            setBeepEnabled(true)
            setOrientationLocked(false)
        }
        qrScannerLauncher.launch(opts)
    }

    private val qrScannerLauncher = registerForActivityResult(ScanContract()) { result ->
        val raw = result.contents?.trim()
        if (!raw.isNullOrBlank()) {
            try {
                val uri = Uri.parse(raw)
                if (!isAllowedTarsOrigin(uri)) {
                    Toast.makeText(this, "QR no valido para TARS: debe ser HTTPS local o Tailscale.", Toast.LENGTH_LONG).show()
                    return@registerForActivityResult
                }
                val port = if (uri.port != -1) uri.port else 8443
                val host = uri.host ?: return@registerForActivityResult
                val baseUrl = "https://$host:$port"
                val token = uri.getQueryParameter("token")?.trim() ?: ""
                val certFp = uri.getQueryParameter("fp")?.trim() ?: ""

                val editor = prefs.edit().putString(KEY_LAST_WORKING_URL, baseUrl)
                if (token.isNotBlank()) {
                    editor.putString(KEY_AUTH_TOKEN, token)
                }
                val isLanHost = host.startsWith("192.168.") || host.startsWith("10.") || host.startsWith("172.") || host == "localhost" || host == "127.0.0.1"
                if (isLanHost) {
                    editor.putString(KEY_LOCAL_IP, baseUrl)
                } else {
                    editor.putString(KEY_TS_DOMAIN, baseUrl)
                }
                editor.apply()

                if (TarsTlsPinning.isValidFingerprint(certFp)) {
                    TarsTlsPinning.savePinnedFingerprint(prefs, certFp)
                }

                activeSettingsDialog?.dismiss()
                activeSettingsDialog = null
                try {
                    TarsSyncService.startService(this@MainActivity)
                } catch (e: Exception) {}

                val loadTarget = if (token.isNotBlank()) "$baseUrl/?token=${Uri.encode(token)}" else baseUrl
                loadingLayout.visibility = View.VISIBLE
                loadingText.text = getString(R.string.connecting)
                webView.loadUrl(loadTarget)
                startPageLoadWatchdog(baseUrl)
                Toast.makeText(this, "Vinculado por QR: $host", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this, "Error leyendo QR: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    companion object {
        private const val PREFS_NAME = "tars_app_config"
        private const val KEY_LOCAL_IP = "local_ip"
        private const val KEY_TS_DOMAIN = "ts_domain"
        private const val KEY_LAST_WORKING_URL = "last_working_url"
        private const val KEY_AUTH_TOKEN = "auth_token"
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
        s.allowFileAccess = false
        s.cacheMode = WebSettings.LOAD_DEFAULT
        s.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        s.setSupportMultipleWindows(true)
        s.javaScriptCanOpenWindowsAutomatically = false
        s.userAgentString = s.userAgentString + " TARS-Android-Shell/1.0"
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false)

        webView.addJavascriptInterface(AndroidBridge(this), "AndroidBridge")

        webView.setDownloadListener { url, _, _, _, _ ->
            openExternalIntent(url)
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.let {
                    if (!isAllowedTarsOrigin(it.origin)) {
                        it.deny()
                        return
                    }
                    val allowed = it.resources.filter { r -> r == PermissionRequest.RESOURCE_AUDIO_CAPTURE }.toTypedArray()
                    if (allowed.isNotEmpty()) {
                        it.grant(allowed)
                    } else {
                        it.deny()
                    }
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
            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                // Pinning SHA-256 estricto del certificado vinculado por QR para redes locales autofirmadas
                if (TarsTlsPinning.matchesPinnedSslError(error, prefs)) {
                    handler?.proceed()
                } else {
                    handler?.cancel()
                    pageLoadWatchdogJob?.cancel()
                    loadingLayout.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                    Toast.makeText(
                        this@MainActivity,
                        "Certificado HTTPS no verificado. Escanea el codigo QR en tu PC para vincular el certificado local.",
                        Toast.LENGTH_LONG
                    ).show()
                    showConnectionFailedDialog(error?.url ?: "")
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                CookieManager.getInstance().flush()
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

            @Deprecated("Deprecated in Java")
            override fun onReceivedError(view: WebView?, errorCode: Int, description: String?, failingUrl: String?) {
                super.onReceivedError(view, errorCode, description, failingUrl)
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                    pageLoadWatchdogJob?.cancel()
                    loadingLayout.visibility = View.GONE
                    swipeRefresh.isRefreshing = false
                    showConnectionFailedDialog(failingUrl ?: "")
                }
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
        val parsed = try { Uri.parse(url) } catch (e: Exception) { return }
        val scheme = parsed.scheme?.lowercase() ?: return
        if (scheme != "https" && scheme != "http") {
            return
        }
        try {
            val intent = Intent(Intent.ACTION_VIEW, parsed).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        } catch (e: Exception) {
            try {
                val browserIntent = Intent(Intent.ACTION_VIEW, parsed)
                startActivity(browserIntent)
            } catch (e2: Exception) {
                Toast.makeText(this@MainActivity, "No se pudo abrir el enlace: ${e2.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun isAllowedTarsHost(hostRaw: String?): Boolean {
        return TarsTlsPinning.isAllowedTarsHost(hostRaw)
    }

    private fun isAllowedTarsOrigin(origin: Uri?): Boolean {
        return TarsTlsPinning.isAllowedTarsOrigin(origin)
    }

    private fun handleUriNavigation(uri: Uri): Boolean {
        val urlStr = uri.toString()
        val scheme = uri.scheme?.lowercase() ?: return false
        if (scheme == "intent") {
            // Bloquear Intent Redirection (F-19): solo permitir browsable https sin component ni selector
            try {
                val intent = Intent.parseUri(urlStr, Intent.URI_INTENT_SCHEME)
                intent.addCategory(Intent.CATEGORY_BROWSABLE)
                intent.component = null
                intent.selector = null
                val dataScheme = intent.data?.scheme?.lowercase()
                if (dataScheme == "https") {
                    startActivity(intent)
                }
                return true
            } catch (e: Exception) {
                return true
            }
        }
        if (urlStr.endsWith(".apk") || uri.path?.contains("/api/download") == true) {
            openExternalIntent(urlStr)
            return true
        }
        val isTarsHost = scheme == "https" && isAllowedTarsHost(uri.host)
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

        @JavascriptInterface
        fun acquireCallWakeLock() {
            runOnUiThread {
                acquireCallWakeLockInternal()
            }
        }

        @JavascriptInterface
        fun releaseCallWakeLock() {
            runOnUiThread {
                releaseCallWakeLockInternal()
            }
        }
    }

    @SuppressLint("WakelockTimeout")
    private fun acquireCallWakeLockInternal() {
        try {
            if (callWakeLock == null) {
                val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
                callWakeLock = powerManager.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "TARS::VoiceCallWakeLock"
                ).apply {
                    setReferenceCounted(false)
                }
            }
            if (callWakeLock?.isHeld == false) {
                callWakeLock?.acquire(10 * 60 * 1000L)
            }
            TarsSyncService.setCallActive(this, true)
        } catch (e: Exception) {}
    }

    private fun releaseCallWakeLockInternal() {
        try {
            if (callWakeLock?.isHeld == true) {
                callWakeLock?.release()
            }
            TarsSyncService.setCallActive(this, false)
        } catch (e: Exception) {}
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
                val quoted = JSONObject.quote(command)
                stopNativeWakeWord()
                webView.post {
                    webView.evaluateJavascript("window.onNativeWakeWordDetected($quoted);", null)
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
        if (input.startsWith("http://", ignoreCase = true)) {
            input = "https://" + input.substring(7)
        } else if (!input.startsWith("https://", ignoreCase = true)) {
            input = "https://$input"
        }
        return try {
            val uri = URL(input)
            val host = uri.host ?: return ""
            if (!isAllowedTarsHost(host)) return ""
            val port = if (uri.port == -1) defaultPort else uri.port
            "https://$host:$port"
        } catch (e: Exception) {
            ""
        }
    }

    private fun connectToBestNetwork(localIp: String, tsDomain: String) {
        val targetLocal = normalizeUrl(localIp)
        val targetTs = normalizeUrl(tsDomain)
        val lastWorking = normalizeUrl(prefs.getString(KEY_LAST_WORKING_URL, "") ?: "")

        pageLoadWatchdogJob?.cancel()
        loadingLayout.visibility = View.VISIBLE
        loadingText.text = getString(R.string.connecting)

        activityScope.launch {
            val chosenUrl = withContext(Dispatchers.IO) {
                val candidates = mutableListOf<String>()
                if (targetLocal.isNotBlank()) candidates.add(targetLocal)
                if (targetTs.isNotBlank() && !candidates.contains(targetTs)) candidates.add(targetTs)
                if (lastWorking.isNotBlank() && !candidates.contains(lastWorking)) candidates.add(lastWorking)

                if (candidates.isEmpty()) return@withContext null

                val deferredProbes = candidates.map { url ->
                    async {
                        val isLocal = url.contains("192.168.") || url.contains("10.") || url.contains("172.") || url.contains("127.0.0.1")
                        val timeout = if (isLocal) 900 else 1500
                        if (testEndpointReachable(url, timeoutMs = timeout)) url else null
                    }
                }

                val reachable = deferredProbes.awaitAll().filterNotNull()
                if (reachable.isEmpty()) return@withContext null

                if (targetLocal in reachable) return@withContext targetLocal
                if (targetTs in reachable) return@withContext targetTs
                reachable.first()
            }

            if (chosenUrl != null && chosenUrl.isNotBlank()) {
                prefs.edit().putString(KEY_LAST_WORKING_URL, chosenUrl).apply()
                try {
                    TarsSyncService.startService(this@MainActivity)
                } catch (e: Exception) {}
                val savedToken = prefs.getString(KEY_AUTH_TOKEN, "") ?: ""
                val urlWithToken = if (savedToken.isNotBlank() && !chosenUrl.contains("token=")) {
                    "${chosenUrl.trimEnd('/')}/?token=${Uri.encode(savedToken)}"
                } else {
                    chosenUrl
                }
                webView.loadUrl(urlWithToken)
                startPageLoadWatchdog(chosenUrl)
            } else {
                loadingLayout.visibility = View.GONE
                showConnectionFailedDialog(if (targetLocal.isNotBlank()) targetLocal else targetTs)
            }
        }
    }

    private fun startPageLoadWatchdog(targetUrl: String) {
        pageLoadWatchdogJob?.cancel()
        pageLoadWatchdogJob = activityScope.launch {
            kotlinx.coroutines.delay(4500)
            if (loadingLayout.visibility == View.VISIBLE) {
                loadingLayout.visibility = View.GONE
                swipeRefresh.isRefreshing = false
                val curUrl = webView.url ?: ""
                if (curUrl.isBlank() || curUrl == "about:blank") {
                    showConnectionFailedDialog(targetUrl)
                }
            }
        }
    }

    private fun showConnectionFailedDialog(failedUrl: String) {
        if (isFinishing || isDestroyed) return

        val cleanFailed = if (failedUrl.isNotBlank()) failedUrl else "el servidor"
        val options = arrayOf(
            "Escanear codigo QR de la PC (recomendado)",
            "Escanear red Wi-Fi automaticamente",
            "Ingresar IP o dominio manualmente"
        )

        MaterialAlertDialogBuilder(this)
            .setTitle("Error al conectar con TARS")
            .setMessage("No se pudo conectar a $cleanFailed.\nElige como reconectar:")
            .setItems(options) { dialog, which ->
                dialog.dismiss()
                when (which) {
                    0 -> launchQrScanner()
                    1 -> autoScanWifiAndConnect()
                    2 -> showSettingsDialog(isFirstRun = false)
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
        var conn: HttpURLConnection? = null
        return try {
            val probeUrl = "${baseUrl.trimEnd('/')}/api/health"
            val url = URL(probeUrl)
            if (!url.protocol.equals("https", ignoreCase = true) || !isAllowedTarsHost(url.host)) {
                return false
            }
            val httpsConn = url.openConnection() as HttpsURLConnection
            TarsTlsPinning.applyPinnedTls(httpsConn, prefs)
            conn = httpsConn

            httpsConn.connectTimeout = timeoutMs
            httpsConn.readTimeout = timeoutMs
            httpsConn.requestMethod = "GET"
            httpsConn.instanceFollowRedirects = false
            val tok = prefs.getString(KEY_AUTH_TOKEN, "") ?: ""
            if (tok.isNotBlank()) {
                httpsConn.setRequestProperty("X-TARS-Token", tok)
            }
            httpsConn.connect()
            val code = httpsConn.responseCode
            code in 200..399
        } catch (e: Exception) {
            false
        } finally {
            conn?.disconnect()
        }
    }

    private fun testTcpPortOpen(host: String, port: Int, timeoutMs: Int): Boolean {
        return try {
            Socket().use { sock ->
                sock.connect(InetSocketAddress(host, port), timeoutMs)
                true
            }
        } catch (e: Exception) {
            false
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
                        val hasPin = TarsTlsPinning.getPinnedFingerprint(prefs).isNotEmpty()
                        val reachable = if (hasPin) {
                            testEndpointReachable(testUrl, timeoutMs = 400)
                        } else {
                            testTcpPortOpen(ip, 8443, 300)
                        }
                        if (reachable) testUrl else null
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
        val btnScanQr = dialogView.findViewById<View>(R.id.btnScanQr)
        val btnScan = dialogView.findViewById<View>(R.id.btnScanLan)

        btnScanQr?.setOnClickListener {
            launchQrScanner()
        }
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

        activeSettingsDialog = builder.show()
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
        pageLoadWatchdogJob?.cancel()
        activityScope.cancel()
        releaseCallWakeLockInternal()
        stopNativeWakeWord()
        try {
            speechRecognizer?.destroy()
        } catch (e: Exception) {}
    }
}
