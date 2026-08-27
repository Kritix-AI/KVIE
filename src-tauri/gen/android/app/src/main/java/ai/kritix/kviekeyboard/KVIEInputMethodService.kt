package ai.kritix.kviekeyboard

import ai.kritix.desktop.R
import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.GridLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * KVIE Next-Gen AI Voice & QWERTY Keyboard Input Method Service.
 * Flagship Features:
 * 1. Full QWERTY with Dedicated Number Row & Long-Press Alt-Symbols (q->1, w->2, a->@, etc.)
 * 2. Real-Time Autocorrect & Next-Word 3-Candidate Suggestion Bar
 * 3. Native Multi-Item Clipboard History Drawer
 * 4. Full Emoji Keyboard Drawer (Smileys, Gestures, Hearts, Vibes)
 * 5. Instant 1-Tap AI Voice Dictation & SmolLM2-360M Polish
 * 6. Dual Tactile Haptic & Acoustic Mechanical Key Click Feedback
 */
class KVIEInputMethodService : InputMethodService() {

    private var speechRecognizer: SpeechRecognizer? = null
    private var whisperEngine: WhisperEngine? = null
    private var parakeetEngine: ParakeetEngine? = null

    private var isListening = false
    private var isShifted = false
    private var isCapsLock = false
    private var isSymbolsMode = false
    private var isSymbolsSecondaryPage = false
    private var isNumberRowVisible = true

    // Top Voice & Suggestion Toolbar
    private lateinit var voiceToolbar: LinearLayout
    private lateinit var statusText: TextView
    private lateinit var micButton: ImageButton
    private lateinit var polishButton: TextView
    private lateinit var suggestionBar: LinearLayout
    private lateinit var suggestion1: TextView
    private lateinit var suggestion2: TextView
    private lateinit var suggestion3: TextView
    private lateinit var btnClipboard: TextView
    private lateinit var btnNumberRowToggle: TextView

    // Clipboard Drawer
    private lateinit var clipboardDrawer: LinearLayout
    private lateinit var clipboardItemsContainer: LinearLayout
    private lateinit var btnClearClipboard: TextView
    private lateinit var clipboardManager: ClipboardManager
    private val recentClips = mutableListOf<String>()

    // QWERTY Container
    private lateinit var qwertyContainer: LinearLayout
    private lateinit var rowNumbers: LinearLayout
    private lateinit var row1: LinearLayout
    private lateinit var row2: LinearLayout
    private lateinit var row3Letters: LinearLayout
    private lateinit var keyShift: TextView
    private lateinit var keySymbols: TextView
    private lateinit var keyEmoji: TextView
    private lateinit var keyBackspace: TextView
    private lateinit var keySpace: TextView
    private lateinit var keyDot: TextView
    private lateinit var keyComma: TextView
    private lateinit var keyEnter: TextView

    // Emoji Drawer
    private lateinit var emojiDrawer: LinearLayout
    private lateinit var emojiGrid: GridLayout
    private lateinit var tabSmiley: TextView
    private lateinit var tabGestures: TextView
    private lateinit var tabHearts: TextView
    private lateinit var tabFire: TextView
    private lateinit var btnReturnToAbc: TextView
    private lateinit var btnEmojiBackspace: TextView

    private val numberKeys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    private val alphabetKeysRow1 = listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p")
    private val alphabetKeysRow2 = listOf("a", "s", "d", "f", "g", "h", "j", "k", "l")
    private val alphabetKeysRow3 = listOf("z", "x", "c", "v", "b", "n", "m")

    private val symbolKeysRow1 = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    private val symbolKeysRow2 = listOf("@", "#", "$", "_", "&", "-", "+", "(", ")", "/")
    private val symbolKeysRow3 = listOf("*", "\"", "'", ":", ";", "!", "?")

    private val symbolPage2Row1 = listOf("~", "\\", "|", "<", ">", "{", "}", "[", "]", "%")
    private val symbolPage2Row2 = listOf("^", "=", "°", "•", "¥", "€", "£", "¢", "₱", "©")
    private val symbolPage2Row3 = listOf("®", "™", "✓", "§", "¶", "¿", "¡")

    private val altSymbolMap = mapOf(
        "q" to "1", "w" to "2", "e" to "3", "r" to "4", "t" to "5",
        "y" to "6", "u" to "7", "i" to "8", "o" to "9", "p" to "0",
        "a" to "@", "s" to "#", "d" to "$", "f" to "%", "g" to "&",
        "h" to "-", "j" to "+", "k" to "(", "l" to ")",
        "z" to "*", "x" to "\"", "c" to "'", "v" to ":", "b" to ";",
        "n" to "!", "m" to "?"
    )

    private val commonWords = listOf(
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "I",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
        "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
        "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
        "when", "make", "can", "like", "time", "no", "just", "him", "know", "take",
        "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
        "than", "then", "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
        "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
        "Kritix", "KVIE", "hello", "thanks", "please", "yes", "sure", "great", "awesome", "today",
        "tomorrow", "yesterday", "meeting", "call", "send", "message", "okay", "done", "fine", "cool",
        "bhai", "kya", "ha", "nahi", "accha", "theek", "kaise", "kaha", "chalo", "ab", "kab"
    )

    // Emoji Catalogs
    private val smileyEmojis = listOf(
        "😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚",
        "😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🤩","🥳","😏","😒","😞","😔","😟","😕","🙁","😣","😖",
        "😫","😩","🥺","😢","😭","😤","😠","😡","🤬","🤯","😳","🥵","🥶","😱","😨","😰","😥","😓","🤗","🤔",
        "🤭","🤫","🤥","😶","😐","😑","😬","🙄","😯","😦","😧","😮","😲","🥱","😴","🤤","😪","😵","🤐","🥴"
    )
    private val gestureEmojis = listOf(
        "👍","👎","👌","✌️","🤞","🤟","🤘","🤙","👈","👉","👆","🖕","👇","☝️","👋","🤚","🖐️","✋","🖖","👏",
        "🙌","👐","🤲","🤝","🙏","✍️","💅","🤳","💪","🦾","🦿","🦵","🦶","👂","🦻","👃","🧠","🫀","🫁","🦷"
    )
    private val heartEmojis = listOf(
        "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞","💓","💗","💖","💘","💝","💟","💌",
        "💋","💯","💢","💥","💫","💦","💨","🕳️","💣","💬","👁️‍🗨️","🗨️","🗯️","💭","💤"
    )
    private val fireEmojis = listOf(
        "🔥","✨","⭐","🌟","⚡","🎉","🎊","🚀","🏆","🥇","👑","💎","🎯","🔮","💡","📌","🔑","🔔","📢","🎵",
        "🎶","🎤","🎧","🎮","🕹️","🎲","🧩","🎨","🎬","📸","💻","📱","⌚","💰","💵","💸","🎁"
    )

    private val currentKeyButtons = mutableListOf<TextView>()
    private val scope = CoroutineScope(Dispatchers.Main)
    private var engineJob: Job? = null

    private val backspaceHandler = Handler(Looper.getMainLooper())
    private var isBackspaceHolding = false
    private var keyboardRootView: View? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        whisperEngine = WhisperEngine(this)
        parakeetEngine = ParakeetEngine(this)
        AutoEditClient.init(this)
        initClipboardManager()
    }

    override fun onCreateInputView(): View {
        val view = layoutInflater.inflate(R.layout.keyboard_view, null)
        keyboardRootView = view

        // Toolbar Views
        voiceToolbar = view.findViewById(R.id.voiceToolbar)
        statusText = view.findViewById(R.id.statusText)
        micButton = view.findViewById(R.id.micButton)
        polishButton = view.findViewById(R.id.polishButton)
        suggestionBar = view.findViewById(R.id.suggestionBar)
        suggestion1 = view.findViewById(R.id.suggestion1)
        suggestion2 = view.findViewById(R.id.suggestion2)
        suggestion3 = view.findViewById(R.id.suggestion3)
        btnClipboard = view.findViewById(R.id.btnClipboard)
        btnNumberRowToggle = view.findViewById(R.id.btnNumberRowToggle)

        // Clipboard Drawer Views
        clipboardDrawer = view.findViewById(R.id.clipboardDrawer)
        clipboardItemsContainer = view.findViewById(R.id.clipboardItemsContainer)
        btnClearClipboard = view.findViewById(R.id.btnClearClipboard)

        // QWERTY Views
        qwertyContainer = view.findViewById(R.id.qwertyContainer)
        rowNumbers = view.findViewById(R.id.rowNumbers)
        row1 = view.findViewById(R.id.row1)
        row2 = view.findViewById(R.id.row2)
        row3Letters = view.findViewById(R.id.row3Letters)
        keyShift = view.findViewById(R.id.keyShift)
        keySymbols = view.findViewById(R.id.keySymbols)
        keyEmoji = view.findViewById(R.id.keyEmoji)
        keyBackspace = view.findViewById(R.id.keyBackspace)
        keySpace = view.findViewById(R.id.keySpace)
        keyDot = view.findViewById(R.id.keyDot)
        keyComma = view.findViewById(R.id.keyComma)
        keyEnter = view.findViewById(R.id.keyEnter)

        // Emoji Drawer Views
        emojiDrawer = view.findViewById(R.id.emojiDrawer)
        emojiGrid = view.findViewById(R.id.emojiGrid)
        tabSmiley = view.findViewById(R.id.tabSmiley)
        tabGestures = view.findViewById(R.id.tabGestures)
        tabHearts = view.findViewById(R.id.tabHearts)
        tabFire = view.findViewById(R.id.tabFire)
        btnReturnToAbc = view.findViewById(R.id.btnReturnToAbc)
        btnEmojiBackspace = view.findViewById(R.id.btnEmojiBackspace)

        setupToolbarActions(view)
        setupKeypadActions()
        setupClipboardDrawer()
        setupEmojiDrawer()

        populateNumberRow()
        populateKeys()
        updateSuggestions()

        return view
    }

    private fun setupToolbarActions(view: View) {
        micButton.setOnClickListener {
            performKeyHaptic()
            if (isListening) stopListening() else startListening()
        }

        micButton.setOnLongClickListener {
            performKeyHaptic()
            launchFloatingMicOverlay()
            true
        }

        polishButton.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish()
        }

        btnClipboard.setOnClickListener {
            performKeyHaptic()
            toggleClipboardDrawer()
        }

        btnNumberRowToggle.setOnClickListener {
            performKeyHaptic()
            isNumberRowVisible = !isNumberRowVisible
            rowNumbers.visibility = if (isNumberRowVisible) View.VISIBLE else View.GONE
            btnNumberRowToggle.setTextColor(if (isNumberRowVisible) 0xFF00E5FF.toInt() else 0xFF8E8E9E.toInt())
        }

        view.findViewById<ImageButton>(R.id.switchKeyboardButton).setOnClickListener {
            performKeyHaptic()
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showInputMethodPicker()
        }

        suggestion1.setOnClickListener { applySuggestion(suggestion1.text.toString()) }
        suggestion2.setOnClickListener { applySuggestion(suggestion2.text.toString()) }
        suggestion3.setOnClickListener { applySuggestion(suggestion3.text.toString()) }
    }

    private fun setupKeypadActions() {
        keyShift.setOnClickListener {
            performKeyHaptic()
            toggleShift()
        }

        keyShift.setOnLongClickListener {
            performKeyHaptic()
            if (!isSymbolsMode) {
                isCapsLock = !isCapsLock
                isShifted = isCapsLock
                updateKeyLabels()
            }
            true
        }

        keySymbols.setOnClickListener {
            performKeyHaptic()
            toggleSymbolsMode()
        }

        keyEmoji.setOnClickListener {
            performKeyHaptic()
            showEmojiDrawer()
        }

        setupBackspaceKey()

        keySpace.setOnTouchListener { v, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                v.isPressed = true
                performKeyHaptic()
                currentInputConnection?.commitText(" ", 1)
                updateSuggestions()
                true
            } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                v.isPressed = false
                true
            } else false
        }

        keyDot.setOnTouchListener { v, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                v.isPressed = true
                performKeyHaptic()
                currentInputConnection?.commitText(if (isSymbolsMode) "/" else ".", 1)
                updateSuggestions()
                true
            } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                v.isPressed = false
                true
            } else false
        }

        keyComma.setOnTouchListener { v, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                v.isPressed = true
                performKeyHaptic()
                currentInputConnection?.commitText(if (isSymbolsMode) "=" else ",", 1)
                updateSuggestions()
                true
            } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                v.isPressed = false
                true
            } else false
        }

        keyEnter.setOnTouchListener { v, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                v.isPressed = true
                performKeyHaptic()
                handleEnterKey()
                true
            } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                v.isPressed = false
                true
            } else false
        }
    }

    private fun populateNumberRow() {
        rowNumbers.removeAllViews()
        for (num in numberKeys) {
            val btn = TextView(this).apply {
                val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                    marginStart = 2
                    marginEnd = 2
                }
                layoutParams = params
                gravity = Gravity.CENTER
                setBackgroundResource(R.drawable.key_bg)
                setTextColor(0xFFFFFFFF.toInt())
                textSize = 17f
                setTypeface(null, android.graphics.Typeface.BOLD)
                includeFontPadding = false
                text = num
                isClickable = true
                isFocusable = false

                setOnTouchListener { v, event ->
                    if (event.action == MotionEvent.ACTION_DOWN) {
                        v.isPressed = true
                        performKeyHaptic()
                        currentInputConnection?.commitText(num, 1)
                        updateSuggestions()
                        true
                    } else if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                        v.isPressed = false
                        true
                    } else false
                }
            }
            rowNumbers.addView(btn)
        }
    }

    private fun populateKeys() {
        row1.removeAllViews()
        row2.removeAllViews()
        row3Letters.removeAllViews()
        currentKeyButtons.clear()

        val r1 = when {
            isSymbolsMode && isSymbolsSecondaryPage -> symbolPage2Row1
            isSymbolsMode -> symbolKeysRow1
            else -> alphabetKeysRow1
        }
        val r2 = when {
            isSymbolsMode && isSymbolsSecondaryPage -> symbolPage2Row2
            isSymbolsMode -> symbolKeysRow2
            else -> alphabetKeysRow2
        }
        val r3 = when {
            isSymbolsMode && isSymbolsSecondaryPage -> symbolPage2Row3
            isSymbolsMode -> symbolKeysRow3
            else -> alphabetKeysRow3
        }

        for (char in r1) {
            val btn = createKeyButton(char)
            row1.addView(btn)
            currentKeyButtons.add(btn)
        }

        for (char in r2) {
            val btn = createKeyButton(char)
            row2.addView(btn)
            currentKeyButtons.add(btn)
        }

        for (char in r3) {
            val btn = createKeyButton(char)
            row3Letters.addView(btn)
            currentKeyButtons.add(btn)
        }

        updateKeyLabels()
    }

    private fun createKeyButton(label: String): TextView {
        val btn = TextView(this).apply {
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                marginStart = 2
                marginEnd = 2
            }
            layoutParams = params
            gravity = Gravity.CENTER
            setBackgroundResource(R.drawable.key_bg)
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 20f
            setTypeface(null, android.graphics.Typeface.BOLD)
            includeFontPadding = false
            minWidth = 0
            minHeight = 0
            setPadding(0, 0, 0, 0)
            isClickable = true
            isFocusable = false
            tag = label

            var isLongPressed = false
            val longPressHandler = Handler(Looper.getMainLooper())
            val longPressRunnable = Runnable {
                val alt = altSymbolMap[label.lowercase()]
                if (alt != null && !isSymbolsMode) {
                    isLongPressed = true
                    performKeyHaptic()
                    currentInputConnection?.commitText(alt, 1)
                    updateSuggestions()
                }
            }

            setOnTouchListener { v, event ->
                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        v.isPressed = true
                        isLongPressed = false
                        longPressHandler.postDelayed(longPressRunnable, 350)
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        v.isPressed = false
                        longPressHandler.removeCallbacks(longPressRunnable)
                        if (!isLongPressed) {
                            performKeyHaptic()
                            val textToCommit = text.toString()
                            currentInputConnection?.commitText(textToCommit, 1)

                            if (isShifted && !isCapsLock && !isSymbolsMode) {
                                isShifted = false
                                updateKeyLabels()
                            }
                            updateSuggestions()
                        }
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        v.isPressed = false
                        longPressHandler.removeCallbacks(longPressRunnable)
                        true
                    }
                    else -> false
                }
            }
        }
        return btn
    }

    private fun updateKeyLabels() {
        for (btn in currentKeyButtons) {
            val raw = btn.tag as? String ?: continue
            if (isSymbolsMode) {
                btn.text = raw
            } else {
                btn.text = if (isShifted || isCapsLock) raw.uppercase() else raw.lowercase()
            }
        }

        keyShift.text = when {
            isSymbolsMode && isSymbolsSecondaryPage -> "2/2"
            isSymbolsMode -> "1/2"
            isCapsLock -> "⇪"
            isShifted -> "⇧"
            else -> "⇧"
        }
        keyShift.isSelected = isShifted || isCapsLock || (isSymbolsMode && isSymbolsSecondaryPage)
        keySymbols.text = if (isSymbolsMode) "ABC" else "?123"
        keyDot.text = if (isSymbolsMode) "/" else "."
        keyComma.text = if (isSymbolsMode) "=" else ","
    }

    private fun toggleShift() {
        if (isSymbolsMode) {
            isSymbolsSecondaryPage = !isSymbolsSecondaryPage
            populateKeys()
            return
        }
        if (isCapsLock) {
            isCapsLock = false
            isShifted = false
        } else if (isShifted) {
            isCapsLock = true
        } else {
            isShifted = true
        }
        updateKeyLabels()
    }

    private fun toggleSymbolsMode() {
        isSymbolsMode = !isSymbolsMode
        isSymbolsSecondaryPage = false
        isShifted = false
        isCapsLock = false
        populateKeys()
    }

    // ───────────── INTERACTIVE AUTOCORRECT & SUGGESTIONS ─────────────
    private fun updateSuggestions() {
        val ic = currentInputConnection ?: return
        val textBefore = ic.getTextBeforeCursor(40, 0)?.toString().orEmpty()
        val currentWord = textBefore.substringAfterLast(" ", textBefore).trim()

        if (currentWord.isEmpty()) {
            suggestion1.text = "the"
            suggestion2.text = "Kritix"
            suggestion3.text = "I"
            return
        }

        // 1. Check known phonetic brand typos & instant autocorrect
        val lower = currentWord.lowercase()
        val brandCorrection = when (lower) {
            "critics", "critic", "kritiks", "kritik", "kritcs", "kritic", "critis" -> "Kritix"
            "teh" -> "the"
            "recieve" -> "receive"
            "kvie" -> "KVIE"
            "tauri" -> "Tauri"
            else -> null
        }

        val matches = commonWords.filter { it.startsWith(currentWord, ignoreCase = true) }
        val c1 = matches.getOrNull(0) ?: currentWord
        val c2 = brandCorrection ?: matches.getOrNull(1) ?: (currentWord.replaceFirstChar { it.uppercase() })
        val c3 = matches.getOrNull(2) ?: "..."

        suggestion1.text = c1
        suggestion2.text = c2
        suggestion3.text = c3
    }

    private fun applySuggestion(candidate: String) {
        if (candidate.isBlank() || candidate == "...") return
        val ic = currentInputConnection ?: return
        performKeyHaptic()

        val textBefore = ic.getTextBeforeCursor(40, 0)?.toString().orEmpty()
        val currentWord = textBefore.substringAfterLast(" ", textBefore).trim()
        if (currentWord.isNotEmpty()) {
            ic.deleteSurroundingText(currentWord.length, 0)
        }
        ic.commitText(candidate + " ", 1)
        updateSuggestions()
    }

    // ───────────── CLIPBOARD DRAWER ─────────────
    private fun initClipboardManager() {
        clipboardManager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboardManager.addPrimaryClipChangedListener {
            val clip = clipboardManager.primaryClip?.getItemAt(0)?.text?.toString()?.trim()
            if (!clip.isNullOrBlank() && !recentClips.contains(clip)) {
                recentClips.add(0, clip)
                if (recentClips.size > 15) recentClips.removeAt(recentClips.size - 1)
                refreshClipboardDrawer()
            }
        }
    }

    private fun setupClipboardDrawer() {
        btnClearClipboard.setOnClickListener {
            performKeyHaptic()
            recentClips.clear()
            refreshClipboardDrawer()
            clipboardDrawer.visibility = View.GONE
        }
    }

    private fun toggleClipboardDrawer() {
        if (clipboardDrawer.visibility == View.VISIBLE) {
            clipboardDrawer.visibility = View.GONE
        } else {
            refreshClipboardDrawer()
            clipboardDrawer.visibility = View.VISIBLE
        }
    }

    private fun refreshClipboardDrawer() {
        clipboardItemsContainer.removeAllViews()
        if (recentClips.isEmpty()) {
            val emptyText = TextView(this).apply {
                text = "Clipboard empty (copy text to store)"
                setTextColor(0xFF8E8E9E.toInt())
                textSize = 11f
                setPadding(10, 0, 10, 0)
            }
            clipboardItemsContainer.addView(emptyText)
            return
        }

        for (clip in recentClips) {
            val chip = TextView(this).apply {
                val params = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.MATCH_PARENT
                ).apply {
                    marginStart = 4
                    marginEnd = 4
                }
                layoutParams = params
                gravity = Gravity.CENTER
                setBackgroundResource(R.drawable.clipboard_chip_bg)
                setTextColor(0xFFFFFFFF.toInt())
                textSize = 12f
                setPadding(16, 0, 16, 0)
                isClickable = true
                isFocusable = false
                val display = if (clip.length > 25) clip.take(25) + "…" else clip
                text = display

                setOnClickListener {
                    performKeyHaptic()
                    currentInputConnection?.commitText(clip, 1)
                    clipboardDrawer.visibility = View.GONE
                }
            }
            clipboardItemsContainer.addView(chip)
        }
    }

    // ───────────── EMOJI DRAWER ─────────────
    private fun setupEmojiDrawer() {
        tabSmiley.setOnClickListener {
            performKeyHaptic()
            populateEmojiGrid(smileyEmojis)
        }
        tabGestures.setOnClickListener {
            performKeyHaptic()
            populateEmojiGrid(gestureEmojis)
        }
        tabHearts.setOnClickListener {
            performKeyHaptic()
            populateEmojiGrid(heartEmojis)
        }
        tabFire.setOnClickListener {
            performKeyHaptic()
            populateEmojiGrid(fireEmojis)
        }

        btnReturnToAbc.setOnClickListener {
            performKeyHaptic()
            emojiDrawer.visibility = View.GONE
            qwertyContainer.visibility = View.VISIBLE
        }

        btnEmojiBackspace.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.deleteSurroundingText(1, 0)
        }
    }

    private fun showEmojiDrawer() {
        qwertyContainer.visibility = View.GONE
        clipboardDrawer.visibility = View.GONE
        emojiDrawer.visibility = View.VISIBLE
        populateEmojiGrid(smileyEmojis)
    }

    private fun populateEmojiGrid(emojis: List<String>) {
        emojiGrid.removeAllViews()
        val displayWidth = resources.displayMetrics.widthPixels
        val cellWidth = (displayWidth - 24) / 7

        for (emoji in emojis) {
            val cell = TextView(this).apply {
                val params = GridLayout.LayoutParams().apply {
                    width = cellWidth
                    height = 110
                }
                layoutParams = params
                gravity = Gravity.CENTER
                text = emoji
                textSize = 24f
                isClickable = true
                isFocusable = false

                setOnClickListener {
                    performKeyHaptic()
                    currentInputConnection?.commitText(emoji, 1)
                }
            }
            emojiGrid.addView(cell)
        }
    }

    private fun setupBackspaceKey() {
        val backspaceRunnable = object : Runnable {
            override fun run() {
                if (isBackspaceHolding) {
                    performKeyHaptic()
                    currentInputConnection?.deleteSurroundingText(1, 0)
                    updateSuggestions()
                    backspaceHandler.postDelayed(this, 50)
                }
            }
        }

        keyBackspace.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    v.isPressed = true
                    isBackspaceHolding = true
                    performKeyHaptic()
                    currentInputConnection?.deleteSurroundingText(1, 0)
                    updateSuggestions()
                    backspaceHandler.postDelayed(backspaceRunnable, 400)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    v.isPressed = false
                    isBackspaceHolding = false
                    backspaceHandler.removeCallbacks(backspaceRunnable)
                    true
                }
                else -> false
            }
        }
    }

    private fun handleEnterKey() {
        val ic = currentInputConnection ?: return
        val editorInfo = currentInputEditorInfo
        val imeAction = editorInfo.imeOptions and EditorInfo.IME_MASK_ACTION

        when (imeAction) {
            EditorInfo.IME_ACTION_SEARCH,
            EditorInfo.IME_ACTION_GO,
            EditorInfo.IME_ACTION_SEND,
            EditorInfo.IME_ACTION_NEXT,
            EditorInfo.IME_ACTION_DONE -> {
                ic.performEditorAction(imeAction)
            }
            else -> {
                ic.commitText("\n", 1)
            }
        }
        updateSuggestions()
    }

    private fun performKeyHaptic() {
        keyboardRootView?.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        try {
            val am = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            am?.playSoundEffect(AudioManager.FX_KEYPRESS_STANDARD, 0.4f)
        } catch (_: Exception) {}
    }

    private fun launchFloatingMicOverlay() {
        if (!Settings.canDrawOverlays(this)) {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:$packageName")
            ).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)
            return
        }
        val serviceIntent = Intent(this, FloatingMicService::class.java)
        startService(serviceIntent)
    }

    private fun triggerAIPolish() {
        val ic = currentInputConnection ?: return
        val textBefore = ic.getTextBeforeCursor(150, 0)?.toString() ?: ""
        if (textBefore.isBlank()) return

        polishButton.text = "⏳..."
        polishButton.isEnabled = false

        scope.launch {
            try {
                val polished = AutoEditClient.refine(textBefore, this@KVIEInputMethodService)
                if (polished != null && polished.isNotBlank() && polished != textBefore) {
                    ic.deleteSurroundingText(textBefore.length, 0)
                    ic.commitText(polished, 1)
                    val targetPkg = currentInputEditorInfo?.packageName ?: lastActivePackageName ?: KVIEAccessibilityService.currentActivePackage
                    val targetApp = SessionManager.resolveAppName(this@KVIEInputMethodService, targetPkg)
                    SessionManager.recordSession(this@KVIEInputMethodService, polished, "$targetApp (AI Polish)")
                }
            } catch (_: Exception) {
            } finally {
                polishButton.text = "✨ Polish"
                polishButton.isEnabled = true
            }
        }
    }

    // ───────────── SPEECH DICTATION ENGINE ─────────────
    private fun getActiveEngineId(): String {
        val prefs = getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        return prefs.getString("active_engine", "android-speech-recognizer") ?: "android-speech-recognizer"
    }

    private fun startListening() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            statusText.text = "Mic permission needed"
            statusText.visibility = View.VISIBLE
            suggestionBar.visibility = View.GONE
            return
        }

        val activeEngine = getActiveEngineId()
        if (activeEngine.startsWith("whisper-cpp")) {
            startWhisperListening(activeEngine)
        } else {
            startSystemSpeechRecognizer()
        }
    }

    private fun startWhisperListening(modelId: String) {
        whisperEngine?.loadModel(modelId)
        isListening = true
        micButton.isSelected = true
        statusText.text = "Whisper listening... Speak now"
        statusText.visibility = View.VISIBLE
        suggestionBar.visibility = View.GONE

        engineJob = scope.launch {
            val transcript = whisperEngine?.transcribeAudio { interim ->
                if (interim.isNotBlank()) statusText.text = interim
            } ?: ""

            if (transcript.isNotBlank()) {
                handleFinalTranscript(transcript)
            } else {
                statusText.text = "KVIE AI Voice (Tap mic)"
            }
            isListening = false
            micButton.isSelected = false
            statusText.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        }
    }

    private fun initSpeechRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {}

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: android.os.Bundle?) {
                    statusText.text = "Listening... Speak now"
                }

                override fun onBeginningOfSpeech() {
                    statusText.text = "Hearing your voice..."
                }

                override fun onRmsChanged(rmsdB: Float) {
                    if (rmsdB > 2.0f && statusText.text.contains("Listening")) {
                        statusText.text = "Listening 🎙️..."
                    }
                }

                override fun onBufferReceived(buffer: ByteArray?) {}

                override fun onEndOfSpeech() {
                    statusText.text = "Transcribing & cleaning..."
                }

                override fun onResults(results: android.os.Bundle?) {
                    stopListening()
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val transcript = matches?.firstOrNull().orEmpty()
                    handleFinalTranscript(transcript)
                }

                override fun onError(error: Int) {
                    stopListening()
                    statusText.text = "Ready (Tap mic to speak)"
                }

                override fun onPartialResults(partialResults: android.os.Bundle?) {
                    val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val interim = matches?.firstOrNull().orEmpty()
                    if (interim.isNotBlank()) {
                        statusText.text = interim
                    }
                }

                override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
            })
        }
    }

    private fun startSystemSpeechRecognizer() {
        destroySpeechRecognizer()
        initSpeechRecognizer()

        if (speechRecognizer == null) {
            statusText.text = "Speech recognizer unavailable"
            isListening = false
            micButton.isSelected = false
            return
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "en-US")
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
            putExtra("android.speech.extra.DICTATION_MODE", true)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2000L)
        }

        try {
            speechRecognizer?.startListening(intent)
            isListening = true
            micButton.isSelected = true
            statusText.text = "Listening... Speak now"
            statusText.visibility = View.VISIBLE
            suggestionBar.visibility = View.GONE
        } catch (e: Exception) {
            statusText.text = "Speech error: ${e.message}"
            stopListening()
        }
    }

    private fun destroySpeechRecognizer() {
        try {
            speechRecognizer?.stopListening()
            speechRecognizer?.cancel()
            speechRecognizer?.destroy()
        } catch (_: Exception) {}
        speechRecognizer = null
    }

    private fun stopListening() {
        engineJob?.cancel()
        whisperEngine?.stopRecording()
        destroySpeechRecognizer()
        isListening = false
        micButton.isSelected = false
        statusText.visibility = View.GONE
        suggestionBar.visibility = View.VISIBLE
        updateSuggestions()
    }

    private fun handleFinalTranscript(rawTranscript: String) {
        if (rawTranscript.isBlank()) {
            return
        }

        val ic = currentInputConnection ?: return
        val cleanText = SmolLMEngine.stripFillersAndPunctuate(rawTranscript)
        if (cleanText.isBlank()) return

        val targetPkg = currentInputEditorInfo?.packageName 
            ?: lastActivePackageName 
            ?: KVIEAccessibilityService.currentActivePackage
        val targetApp = SessionManager.resolveAppName(this, targetPkg)
        val prefix = if (ic.getTextBeforeCursor(1, 0)?.endsWith(" ") == true || ic.getTextBeforeCursor(1, 0).isNullOrEmpty()) "" else " "
        ic.commitText(prefix + cleanText + " ", 1)
        SessionManager.recordSession(this, cleanText, targetApp)
        updateSuggestions()

        scope.launch {
            try {
                val refined = AutoEditClient.refine(cleanText, this@KVIEInputMethodService)
                if (refined != null && refined.isNotBlank() && refined != cleanText) {
                    val oldLen = cleanText.length + 1
                    ic.deleteSurroundingText(oldLen, 0)
                    ic.commitText(prefix + refined + " ", 1)
                    SessionManager.recordSession(this@KVIEInputMethodService, refined, "$targetApp (AI Polish)")
                    updateSuggestions()
                }
            } catch (_: Exception) {}
        }
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        val pkg = info?.packageName
        if (!pkg.isNullOrBlank()) {
            lastActivePackageName = pkg
            KVIEAccessibilityService.currentActivePackage = pkg
        }
        isShifted = false
        isCapsLock = false
        isSymbolsMode = false
        emojiDrawer.visibility = View.GONE
        clipboardDrawer.visibility = View.GONE
        qwertyContainer.visibility = View.VISIBLE
        statusText.visibility = View.GONE
        suggestionBar.visibility = View.VISIBLE
        populateKeys()
        updateSuggestions()
    }

    fun directCommitText(text: String): Boolean {
        val ic = currentInputConnection ?: return false
        val prefix = if (ic.getTextBeforeCursor(1, 0)?.endsWith(" ") == true || ic.getTextBeforeCursor(1, 0).isNullOrEmpty()) "" else " "
        val res = ic.commitText(prefix + text + " ", 1)
        updateSuggestions()
        return res
    }

    override fun onDestroy() {
        if (instance == this) instance = null
        stopListening()
        speechRecognizer?.destroy()
        backspaceHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        var instance: KVIEInputMethodService? = null
        var lastActivePackageName: String? = null

        fun commitFromExternal(text: String): Boolean {
            return instance?.directCommitText(text) ?: false
        }
    }
}
