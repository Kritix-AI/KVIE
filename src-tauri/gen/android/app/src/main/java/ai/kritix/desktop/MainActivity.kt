package ai.kritix.desktop

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
        val attached = attachBridgeToWebView(window.decorView)
        if (!attached && attempts < 25) {
          attempts++
          handler.postDelayed(this, 250)
        }
      }
    }
    handler.post(runnable)
  }

  private fun attachBridgeToWebView(root: View): Boolean {
    if (root is WebView) {
      try {
        root.settings.javaScriptEnabled = true
        root.addJavascriptInterface(AndroidBridge(this), "AndroidKeyboardBridge")
        return true
      } catch (e: Exception) {
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
