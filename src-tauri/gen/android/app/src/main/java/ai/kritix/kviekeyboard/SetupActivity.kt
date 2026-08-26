package ai.kritix.kviekeyboard

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class SetupActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
            setBackgroundColor(0xFF121214.toInt())
        }

        layout.addView(TextView(this).apply {
            text = "KVIE Voice Keyboard Setup"
            textSize = 22f
            setTextColor(0xFFD7FB52.toInt())
            setPadding(0, 0, 0, 32)
        })

        layout.addView(Button(this).apply {
            text = "1. Enable in System Keyboard Settings"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
            }
        })

        layout.addView(Button(this).apply {
            text = "2. Switch to KVIE Keyboard"
            setOnClickListener {
                val imm = getSystemService(INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager
                imm?.showInputMethodPicker()
            }
        })

        layout.addView(Button(this).apply {
            text = "3. Grant Microphone Permission"
            setOnClickListener {
                if (ContextCompat.checkSelfPermission(this@SetupActivity, Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    ActivityCompat.requestPermissions(
                        this@SetupActivity,
                        arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.MODIFY_AUDIO_SETTINGS),
                        100
                    )
                }
            }
        })

        setContentView(layout)
    }
}
