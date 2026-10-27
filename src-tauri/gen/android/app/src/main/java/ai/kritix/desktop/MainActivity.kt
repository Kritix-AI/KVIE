package ai.kritix.desktop

import ai.kritix.kviekeyboard.SetupActivity
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.enableEdgeToEdge
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.util.WeakHashMap

class MainActivity : TauriActivity() {

  companion object {
    @JvmStatic
    var instance: MainActivity? = null
    private val bridgedWebViews = WeakHashMap<WebView, Boolean>()
  }

  private val mainHandler = Handler(Looper.getMainLooper())

  override fun onCreate(savedInstanceState: Bundle?) {
    instance = this
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)

    // Request Audio and Bluetooth permissions upfront for mobile voice dictation
    val requiredPermissions = mutableListOf(
      Manifest.permission.RECORD_AUDIO,
      Manifest.permission.MODIFY_AUDIO_SETTINGS
    )
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
      requiredPermissions.add(Manifest.permission.BLUETOOTH_CONNECT)
    }

    val missing = requiredPermissions.filter {
      ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
    }

    if (missing.isNotEmpty()) {
      ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
    }

    startBridgeAttachmentPolling()
  }

  override fun onResume() {
    super.onResume()
    instance = this
    startBridgeAttachmentPolling()
  }

  override fun onDestroy() {
    if (instance == this) instance = null
    super.onDestroy()
  }

  private fun startBridgeAttachmentPolling() {
    var attempts = 0
    val runnable = object : Runnable {
      override fun run() {
        if (!attachBridgeToWebView(window.decorView) && attempts < 40) {
          attempts++
          mainHandler.postDelayed(this, 150)
        }
      }
    }
    mainHandler.post(runnable)
  }

  private fun attachBridgeToWebView(root: View): Boolean {
    if (root is WebView) {
      if (bridgedWebViews.containsKey(root)) return true
      try {
        root.settings.javaScriptEnabled = true
        root.settings.domStorageEnabled = true
        root.settings.mediaPlaybackRequiresUserGesture = false
        root.settings.allowFileAccess = false
        root.settings.allowContentAccess = false
        root.settings.allowFileAccessFromFileURLs = false
        root.settings.allowUniversalAccessFromFileURLs = false
        root.settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        root.settings.javaScriptCanOpenWindowsAutomatically = false
        root.settings.setSupportMultipleWindows(false)
        root.settings.databaseEnabled = false
        val originalClient = if (WebViewFeature.isFeatureSupported(WebViewFeature.GET_WEB_VIEW_CLIENT)) {
          WebViewCompat.getWebViewClient(root)
        } else null
        root.webViewClient = object : WebViewClient() {
          override fun shouldOverrideUrlLoading(view: WebView, request: android.webkit.WebResourceRequest): Boolean {
            if (!isTrustedAppUri(request.url)) {
              view.removeJavascriptInterface("AndroidKeyboardBridge")
              return true
            }
            return originalClient?.shouldOverrideUrlLoading(view, request) ?: false
          }

          override fun shouldOverrideUrlLoading(view: WebView, url: String): Boolean {
            if (!isTrustedAppUri(Uri.parse(url))) {
              view.removeJavascriptInterface("AndroidKeyboardBridge")
              return true
            }
            return originalClient?.shouldOverrideUrlLoading(view, url) ?: false
          }

          override fun shouldInterceptRequest(view: WebView, request: android.webkit.WebResourceRequest): android.webkit.WebResourceResponse? =
            originalClient?.shouldInterceptRequest(view, request) ?: super.shouldInterceptRequest(view, request)

          override fun shouldInterceptRequest(view: WebView, url: String): android.webkit.WebResourceResponse? =
            originalClient?.shouldInterceptRequest(view, url) ?: super.shouldInterceptRequest(view, url)

          override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
            if (!isTrustedAppUri(Uri.parse(url))) {
              view.removeJavascriptInterface("AndroidKeyboardBridge")
              view.stopLoading()
              return
            }
            originalClient?.onPageStarted(view, url, favicon)
          }

          override fun onPageFinished(view: WebView, url: String) {
            originalClient?.onPageFinished(view, url)
          }
        }
        root.webChromeClient = object : android.webkit.WebChromeClient() {
          override fun onPermissionRequest(request: android.webkit.PermissionRequest?) {
            val permissionRequest = request ?: return
            val origin = permissionRequest.origin
            val trustedLocalOrigin = when (origin.scheme) {
              "http" -> (origin.host == "tauri.localhost" && origin.port in setOf(-1, 80)) ||
                (origin.host in setOf("localhost", "127.0.0.1", "10.0.2.2", "10.0.3.2") && origin.port == 5173)
              "https" -> origin.host in setOf("tauri.localhost", "localhost") && origin.port in setOf(-1, 443)
              else -> false
            }
            val requestedResources = permissionRequest.resources
            val audioOnly = requestedResources.isNotEmpty() && requestedResources.all {
              it == android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE
            }
            if (!trustedLocalOrigin || !audioOnly) {
              permissionRequest.deny()
              return
            }
            runOnUiThread {
              permissionRequest.grant(requestedResources)
            }
          }
        }
        root.addJavascriptInterface(AndroidBridge(this), "AndroidKeyboardBridge")
        bridgedWebViews[root] = true
        return true
      } catch (_: Exception) {
        return false
      }
    }
    if (root is ViewGroup) {
      for (i in 0 until root.childCount) {
        if (attachBridgeToWebView(root.getChildAt(i))) {
          return true
        }
      }
    }
    return false
  }

  private fun isTrustedAppUri(uri: Uri): Boolean = when (uri.scheme) {
    "http" -> (uri.host == "tauri.localhost" && uri.port in setOf(-1, 80)) ||
      (uri.host in setOf("localhost", "127.0.0.1", "10.0.2.2", "10.0.3.2") && uri.port == 5173)
    "https" -> uri.host in setOf("tauri.localhost", "localhost") && uri.port in setOf(-1, 443)
    "tauri" -> uri.host == "localhost"
    else -> false
  }

  fun openKeyboardSettingsInternal() {
    runOnUiThread {
      try {
        val intent = Intent(Settings.ACTION_INPUT_METHOD_SETTINGS).apply {
          addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
      } catch (e: Exception) {
        try {
          val intent = Intent(Settings.ACTION_SETTINGS).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
          }
          startActivity(intent)
        } catch (_: Exception) {}
      }
    }
  }

  fun showKeyboardPickerInternal() {
    runOnUiThread {
      try {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.showInputMethodPicker()
      } catch (_: Exception) {}
    }
  }

  fun requestMicPermissionInternal() {
    runOnUiThread {
      ActivityCompat.requestPermissions(
        this,
        arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.MODIFY_AUDIO_SETTINGS),
        101
      )
    }
  }

  fun openAccessibilitySettingsInternal() {
    runOnUiThread {
      try {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
          addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
      } catch (_: Exception) {}
    }
  }

  fun startFloatingMicInternal(): Boolean {
    if (!android.provider.Settings.canDrawOverlays(this)) {
      runOnUiThread {
        try {
          val intent = Intent(
            android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName")
          ).apply { addFlags(Intent.FLAG_ACTIVITY_NEW_TASK) }
          startActivity(intent)
        } catch (_: Exception) {}
      }
      return false
    }

    return try {
      startService(Intent(this, ai.kritix.kviekeyboard.FloatingMicService::class.java)) != null
    } catch (_: Exception) {
      false
    }
  }

  class AndroidBridge(private val activity: MainActivity) {
    @JavascriptInterface
    fun isAndroid(): Boolean = true

    @JavascriptInterface
    fun openKeyboardSettings() {
      activity.openKeyboardSettingsInternal()
    }

    @JavascriptInterface
    fun openAccessibilitySettings() {
      activity.openAccessibilitySettingsInternal()
    }

    @JavascriptInterface
    fun isAccessibilityEnabled(): Boolean {
      return ai.kritix.kviekeyboard.KVIEAccessibilityService.isAvailable
    }

    @JavascriptInterface
    fun startFloatingMic(): Boolean {
      return activity.startFloatingMicInternal()
    }

    @JavascriptInterface
    fun showKeyboardPicker() {
      activity.showKeyboardPickerInternal()
    }

    @JavascriptInterface
    fun requestMicPermission() {
      activity.requestMicPermissionInternal()
    }

    @JavascriptInterface
    fun openSetupActivity() {
      try {
        val intent = Intent(activity, SetupActivity::class.java).apply {
          addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        activity.startActivity(intent)
      } catch (_: Exception) {}
    }

    @JavascriptInterface
    fun setSelectedEngine(engineId: String) {
      val prefs = activity.getSharedPreferences("kvie_prefs", android.content.Context.MODE_PRIVATE)
      prefs.edit().putString("active_engine", engineId).apply()
    }

    @JavascriptInterface
    fun getSelectedEngine(): String {
      val prefs = activity.getSharedPreferences("kvie_prefs", android.content.Context.MODE_PRIVATE)
      return prefs.getString("active_engine", "android-speech-recognizer") ?: "android-speech-recognizer"
    }

    @JavascriptInterface
    fun setAccentColor(hexColor: String) {
      val prefs = activity.getSharedPreferences("kvie_prefs", android.content.Context.MODE_PRIVATE)
      prefs.edit().putString("accent_color", hexColor).apply()
    }

    @JavascriptInterface
    fun getAccentColor(): String {
      val prefs = activity.getSharedPreferences("kvie_prefs", android.content.Context.MODE_PRIVATE)
      return prefs.getString("accent_color", "#22d3ee") ?: "#22d3ee"
    }

    @JavascriptInterface
    fun isMicPermissionGranted(): Boolean {
      return ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    }

    @JavascriptInterface
    fun isKeyboardEnabled(): Boolean {
      try {
        val imm = activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as? InputMethodManager
        val enabledMethods = imm?.enabledInputMethodList ?: return false
        val pkg = activity.packageName
        for (method in enabledMethods) {
          if (method.packageName == pkg || method.serviceName.contains("KVIEInputMethodService") || method.id.contains(pkg)) {
            return true
          }
        }
      } catch (_: Exception) {}
      return false
    }

    @JavascriptInterface
    fun getRecordedSessions(): String {
      return ai.kritix.kviekeyboard.SessionManager.getSessionsJson(activity)
    }

    @JavascriptInterface
    fun recordSession(text: String, targetApp: String) {
      ai.kritix.kviekeyboard.SessionManager.recordSession(activity, text, targetApp)
    }

    @JavascriptInterface
    fun clearRecordedSessions() {
      ai.kritix.kviekeyboard.SessionManager.clearSessions(activity)
    }
  }
}
