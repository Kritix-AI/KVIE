package ai.kritix.desktop

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
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
  override fun onCreate(savedInstanceState: Bundle?) {
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
    attachBridgeToWebView(window.decorView)
  }

  override fun onResume() {
    super.onResume()
    attachBridgeToWebView(window.decorView)
  }

  private fun attachBridgeToWebView(root: View) {
    if (root is WebView) {
      root.addJavascriptInterface(AndroidBridge(this), "AndroidKeyboardBridge")
      return
    }
    if (root is ViewGroup) {
      for (i in 0 until root.childCount) {
        attachBridgeToWebView(root.getChildAt(i))
      }
    }
  }

  class AndroidBridge(private val activity: MainActivity) {
    @JavascriptInterface
    fun isAndroid(): Boolean = true

    @JavascriptInterface
    fun openKeyboardSettings() {
      activity.runOnUiThread {
        val intent = Intent(Settings.ACTION_INPUT_METHOD_SETTINGS).apply {
          addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        activity.startActivity(intent)
      }
    }

    @JavascriptInterface
    fun showKeyboardPicker() {
      activity.runOnUiThread {
        val imm = activity.getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.showInputMethodPicker()
      }
    }

    @JavascriptInterface
    fun requestMicPermission() {
      activity.runOnUiThread {
        ActivityCompat.requestPermissions(
          activity,
          arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.MODIFY_AUDIO_SETTINGS),
          101
        )
      }
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
