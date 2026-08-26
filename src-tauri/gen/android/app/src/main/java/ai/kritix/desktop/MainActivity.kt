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
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : TauriActivity() {

  companion object {
    @JvmStatic
    var instance: MainActivity? = null
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
      try {
        root.settings.javaScriptEnabled = true
        root.settings.domStorageEnabled = true
        root.settings.mediaPlaybackRequiresUserGesture = false
        root.webChromeClient = object : android.webkit.WebChromeClient() {
          override fun onPermissionRequest(request: android.webkit.PermissionRequest?) {
            runOnUiThread {
              request?.grant(request.resources)
            }
          }
        }
        root.addJavascriptInterface(AndroidBridge(this), "AndroidKeyboardBridge")
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
  }
}
