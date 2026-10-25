package ai.kritix.kviekeyboard

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.InputType
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.Normalizer
import java.util.Locale

/**
 * KVIE – Production Keyboard
 *
 * Features
 *   • QWERTY text input with proper Enter key
 *   • Emoji panel (system Unicode emoji via Noto Color Emoji font)
 *   • Devanagari (Hindi) Inscript keyboard + live transliteration
 *   • Text snippet expansion (type shortcut → space → full text)
 *   • Voice dictation (Android SpeechRecognizer)
 *   • Auto-edit post-processing via backend
 *
 * Emoji note: Android ships Noto Color Emoji on API 19+.
 * We render emojis as plain text in Button widgets so the system
 * color-font engine draws them. This eliminates the "rectangular box"
 * problem that appears when emoji are forced through an ImageButton
 * or custom font path.
 */
class KVIEInputMethodService : InputMethodService() {

    // ── State ──────────────────────────────────────────────────────────────────
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var isShifted = false
    private var currentMode = Mode.TEXT        // TEXT | EMOJI | HINDI | SNIPPETS
    private var currentLang: Locale = Locale.ENGLISH
    private var lastBuffer = StringBuilder()

    private val scope = CoroutineScope(Dispatchers.Main)

    // ── Snippet map ────────────────────────────────────────────────────────────
    private val snippets = linkedMapOf(
        "brb" to "be right back",
        "omw" to "on my way",
        "tysm" to "thank you so much",
        "idk" to "I don't know",
        "np" to "no problem",
        "thx" to "thanks",
        "ty" to "thank you",
        "gm" to "good morning",
        "gn" to "good night",
        "pls" to "please",
        "plz" to "please",
        "rn" to "right now",
        "tbh" to "to be honest",
        "ofc" to "of course",
        "irl" to "in real life",
        "asap" to "as soon as possible",
        "msg" to "message",
        "ikr" to "I know right",
        "fyi" to "for your information",
        "gtg" to "got to go",
        "ttyl" to "talk to you later",
        "bbl" to "be back later",
        "afaik" to "as far as I know",
        "smh" to "shaking my head",
        "wyd" to "what are you doing",
        "hbu" to "how about you",
    )

    // ── Emoji palette ───────────────────────────────────────────────────────────
    private val emojiRows = listOf(
        listOf("😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚","😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🤩","🥳","😏","😒","😞","😔","😟","😕","🙁","😣","😖","😫","😩","🥺","😢","😭","😤","😠","😡","🤬","😳","🥵","🥶","😱","😨","😰","😥","😓","🤗","🤔","🤭","🤫","🤥","😶","😐","😑","😬","🙄","😯","😦","😧","😮","😲","🥱","😴","🤤","😪","😵","🤐","🥴","🤢","🤮","🤧","😷","🤒","🤕","🤑","🤠","😈","👿","👹","👺","🤡","💩","👻","💀","☠️","👽","👾","🤖","🎃","😺","😸","😹","😻","😼","😽","🙀","😿","😾"),
        listOf("👋","🤚","🖐","✋","🖖","👌","🤌","🤏","✌️","🤞","🤟","🤘","🤙","👈","👉","👆","👇","☝️","👍","👎","✊","👊","🤛","🤜","👏","🙌","👐","🤲","🙏","✍️","💪","🦾","🦿","🦵","🦶","👂","🦻","👃","🧠","🫀","🫁","🦷","🦴","👀","👁","👅","👄","🫦","👶","🧒","👦","👧","🧑","👱","👨","🧔","👩","🧓","👴","👵","🙋","🙇","🧍","🧎","👭","👫","👬","💏","💑","👨‍👩‍👦","👨‍👩‍👧","👨‍👩‍👧‍👦","👨‍👩‍👦‍👦","👨‍👩‍👧‍👧","👨‍👦","👨‍👦‍👦","👨‍👧","👨‍👧‍👦","👨‍👧‍👧","👩‍👦","👩‍👦‍👦","👩‍👧","👩‍👧‍👦","👩‍👧‍👧"),
        listOf("❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","☮️","✝️","☪️","🕉","☸️","✡️","🔯","🕎","☯️","☦️","🛐","⛎","♈","♉","♊","♋","♌","♍","♎","♏","♐","♑","♒","♓","🆔","⚛️","🉑","☢️","☣️","📴","📳","🈶","🈚","🈸","🈺","🈷️","✴️","🆚","💮","🉐","㊙️","㊗️","🈴","🈵","🈹","🈲","🅰️","🅱️","🆎","🆑","🅾️","🆘","❌","⭕","🛑","⛔","📛","🚫","💯","💢","♨️","🚷","🚯","🚳","🚱","🔞","📵","🚭","❗","❕","❓","❔","‼️","⁉️","🔅","🔆","〽️","⚠️","🚸","🔱","⚜️","🔰","♻️","✅","🈯","💹","❇️","✳️","❎","🌐","💠","Ⓜ️","🌀","💤","🏧","🚾","♿","🅿️","🈳","🛂","🛃","🛄","🛅","🛗","🚹","🚺","🚼","🚻","🚮","🎦","📶","🈁","🔣","ℹ️","🔤","🔡","🔠","🔟","🔢","⏺","⏮","⏭","⏩","⏪","⏫","⏬","🎵","🎶","➕","➖","✖️","➗","💲","💱","™️","©️","®️","👁","‍🗨","🔚","🔙","🔛","🔝","🔜","〰️","➰","➿","✔️","☑️","🔘","🔴","🟠","🟡","🟢","🔵","🟣","⚫","⚪","🟤","🔺","🔻","🔸","🔹","🔶","🔷","🔳","🔲","▪️","▫️","◾","◽","◼️","◻️","🟥","🟧","🟨","🟩","🟦","🟪","⬛","⬜","🟫"),
        listOf("⚽","🏀","🏈","⚾","🎾","🏐","🏉","🎱","🏓","🏸","🥅","🏒","🏑","🥍","🏏","⛳","🥌","🎿","⛷","🏂","🏋️","🤼","🤸","⛹️","🤺","🤾","🏌️","🏇","🧘","🏄","🏊","🤽","🚣","🧗","🚴","🚵","🎽","🏆","🥇","🥈","🥉","🏅","🎖","🏵","🎗","🎫","🎟","🎪","🎭","🩰","🎨","🎬","🎤","🎧","🎼","🎹","🥁","🎷","🎺","🎸","🪕","🎻","🪗","🎲","♟","🎯","🎳","🎮","🎰","🧩"),
        listOf("🚗","🚕","🚙","🚌","🚎","🏎","🚓","🚑","🚒","🚐","🛻","🚚","🚛","🚜","🛵","🏍","🛺","🚲","🛴","🛹","🛼","🚁","🛩","✈️","🛫","🛬","🪂","💺","🚀","🛸","🚉","🚞","🚝","🚄","🚅","🚈","🚂","🚆","🚇","🚊","🚝","🚋","🚌","🚍","🚎","🚐","🚑","🚒","🚓","🚔","🚕","🚖","🚗","🚘","🚙","🚚","🚛","🚜","🏎","🏍","🛵","🛺","🚲","🛴","🛹","🛼","🚁","🛩","✈️","🛫","🛬","🪂","💺","🚀","🛸","🚉","🚞","🚝","🚄","🚅","🚈","🚂","🚆","🚇","🚊"),
        listOf("🍏","🍎","🍐","🍊","🍋","🍌","🍉","🍇","🍓","🫐","🍈","🍒","🍑","🥭","🍍","🥥","🥝","🍅","🍆","🥑","🥦","🥬","🥒","🌶","🫑","🌽","🥕","🧄","🧅","🥔","🍠","🥐","🥯","🍞","🥖","🥨","🧀","🥚","🍳","🧈","🥞","🧇","🥓","🥩","🍗","🍖","🍔","🍟","🍕","🫓","🥪","🥙","🌮","🌯","🫔","🥗","🥘","🫕","🍝","🍜","🍲","🍛","🍣","🍱","🥟","🍤","🍙","🍚","🍘","🍥","🥠","🥮","🍢","🍡","🍧","🍨","🍦","🥧","🧁","🍰","🎂","🍮","🍭","🍬","🍫","🍿","🍩","🍪","🌰","🥜","🍯","🥛","🍼","☕","🫖","🍵","🍶","🍾","🍷","🍸","🍹","🍺","🍻","🥂","🥃","🥤","🧋","🧃","🧉","🧊","🥢","🍽","🍴","🥄","🔪","🏺"),
        listOf("⌚","📱","💻","⌨️","🖥","🖨","🖱","🖲","🕹","🗜","💽","💾","💿","📀","📼","📷","📸","📹","🎥","📽","📞","☎️","📟","📠","📺","📻","🎙","🎚","🎛","⏱","⏲","⏰","🕰","⌛","⏳","📡","🔋","🔌","💡","🔦","🕯","🧯","🛢","💸","💵","💴","💶","💷","🪙","💰","💳","💎","⚖️","🪜","🧰","🪛","🔧","🔨","⚒","🛠","⛏","🔩","⚙️","🪚","🪓","🔫","🏹","🛡","🔮","🪄","💊","💉","🩹","🩺","🚪","🛗","🪞","🪟","🛏","🛋","🪑","🚽","🪒","🧴","🧷","🧹","🧺","🧻","🪣","🧼","🪥","🧽","🧯","🛒","🚬","⚰️","🪦","⚱️","🗿","🔧","🔨","⚒","🛠","⛏","🔩","⚙️","🪚","🔮","💈","🔬","🔭","📡","💉","💊","🩹","🩺","🚪","🛗","🪞","🪟","🛏","🛋","🪑","🚽","🪒","🧴","🧷","🧹","🧺","🧻","🪣","🧼","🪥","🧽","🧯","🛒","🚬","⚰️","🪦","⚱️","🗿"),
        listOf("🏠","🏡","🏢","🏣","🏤","🏥","🏦","🏨","🏩","🏪","🏫","🏬","🏭","🏯","🏰","💒","🗼","🗽","⛪","🕌","🛕","🕍","⛩","🕋","🌃","🌄","🌅","🌆","🌇","🌉","♨️","🎠","🎡","🎢","💈","🎪","🚂","🚃","🚄","🚅","🚆","🚇","🚈","🚉","🚊","🚝","🚞","🚋","🚌","🚍","🚎","🚐","🚑","🚒","🚓","🚔","🚕","🚖","🚗","🚘","🚙","🚚","🚛","🚜","🏎","🏍","🛵","🦽","🦼","🛺","🚲","🛴","🛹","🛼","🚁","🛩","✈️","🛫","🛬","🪂","💺","🚀","🛸","🚉","🚞","🚝","🚄","🚅","🚈","🚂","🚆","🚇","🚊","🚝","🚋","🚌","🚍","🚎","🚐","🚑","🚒","🚓","🚔","🚕","🚖","🚗","🚘","🚙","🚚","🚛","🚜","🏎","🏍","🛵","🦽","🦼","🛺","🚲","🛴","🛹","🛼","🚁","🛩","✈️","🛫","🛬","🪂","💺","🚀","🛸","🚉","🚞","🚝","🚄","🚅","🚈","🚂","🚆","🚇","🚊")
    )

    // ── Transliteration map (Latin → Devanagari) ───────────────────────────────
    private val translitMap = mapOf(
        "aa" to "आ", "ee" to "ई", "oo" to "ऊ", "ai" to "ऐ", "au" to "औ",
        "ksh" to "क्ष", "sh" to "श", "Sh" to "ष", "ny" to "ञ", "ng" to "ङ",
        "ch" to "च", "chh" to "छ", "jh" to "झ", "th" to "थ", "dh" to "ध",
        "bh" to "भ", "ph" to "फ", "gh" to "घ", "kh" to "ख", "aa" to "आ",
        "a" to "अ", "i" to "इ", "e" to "ए", "u" to "उ", "o" to "ओ",
        "k" to "क", "g" to "ग", "c" to "क", "j" to "ज", "t" to "त",
        "d" to "द", "n" to "न", "p" to "प", "b" to "ब", "m" to "म",
        "y" to "य", "r" to "र", "l" to "ल", "v" to "व", "w" to "व",
        "z" to "ज़", "f" to "फ़", "q" to "क़", "x" to "क्ष",
        "h" to "ह", "s" to "स", "1" to "१","2" to "२","3" to "३","4" to "४",
        "5" to "५","6" to "६","7" to "७","8" to "८","9" to "९","0" to "०",
    )

    // ── Hindi consonant rows for the Inscript keyboard ─────────────────────────
    private val hindiRow0 = listOf("1","2","3","4","5","6","7","8","9","0")
    private val hindiRow1 = listOf("अ","आ","इ","ई","उ","ऊ","ए","ऐ","ओ","औ")
    private val hindiRow2 = listOf("क","ख","ग","घ","ङ","च","छ","ज","झ","ञ")
    private val hindiRow3 = listOf("ट","ठ","ड","ढ","ण","त","थ","द","ध","न")
    private val hindiRow4 = listOf("प","फ","ब","भ","म","य","र","ल","व","श")
    private val hindiRow5 = listOf("श्र","क्ष","त्","ड़","।","⎵","⌫","⏎")

    // ── QWERTY definitions ────────────────────────────────────────────────────
    private val qwertyRows = listOf(
        listOf("Q","W","E","R","T","Y","U","I","O","P"),
        listOf("A","S","D","F","G","H","J","K","L"),
        listOf("⇧","Z","X","C","V","B","N","M","⌫"),
        listOf("?123",",","⎵",".","⏎"),
    )
    private val qwertyShiftedRows = listOf(
        listOf("1","2","3","4","5","6","7","8","9","0"),
        listOf("!","@","#","$","%","^","&","*","(",")"),
        listOf("⇧","Z","X","C","V","B","N","M","⌫"),
        listOf("?123",",","⎵",".","⏎"),
    )
    private val symbolRows = listOf(
        listOf("1","2","3","4","5","6","7","8","9","0"),
        listOf("-","/",":",";","(",")","₹","&","@"),
        listOf("#+","=","?",",",".","⎵","!","⌫"),
        listOf("ABC",",","⎵",".","⏎"),
    )

    // ── View references ────────────────────────────────────────────────────────
    private var rootContainer: ViewGroup? = null

    // ══════════════════════════════════════════════════════════════════════════
    // Lifecycle
    // ══════════════════════════════════════════════════════════════════════════

    override fun onCreateInputView(): View {
        rootContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#1A1A1A"))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }

        // Toolbar
        val toolbar = buildToolbar()
        rootContainer?.addView(toolbar)

        // Content frame for keyboard / emoji / Hindi / snippets
        val contentFrame = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }
        rootContainer?.addView(contentFrame)

        // Render text keyboard by default
        showTextKeyboard(contentFrame)

        return rootContainer!!
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        lastBuffer = StringBuilder()

        val isPassword = (info?.inputType ?: 0).let {
            (it and InputType.TYPE_TEXT_VARIATION_PASSWORD) != 0 ||
            (it and InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD) != 0
        }

        if ((info?.inputType ?: 0) and InputType.TYPE_CLASS_NUMBER == InputType.TYPE_CLASS_NUMBER) {
            currentLang = Locale.ENGLISH
        }
    }

    override fun onDestroy() {
        speechRecognizer?.destroy()
        speechRecognizer = null
        super.onDestroy()
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Toolbar
    // ══════════════════════════════════════════════════════════════════════════

    private fun buildToolbar(): LinearLayout {
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(6, 6, 6, 6)
            setBackgroundColor(Color.parseColor("#121212"))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(40)
            )
        }

        fun toolbarBtn(text: String, onClick: () -> Unit): Button {
            return Button(this).apply {
                this.text = text
                textSize = 18f
                minWidth = 0
                minHeight = 0
                setPadding(6, 2, 6, 2)
                layoutParams = LinearLayout.LayoutParams(dp(36), dp(36))
                background = resources.getDrawable(
                    android.R.attr.selectableItemBackgroundBorderless, theme)
            }.also { it.setOnClickListener { onClick() } }
        }

        bar.addView(toolbarBtn("😀") { switchMode(Mode.EMOJI) })
        bar.addView(toolbarBtn("≡") { switchMode(Mode.SNIPPETS) })

        // Language toggle button — shows current language
        val langBtnText = if (currentLang.language == "hi") "अ" else "A"
        bar.addView(Button(this).apply {
            text = langBtnText
            textSize = 16f
            minWidth = 0
            minHeight = 0
            setPadding(6, 2, 6, 2)
            layoutParams = LinearLayout.LayoutParams(dp(36), dp(36))
            background = resources.getDrawable(android.R.attr.selectableItemBackgroundBorderless, theme)
            setTextColor(Color.parseColor("#D7FB52"))
            setTypeface(null, android.graphics.Typeface.BOLD)
            setOnClickListener { switchLanguage() }
        })

        // Spacer
        bar.addView(View(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, 0, 1f)
        })

        // Mic button
        bar.addView(Button(this).apply {
            id = View.generateViewId()
            text = "🎤"
            textSize = 20f
            minWidth = 0
            minHeight = 0
            setPadding(4, 2, 4, 2)
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40))
            background = resources.getDrawable(R.drawable.mic_button_bg, theme)
            setOnClickListener { toggleListening() }
        })

        // Switch keyboard button
        bar.addView(toolbarBtn("⌨") {
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showInputMethodPicker()
        })

        return bar
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Mode switching
    // ══════════════════════════════════════════════════════════════════════════

    private fun findContentFrame(): FrameLayout {
        return (rootContainer?.getChildAt(1) as? FrameLayout)
            ?: FrameLayout(this).also { rootContainer?.addView(it) }
    }

    private fun switchMode(mode: Mode) {
        currentMode = mode
        val frame = findContentFrame()
        when (mode) {
            Mode.TEXT -> showTextKeyboard(frame)
            Mode.EMOJI -> showEmojiKeyboard(frame)
            Mode.HINDI -> showHindiKeyboard(frame)
            Mode.SNIPPETS -> showSnippetKeyboard(frame)
        }
    }

    private fun switchLanguage() {
        currentLang = when (currentLang.language) {
            "en" -> Locale("hi")
            "hi" -> Locale.ENGLISH
            else -> Locale.ENGLISH
        }
        // Rebuild toolbar to update language indicator
        rootContainer?.removeViewAt(0)
        rootContainer?.addView(buildToolbar(), 0)
        if (currentMode == Mode.TEXT) {
            switchMode(Mode.TEXT)
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Text Keyboard (QWERTY)
    // ══════════════════════════════════════════════════════════════════════════

    private fun showTextKeyboard(frame: FrameLayout) {
        frame.removeAllViews()
        val rows = if (isShifted) qwertyShiftedRows else qwertyRows
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(2), dp(2), dp(2), dp(2))
        }
        for (rowKeys in rows) {
            container.addView(buildKeyRow(rowKeys))
        }
        frame.addView(container)
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Emoji Keyboard
    // ══════════════════════════════════════════════════════════════════════════

    private fun showEmojiKeyboard(frame: FrameLayout) {
        frame.removeAllViews()
        val scroll = android.widget.ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        scroll.addView(container)
        frame.addView(scroll)

        for (rowEmojis in emojiRows) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER
            }
            for (emoji in rowEmojis) {
                row.addView(Button(this).apply {
                    text = emoji
                    textSize = 28f
                    // CRITICAL: Do NOT set a custom typeface.
                    // Android's system "sans-serif" font family on API 19+
                    // includes Noto Color Emoji glyphs. Using Button with
                    // default typeface lets the system render color emoji.
                    // ImageButton would force a bitmap path → rectangular boxes.
                    minWidth = 0
                    minHeight = 0
                    setPadding(dp(2), dp(0), dp(2), dp(0))
                    layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply {
                        rightMargin = dp(1)
                        leftMargin = dp(1)
                        topMargin = dp(1)
                        bottomMargin = dp(1)
                    }
                    background = resources.getDrawable(
                        android.R.attr.selectableItemBackgroundBorderless, theme)
                }.also { btn ->
                    btn.setOnClickListener { commitText(emoji) }
                })
            }
            container.addView(row)
        }

        // Back to text
        container.addView(Button(this).apply {
            text = "⌨ ABC"
            textSize = 14f
            setPadding(dp(12), dp(6), dp(12), dp(6))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(8) }
            background = resources.getDrawable(android.R.attr.selectableItemBackground, theme)
            setTextColor(Color.parseColor("#D7FB52"))
            setOnClickListener { switchMode(Mode.TEXT) }
        })
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Hindi Keyboard
    // ══════════════════════════════════════════════════════════════════════════

    private fun showHindiKeyboard(frame: FrameLayout) {
        frame.removeAllViews()
        val scroll = android.widget.ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        scroll.addView(container)
        frame.addView(scroll)

        // Hint
        container.addView(TextView(this).apply {
            text = "Type in Devanagari (Inscript layout)"
            setTextColor(Color.parseColor("#888888"))
            textSize = 12f
            setPadding(dp(4), dp(2), dp(4), dp(6))
        })

        // Numbers
        container.addView(buildHindiRow(hindiRow0, isSpecial = false))
        // Vowels
        container.addView(buildHindiRow(hindiRow1, isSpecial = false))
        // Consonants
        container.addView(buildHindiRow(hindiRow2, isSpecial = false))
        container.addView(buildHindiRow(hindiRow3, isSpecial = false))
        container.addView(buildHindiRow(hindiRow4, isSpecial = false))
        // Specials + space + enter
        val lastRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        for (key in hindiRow5) {
            when (key) {
                "⎵" -> lastRow.addView(makeHindiKey(key, " ", weight = 5f))
                "⌫" -> lastRow.addView(makeHindiKey(key, "", weight = 1.5f, isSpecial = true).also {
                    it.setOnClickListener { currentInputConnection?.deleteSurroundingText(1, 0) }
                })
                "⏎" -> lastRow.addView(makeHindiKey(key, "\n", weight = 1.8f, isSpecial = true).also {
                    it.setOnClickListener { currentInputConnection?.commitText("\n", 1) }
                })
                else -> lastRow.addView(makeHindiKey(key, key, weight = 1f, isSpecial = true))
            }
        }
        container.addView(lastRow)

        // Back button
        container.addView(Button(this).apply {
            text = "⌨ English"
            textSize = 14f
            setPadding(dp(12), dp(6), dp(12), dp(6))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(8) }
            background = resources.getDrawable(android.R.attr.selectableItemBackground, theme)
            setTextColor(Color.parseColor("#D7FB52"))
            setOnClickListener { switchMode(Mode.TEXT) }
        })
    }

    private fun buildHindiRow(keys: List<String>, isSpecial: Boolean): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        for (key in keys) {
            row.addView(makeHindiKey(key, key, weight = 1f, isSpecial = isSpecial))
        }
        return row
    }

    private fun makeHindiKey(label: String, output: String, weight: Float = 1f, isSpecial: Boolean = false): Button {
        return Button(this).apply {
            text = label
            textSize = if (label.length > 1) 13f else 20f
            minWidth = 0
            minHeight = 0
            setPadding(dp(2), dp(4), dp(2), dp(4))
            layoutParams = LinearLayout.LayoutParams(0, dp(44), weight).apply {
                rightMargin = dp(2)
                leftMargin = dp(2)
                topMargin = dp(1)
                bottomMargin = dp(1)
            }
            setBackgroundColor(Color.parseColor("#2A2A2A"))
            setTextColor(Color.WHITE)
            // CRITICAL: No custom typeface — Devanagari requires the system
            // Noto Sans Devanagari font which ships with Android.
        }.also {
            it.setOnClickListener { commitText(output) }
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Snippet Keyboard
    // ══════════════════════════════════════════════════════════════════════════

    private fun showSnippetKeyboard(frame: FrameLayout) {
        frame.removeAllViews()
        val scroll = android.widget.ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        scroll.addView(container)
        frame.addView(scroll)

        for ((shortcut, expansion) in snippets) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(4), dp(4), dp(4), dp(4))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                )
            }

            // Shortcut key (tappable to insert)
            row.addView(Button(this).apply {
                text = shortcut
                textSize = 16f
                setTypeface(null, android.graphics.Typeface.BOLD)
                minWidth = 0
                minHeight = 0
                setPadding(dp(10), dp(8), dp(10), dp(8))
                layoutParams = LinearLayout.LayoutParams(dp(100), dp(44)).apply {
                    rightMargin = dp(4)
                }
                background = resources.getDrawable(
                    android.R.attr.selectableItemBackground, theme)
                setTextColor(Color.parseColor("#D7FB52"))
                setOnClickListener { commitSnippet(shortcut, expansion) }
            })

            // Arrow
            row.addView(TextView(this).apply {
                text = "→"
                textSize = 20f
                setTextColor(Color.parseColor("#888888"))
                layoutParams = LinearLayout.LayoutParams(dp(36), dp(44)).apply {
                    gravity = Gravity.CENTER
                }
            })

            // Expansion text
            row.addView(Button(this).apply {
                text = expansion
                textSize = 14f
                minWidth = 0
                minHeight = 0
                setPadding(dp(10), dp(8), dp(10), dp(8))
                layoutParams = LinearLayout.LayoutParams(0, dp(44), 1f).apply {
                    leftMargin = dp(4)
                }
                background = resources.getDrawable(
                    android.R.attr.selectableItemBackground, theme)
                setTextColor(Color.WHITE)
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                gravity = Gravity.START
                setOnClickListener { commitSnippet(shortcut, expansion) }
            })

            container.addView(row)
        }

        // Back button
        container.addView(Button(this).apply {
            text = "⌨ Keyboard"
            textSize = 14f
            setPadding(dp(12), dp(6), dp(12), dp(6))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(10) }
            background = resources.getDrawable(android.R.attr.selectableItemBackground, theme)
            setTextColor(Color.parseColor("#D7FB52"))
            setOnClickListener { switchMode(Mode.TEXT) }
        })
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Key row builder
    // ══════════════════════════════════════════════════════════════════════════

    private fun buildKeyRow(keys: List<String>): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }

        for (key in keys) {
            when (key) {
                "⇧" -> {
                    val btn = Button(this).apply {
                        text = "⇧"
                        textSize = 20f
                        setTypeface(null, android.graphics.Typeface.BOLD)
                        minWidth = 0
                        minHeight = 0
                        setPadding(dp(4), dp(4), dp(4), dp(4))
                        layoutParams = LinearLayout.LayoutParams(dp(44), dp(44)).apply {
                            rightMargin = dp(2)
                            leftMargin = dp(2)
                        }
                        background = resources.getDrawable(
                            android.R.attr.selectableItemBackground, theme)
                        setTextColor(if (isShifted) Color.parseColor("#D7FB52") else Color.WHITE)
                        isSelected = isShifted
                    }
                    btn.setOnClickListener {
                        isShifted = !isShifted
                        showTextKeyboard(findContentFrame())
                    }
                    row.addView(btn)
                }
                "⎵" -> {
                    row.addView(Button(this).apply {
                        text = "space"
                        textSize = 13f
                        minWidth = 0
                        minHeight = 0
                        layoutParams = LinearLayout.LayoutParams(0, dp(44), 5f).apply {
                            rightMargin = dp(2)
                            leftMargin = dp(2)
                        }
                        setBackgroundColor(Color.parseColor("#333333"))
                        setTextColor(Color.WHITE)
                    }.also { it.setOnClickListener { onKeyAction(" ", it) } })
                }
                "⌫" -> {
                    row.addView(Button(this).apply {
                        text = "⌫"
                        textSize = 20f
                        minWidth = 0
                        minHeight = 0
                        layoutParams = LinearLayout.LayoutParams(0, dp(44), 1.5f).apply {
                            rightMargin = dp(2)
                            leftMargin = dp(2)
                        }
                        setBackgroundColor(Color.parseColor("#FF4444"))
                        setTextColor(Color.WHITE)
                    }.also { it.setOnClickListener {
                        currentInputConnection?.deleteSurroundingText(1, 0)
                        trimBuffer(1)
                    } })
                }
                "⏎" -> {
                    row.addView(Button(this).apply {
                        text = "Enter"
                        textSize = 12f
                        minWidth = 0
                        minHeight = 0
                        layoutParams = LinearLayout.LayoutParams(0, dp(44), 1.8f).apply {
                            rightMargin = dp(2)
                            leftMargin = dp(2)
                        }
                        setBackgroundColor(Color.parseColor("#D7FB52"))
                        setTextColor(Color.BLACK)
                        setTypeface(null, android.graphics.Typeface.BOLD)
                    }.also { it.setOnClickListener {
                        currentInputConnection?.commitText("\n", 1)
                        lastBuffer = StringBuilder()
                    } })
                }
                else -> {
                    row.addView(Button(this).apply {
                        text = key
                        textSize = 18f
                        minWidth = 0
                        minHeight = 0
                        setPadding(dp(6), dp(4), dp(6), dp(4))
                        layoutParams = LinearLayout.LayoutParams(0, dp(44), 1f).apply {
                            rightMargin = dp(2)
                            leftMargin = dp(2)
                        }
                        setBackgroundColor(Color.parseColor("#333333"))
                        setTextColor(Color.WHITE)
                    }.also { it.setOnClickListener { onKeyAction(key, it) } })
                }
            }
        }
        return row
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Key action handler
    // ══════════════════════════════════════════════════════════════════════════

    private fun onKeyAction(key: String, _view: View?) {
        val ic = currentInputConnection ?: return

        when (key) {
            " " -> {
                // Check snippet trigger
                val word = lastBuffer.toString().trim()
                val snippetExpansion = snippets[word.lowercase(Locale.getDefault())]
                if (snippetExpansion != null) {
                    // Delete the shortcut + trailing space, insert expansion
                    ic.deleteSurroundingText(word.length + 1, 0)
                    ic.commitText(snippetExpansion + " ", 1)
                    lastBuffer = StringBuilder()
                    return
                }
                // Live transliteration if in Hindi mode
                if (currentLang.language == "hi" && word.isNotEmpty()) {
                    val translit = tryTransliterate(word)
                    if (translit != word) {
                        ic.deleteSurroundingText(word.length, 0)
                        ic.commitText(translit + " ", 1)
                        lastBuffer = StringBuilder()
                        return
                    }
                }
                // Regular space
                ic.commitText(" ", 1)
                lastBuffer = StringBuilder()
            }
            else -> {
                lastBuffer.append(key)
                ic.commitText(key, 1)
            }
        }
    }

    private fun commitText(text: String) {
        val ic = currentInputConnection ?: return
        ic.commitText(text, 1)
        lastBuffer.append(text)
    }

    private fun trimBuffer(count: Int) {
        if (lastBuffer.isNotEmpty()) {
            lastBuffer.delete(maxOf(0, lastBuffer.length - count), lastBuffer.length)
        }
    }

    private fun commitSnippet(shortcut: String, expansion: String) {
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(shortcut.length + 1, 0)
        ic.commitText(expansion + " ", 1)
        lastBuffer = StringBuilder()
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Transliteration (Latin → Devanagari)
    // ══════════════════════════════════════════════════════════════════════════

    private fun tryTransliterate(word: String): String {
        if (currentLang.language != "hi") return word

        val lower = word.lowercase(Locale.getDefault())
        var result = ""
        var i = 0
        while (i < lower.length) {
            var matched = false
            for (len in kotlin.math.min(4, lower.length - i) downTo 1) {
                val chunk = lower.substring(i, i + len)
                val replacement = translitMap[chunk]
                if (replacement != null) {
                    result = result + replacement
                    i += len
                    matched = true
                    break
                }
            }
            if (!matched) {
                result += lower[i]
                i++
            }
        }
        return result.ifEmpty { word }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Voice Dictation
    // ══════════════════════════════════════════════════════════════════════════

    private fun toggleListening() {
        if (isListening) {
            stopListening()
        } else {
            startListening()
        }
    }

    private fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Toast.makeText(this, "Speech recognition not available", Toast.LENGTH_SHORT).show()
            return
        }

        if (speechRecognizer == null) {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, currentLang.toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }

        speechRecognizer?.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: android.os.Bundle?) {
                Toast.makeText(this@KVIEInputMethodService, "Listening...", Toast.LENGTH_SHORT).show()
                isListening = true
            }

            override fun onResults(results: android.os.Bundle?) {
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val transcript = matches?.firstOrNull().orEmpty()
                handleFinalTranscript(transcript)
                stopListening()
            }

            override fun onError(error: Int) {
                Toast.makeText(this@KVIEInputMethodService, "Try again", Toast.LENGTH_SHORT).show()
                stopListening()
            }

            override fun onPartialResults(partialResults: android.os.Bundle?) {
                val partial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                if (!partial.isNullOrEmpty() && partial[0].isNotBlank()) {
                    Toast.makeText(this@KVIEInputMethodService, partial[0], Toast.LENGTH_SHORT).show()
                }
            }

            override fun onBeginningOfSpeech() {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
            override fun onRmsChanged(rmsdB: Float) {}
        })

        speechRecognizer?.startListening(intent)
    }

    private fun stopListening() {
        speechRecognizer?.stopListening()
        isListening = false
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Transcript handling (auto-edit pipeline)
    // ══════════════════════════════════════════════════════════════════════════

    private fun handleFinalTranscript(rawTranscript: String) {
        if (rawTranscript.isBlank()) {
            Toast.makeText(this, "Didn't catch that — try again", Toast.LENGTH_SHORT).show()
            return
        }

        val stage1 = stripFillerWords(rawTranscript)
        commitTextToField(stage1)

        scope.launch {
            val refined = AutoEditClient.refine(stage1)
            if (refined != null && refined != stage1) {
                replaceLastCommittedText(stage1, refined)
            }
        }
    }

    private fun stripFillerWords(text: String): String {
        val fillers = listOf("um", "uh", "like", "you know")
        var result = text
        for (f in fillers) {
            result = result.replace(Regex("\\b$f\\b", RegexOption.IGNORE_CASE), "")
        }
        return result.replace(Regex("\\s+"), " ").trim()
    }

    private fun commitTextToField(text: String) {
        currentInputConnection?.commitText(text, 1)
    }

    private fun replaceLastCommittedText(old: String, new: String) {
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(old.length, 0)
        ic.commitText(new, 1)
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Utilities
    // ══════════════════════════════════════════════════════════════════════════

    private fun dp(px: Int): Int = (px * resources.displayMetrics.density).toInt()
}

// ── Mode enum ─────────────────────────────────────────────────────────────────
enum class Mode { TEXT, EMOJI, HINDI, SNIPPETS }
