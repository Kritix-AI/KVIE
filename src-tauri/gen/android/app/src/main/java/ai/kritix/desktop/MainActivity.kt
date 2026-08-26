package ai.kritix.desktop

import ai.kritix.kviekeyboard.SetupActivity
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.enableEdgeToEdge
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : TauriActivity() {

  companion object {
    @JvmStatic
    var instance: MainActivity? = null

    @JvmStatic
    fun openKeyboardSettingsStatic() {
      instance?.openKeyboardSettingsInternal()
    }

    @JvmStatic
    fun showKeyboardPickerStatic() {
      instance?.showKeyboardPickerInternal()
    }
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    instance = this
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)

    // Request Audio permissions upfront for mobile voice dictation
    if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
      ActivityCompat.requestPermissions(
        this,
        arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.MODIFY_AUDIO_SETTINGS),
        101
      )
    }
  }

  override fun onPostCreate(savedInstanceState: Bundle?) {
    super.onPostCreate(savedInstanceState)
    attachBridgeWithPolling()
  }

  override fun onResume() {
    super.onResume()
    instance = this
    attachBridgeWithPolling()
  }

  override fun onDestroy() {
    if (instance == this) instance = null
    super.onDestroy()
  }

  private fun attachBridgeWithPolling() {
    val handler = Handler(Looper.getMainLooper())
    var attempts = 0
    val runnable = object : Runnable {
      override fun run() {
        val attached = setupWebView(window.decorView)
        if (!attached && attempts < 30) {
          attempts++
          handler.postDelayed(this, 200)
        }
      }
    }
    handler.post(runnable)
  }

  private fun setupWebView(root: View): Boolean {
    if (root is WebView) {
      try {
        root.settings.javaScriptEnabled = true
        root.addJavascriptInterface(AndroidBridge(this), "AndroidKeyboardBridge")

        // Intercept action links and intents so ERR_UNKNOWN_URL_SCHEME is never shown
        val origClient = root.webViewClient
        root.webViewClient = object : WebViewClient() {
          override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
            val url = request?.url?.toString() ?: return false
            if (url.startsWith("kvie-action://") || url.startsWith("intent:")) {
              handleCustomUrl(url)
              return true
            }
            return origClient?.shouldOverrideUrlLoading(view, request) ?: super.shouldOverrideUrlLoading(view, request)
          }

          @Deprecated("Deprecated in Java")
          override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
            if (url != null && (url.startsWith("kvie-action://") || url.startsWith("intent:"))) {
              handleCustomUrl(url)
              return true
            }
            return origClient?.shouldOverrideUrlLoading(view, url) ?: super.shouldOverrideUrlLoading(view, url)
          }
        }
        return true
      } catch (e: Exception) {
        return false
      }
    }
    if (root is ViewGroup) {
      for (i in 0 until root.childCount) {
        if (setupWebView(root.getChildAt(i))) {
          return true
        }
      }
    }
    return false
  }

  fun handleCustomUrl(url: String) {
    if (url.contains("open-keyboard-settings") || url.contains("INPUT_METHOD_SETTINGS")) {
      openKeyboardSettingsInternal()
    } else if (url.contains("show-keyboard-picker")) {
      showKeyboardPickerInternal()
    } else if (url.contains("request-mic")) {
      requestMicPermissionInternal()
    } else if (url.contains("open-setup")) {
      try {
        val intent = Intent(this, SetupActivity::class.java).apply {
          addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
      } catch (_: Exception) {}
    }
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

  class AndroidBridge(private val activity: MainActivity) {
    @JavascriptInterface
    fun isAndroid(): Boolean = true

    @JavascriptInterface
    fun openKeyboardSettings() {
      activity.openKeyboardSettingsInternal()
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
      activity.handleCustomUrl("kvie-action://open-setup")
    }

    @JavascriptInterface
    fun isMicPermissionGranted(): Boolean {
      return ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    }

    @JavascriptInterface
    fun isKeyboardEnabled(): Boolean {
      val enabled = Settings.Secure.getString(activity.contentResolver, Settings.Secure.ENABLED_INPUT_METHODS) ?: ""
      return enabled.contains("KVIEInputMethodService") || enabled.contains("ai.kritix.kviekeyboard")
    }
  }
}
