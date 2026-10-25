package ai.kritix.kviekeyboard

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Not the keyboard itself — just the launcher screen that walks the
 * user through enabling the keyboard and granting mic permission.
 * The OS won't let a keyboard's own process trigger the system
 * "enable this keyboard" screen or a runtime permission dialog, so a
 * normal activity has to do it.
 */
class SetupActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
        }

        layout.addView(TextView(this).apply {
            text = "Set up KVIE Keyboard"
            textSize = 20f
        })

        layout.addView(Button(this).apply {
            text = "1. Enable in system keyboard settings"
            setOnClickListener {
                startActivity(android.content.Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
            }
        })

        layout.addView(Button(this).apply {
            text = "2. Grant microphone permission"
            setOnClickListener {
                if (ContextCompat.checkSelfPermission(this@SetupActivity, Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    ActivityCompat.requestPermissions(
                        this@SetupActivity,
                        arrayOf(Manifest.permission.RECORD_AUDIO),
                        100
                    )
                }
            }
        })

        setContentView(layout)
    }
}
