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
import android.text.Editable
import android.text.TextUtils
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.TextWatcher
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.HorizontalScrollView
import android.widget.ImageButton
import android.widget.ScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.Normalizer
import java.util.Locale

/**
 * KVIE Next-Gen AI Voice & QWERTY Keyboard Input Method Service.
 * Flagship Features:
 * 1. Full QWERTY with Number Row Toggle & Long-Press Alt-Symbols (q->1, w->2, a->@, etc.)
 * 2. Real-Time Autocorrect & Contextual Next-Word 3-Candidate Suggestion Bar (Case-Aware)
 * 3. Native Multi-Item Clipboard History Drawer
 * 4. Massive 500+ Emoji Drawer with Real-Time Search across 8 Categories
 * 5. Instant 1-Tap AI Voice Dictation with 6 Voice Editing Commands
 * 6. Quick AI Action Chips (Formal, Casual, Shorten, To English) & Per-App Tone Defaults
 * 7. Dual Tactile Haptic & Acoustic Mechanical Key Click Feedback
 * 8. Devanagari (Hindi) Inscript keyboard + live transliteration
 * 9. Text snippet expansion (type shortcut → space → full text)
 */
class KVIEInputMethodService : InputMethodService() {

    // ── Mode ───────────────────────────────────────────────────────────────────
    enum class Mode { TEXT, EMOJI, HINDI, SNIPPETS }

    private var speechRecognizer: SpeechRecognizer? = null
    private var whisperEngine: WhisperEngine? = null
    private var parakeetEngine: ParakeetEngine? = null

    private var isListening = false
    private var isShifted = false
    private var isCapsLock = false
    private isSymbolsMode = false
    private var isSymbolsSecondaryPage = false
    private var isNumberRowVisible = true
    private var currentMode = Mode.TEXT        // TEXT | EMOJI | HINDI | SNIPPETS
    private var currentLang: Locale = Locale.ENGLISH
    private var lastBuffer = StringBuilder()

    // Top Voice & Suggestion Toolbar
    private lateinit var voiceToolbar: LinearLayout
    private lateinit var statusText: TextView
    private lateinit var micButton: ImageButton
    private lateinit var polishButton: ImageView
    private lateinit var suggestionBar: LinearLayout
    private lateinit var suggestion1: TextView
    private lateinit var suggestion2: TextView
    private lateinit var suggestion3: TextView
    private lateinit var aiActionsBar: HorizontalScrollView
    private lateinit var chipToneFormal: TextView
    private lateinit var chipToneCasual: TextView
    private lateinit var chipToneShorten: TextView
    private lateinit var chipToneTranslate: TextView
    private lateinit var btnClipboard: ImageView
    private lateinit var btnNumberRowToggle: TextView
    private lateinit var btnLangToggle: TextView
    private lateinit var btnSnippets: TextView

    // Dynamic Personal Dictionary & Autocorrect Engine
    private lateinit var userLexiconDb: UserLexiconDatabase

    data class AutocorrectRecord(
        val originalWord: String,
        val appliedWord: String,
        val timestamp: Long = System.currentTimeMillis()
    )
    private var lastAutocorrectRecord: AutocorrectRecord? = null
    private val commonWordsSet by lazy { commonWords.map { it.lowercase() }.toHashSet() }

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

    // ── Transliteration map (Latin → Devanagari) ───────────────────────────────
    private val translitMap = mapOf(
        "aa" to "आ", "ee" to "ई", "oo" to "ऊ", "ai" to "ऐ", "au" to "औ",
        "ksh" to "क्ष", "sh" to "श", "Sh" to "ष", "ny" to "ञ", "ng" to "ङ",
        "ch" to "च", "chh" to "छ", "jh" to "झ", "th" to "थ", "dh" to "ध",
        "bh" to "भ", "ph" to "फ", "gh" to "घ", "kh" to "ख",
        "a" to "अ", "i" to "इ", "e" to "ए", "u" to "उ", "o" to "ओ",
        "k" to "क", "g" to "ग", "c" to "क", "j" to "ज", "t" to "त",
        "d" to "द", "n" to "न", "p" to "प", "b" to "ब", "m" to "म",
        "y" to "य", "r" to "र", "l" to "ल", "v" to "व", "w" to "व",
        "z" to "ज़", "f" to "फ़", "q" to "क़", "x" to "क्ष",
        "h" to "ह", "s" to "स",
        "1" to "१","2" to "२","3" to "३","4" to "४",
        "5" to "५","6" to "६","7" to "७","8" to "८","9" to "९","0" to "०",
    )

    // ── Hindi consonant rows for the Inscript keyboard ─────────────────────────
    private val hindiRow0 = listOf("1","2","3","4","5","6","7","8","9","0")
    private val hindiRow1 = listOf("अ","आ","इ","ई","उ","ऊ","ए","ऐ","ओ","औ")
    private val hindiRow2 = listOf("क","ख","ग","घ","ङ","च","छ","ज","झ","ञ")
    private val hindiRow3 = listOf("ट","ठ","ड","ढ","ण","त","थ","द","ध","न")
    private val hindiRow4 = listOf("प","फ","ब","भ","म","य","र","ल","व","श")
    private val hindiRow5 = listOf("श्र","क्ष","त्","ड़","।","⎵","⌫","⏎")

    // Dynamic App Accent Color Binding
    private var currentAccentColor: Int = 0xFF22D3EE.toInt()
    private var lastCompletedWord: String? = null
    private var pendingVoiceValidationJob: Job? = null
    private var lastDictatedWords: List<String> = emptyList()

    // High-Accuracy / Most Common Word Dynamic Green Highlight
    private val highAccuracyGreenColor = 0xFF00E676.toInt() // Vibrant Neon Green
    private val secondarySuggestionColor = 0xFFA0A0B2.toInt() // Neutral Secondary
    private var currentHighlightedPillIndex: Int = 0

    private fun highlightBestSuggestion(bestIndex: Int) {
        currentHighlightedPillIndex = bestIndex
        val pills = listOf(
            if (::suggestion1.isInitialized) suggestion1 else null,
            if (::suggestion2.isInitialized) suggestion2 else null,
            if (::suggestion3.isInitialized) suggestion3 else null
        )

        for (i in pills.indices) {
            val pill = pills[i] ?: continue
            if (i == bestIndex) {
                // HIGHEST ACCURACY / MOST COMMON WORD: Vibrant Green Highlight
                pill.setTextColor(highAccuracyGreenColor)
                pill.setTypeface(null, Typeface.BOLD)

                val greenBg = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = dpToPx(14f)
                    val tint = (0x28 shl 24) or (highAccuracyGreenColor and 0x00FFFFFF)
                    setColor(tint)
                    setStroke(dpToPx(1.5f).toInt(), highAccuracyGreenColor)
                }
                pill.background = greenBg
            } else {
                // Secondary candidate: Subtle neutral grey
                pill.setTextColor(secondarySuggestionColor)
                pill.setTypeface(null, Typeface.NORMAL)
                pill.setBackgroundResource(R.drawable.suggestion_pill_bg)
            }
        }
    }

    private fun extractContextWords(textBefore: String): Pair<String, String> {
        val tokens = textBefore.trim().split(Regex("\\s+")).filter { it.isNotBlank() }
        val w1 = if (tokens.size >= 2) tokens[tokens.size - 2].lowercase() else ""
        val w2 = if (tokens.isNotEmpty()) tokens.last().lowercase() else ""
        return Pair(w1, w2)
    }

    private fun getWordCommonalityScore(word: String, typedPrefix: String, w1: String = "", w2: String = ""): Int {
        val lower = word.lowercase().trim()
        val typedLower = typedPrefix.lowercase().trim()

        if (lower.isEmpty() || lower == "...") return 0

        // 1. Calculate Base Commonality Score
        val baseScore = if (::userLexiconDb.isInitialized && userLexiconDb.isPersonalWord(lower)) {
            val personalMatches = userLexiconDb.getMatchingFrequentWords(typedLower, 5)
            val rank = personalMatches.indexOf(lower)
            if (rank != -1) 100 - rank * 4 else 92
        } else {
            val typoCorrection = grammarCorrections[typedLower]
            if (typoCorrection != null && typoCorrection.equals(lower, ignoreCase = true)) {
                96
            } else if (lower == typedLower && commonWordsSet.contains(lower)) {
                val commonRank = commonWords.indexOfFirst { it.equals(lower, ignoreCase = true) }
                if (commonRank in 0..100) 94 else 85
            } else {
                val rank = commonWords.indexOfFirst { it.equals(lower, ignoreCase = true) }
                when {
                    rank in 0..15 -> 88
                    rank in 16..60 -> 82
                    rank in 61..250 -> 76
                    rank in 251..1000 -> 68
                    rank > 1000 -> 55
                    else -> 45
                }
            }
        }

        // 2. Blend with Contextual Bandit Score (Cross-Modal Reinforcement Learning)
        return ContextualBanditEngine.calculateBlendedScore(
            w1 = w1,
            w2 = w2,
            candidate = lower,
            baseScore = baseScore,
            userLexiconDb = if (::userLexiconDb.isInitialized) userLexiconDb else null
        )
    }

    private fun loadAccentColor(): Int {
        val prefs = getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        val hex = prefs.getString("accent_color", "#22d3ee") ?: "#22d3ee"
        return try {
            Color.parseColor(hex)
        } catch (_: Exception) {
            0xFF22D3EE.toInt()
        }
    }

    private fun isColorBright(color: Int): Boolean {
        val r = Color.red(color)
        val g = Color.green(color)
        val b = Color.blue(color)
        val luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        return luminance > 0.55
    }

    private fun dpToPx(dp: Float): Float = dp * resources.displayMetrics.density

    // ── Helper: dp() ───────────────────────────────────────────────────────────
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun applyAccentTheme() {
        currentAccentColor = loadAccentColor()
        val isBright = isColorBright(currentAccentColor)

        // 1. Maintain dynamic suggestion highlight (Green on most accurate word)
        highlightBestSuggestion(currentHighlightedPillIndex)

        // 2. Enter Key Accent Styling
        if (::keyEnter.isInitialized) {
            val enterBg = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dpToPx(7f)
                setColor(currentAccentColor)
            }
            keyEnter.background = enterBg
            keyEnter.setTextColor(if (isBright) 0xFF0E0E12.toInt() else 0xFFFFFFFF.toInt())
        }

        // 3. Toolbar Sparkle / Polish Button
        if (::polishButton.isInitialized) {
            polishButton.setColorFilter(currentAccentColor)
        }

        // 4. Number row toggle button
        if (::btnNumberRowToggle.isInitialized) {
            btnNumberRowToggle.setTextColor(if (isNumberRowVisible) currentAccentColor else 0xFF8E8E9E.toInt())
        }

        // 5. Shift key visual
        updateShiftKeyVisual()

        // 6. Language toggle button
        if (::btnLangToggle.isInitialized) {
            btnLangToggle.text = if (currentLang.language == "hi") "अ" else "A"
        }
    }

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
    private lateinit var keyEmoji: ImageView
    private lateinit var keyBackspace: ImageView
    private lateinit var keySpace: TextView
    private lateinit var keyDot: TextView
    private lateinit var keyComma: TextView
    private lateinit var keyEnter: TextView

    // Emoji Drawer
    private lateinit var emojiDrawer: LinearLayout
    private lateinit var emojiGrid: GridLayout
    private lateinit var emojiSearchInput: EditText
    private lateinit var btnClearEmojiSearch: TextView
    private lateinit var tabSmiley: TextView
    private lateinit var tabGestures: TextView
    private lateinit var tabHearts: TextView
    private lateinit var tabFire: TextView
    private lateinit var tabAnimals: TextView
    private lateinit var tabFood: TextView
    private lateinit var tabTravel: TextView
    private lateinit var tabObjects: TextView
    private lateinit var btnReturnToAbc: TextView
    private lateinit var btnEmojiBackspace: ImageView
    private lateinit var modeOverlay: FrameLayout
    private var currentActiveEmojiCategory: List<String> = emptyList()

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

    // High-Frequency 2, 3, 4+ letter conversational vocabulary + Hinglish & Brands
    private val commonWords = listOf(
        // 2-letter
        "am", "an", "as", "at", "be", "by", "do", "go", "he", "hi", "if", "in", "is", "it",
        "me", "my", "no", "of", "ok", "on", "or", "so", "to", "up", "us", "we",
        // 3-letter
        "all", "and", "any", "app", "are", "bad", "big", "boy", "bus", "but", "bye", "can",
        "car", "cat", "day", "did", "dog", "end", "far", "few", "for", "fun", "get", "got",
        "guy", "had", "has", "her", "hey", "him", "his", "hot", "how", "job", "let", "lot",
        "man", "may", "new", "not", "now", "off", "old", "one", "our", "out", "pay", "put",
        "red", "run", "say", "see", "set", "she", "sir", "six", "sun", "ten", "the", "top",
        "try", "two", "use", "war", "way", "who", "why", "win", "yes", "yet", "you",
        // 4+ letter common English
        "about", "after", "again", "also", "always", "another", "around", "ask", "awesome",
        "back", "because", "before", "best", "better", "between", "both", "call", "came",
        "change", "check", "come", "cool", "could", "done", "down", "each", "even", "every",
        "feel", "find", "fine", "first", "from", "give", "going", "good", "great", "group",
        "have", "help", "here", "home", "hope", "into", "just", "keep", "kind", "know",
        "last", "later", "leave", "life", "like", "line", "little", "live", "look", "love",
        "make", "many", "meeting", "message", "might", "more", "most", "much", "must",
        "name", "need", "never", "next", "night", "nothing", "number", "office", "okay",
        "only", "other", "over", "part", "people", "place", "play", "please", "point",
        "problem", "right", "same", "school", "seem", "send", "should", "show", "side",
        "small", "some", "something", "soon", "sorry", "start", "still", "such", "sure",
        "take", "talk", "tell", "than", "thank", "thanks", "that", "their", "them", "then",
        "there", "these", "they", "thing", "think", "this", "those", "through", "time",
        "today", "together", "tomorrow", "under", "very", "wait", "want", "water", "well",
        "went", "what", "when", "where", "which", "while", "white", "will", "with", "word",
        "work", "world", "would", "write", "year", "yesterday", "your",
        // Hinglish & Everyday Indian Context
        "Kritix", "KVIE", "bhai", "kya", "ha", "nahi", "accha", "theek", "kaise", "kaha",
        "chalo", "ab", "kab", "aaj", "kal", "kar", "karo", "karna", "bolo", "bol", "dekh",
        "dekho", "sun", "suno", "aao", "jao", "mera", "meri", "hum", "tum", "aap", "yaar"
    )

    // Typo, Brand & Grammar Auto-Correction Map
    private val grammarCorrections = mapOf(
        "teh" to "the",
        "recieve" to "receive",
        "recieved" to "received",
        "seperate" to "separate",
        "untill" to "until",
        "truely" to "truly",
        "definately" to "definitely",
        "alot" to "a lot",
        "dont" to "don't",
        "cant" to "can't",
        "wont" to "won't",
        "didnt" to "didn't",
        "isnt" to "isn't",
        "arent" to "aren't",
        "wasnt" to "wasn't",
        "werent" to "weren't",
        "im" to "I'm",
        "ive" to "I've",
        "id" to "I'd",
        "ill" to "I'll",
        "youre" to "you're",
        "theyre" to "they're",
        "weve" to "we've",
        "hes" to "he's",
        "shes" to "she's",
        "thats" to "that's",
        "whats" to "what's",
        "critics" to "Kritix", "critic" to "Kritix", "kritiks" to "Kritix",
        "kritik" to "Kritix", "kritcs" to "Kritix", "kritic" to "Kritix", "critis" to "Kritix",
        "kvie" to "KVIE", "tauri" to "Tauri"
    )

    // Contextual Bigram Next-Word Prediction Map
    private val bigramContext = mapOf(
        "how" to listOf("are", "is", "about"),
        "thank" to listOf("you", "so", "much"),
        "thanks" to listOf("for", "a", "lot"),
        "let" to listOf("me", "us", "know"),
        "can" to listOf("you", "we", "I"),
        "i" to listOf("am", "will", "have"),
        "what" to listOf("is", "are", "do"),
        "where" to listOf("are", "is", "were"),
        "when" to listOf("will", "is", "can"),
        "why" to listOf("did", "is", "are"),
        "good" to listOf("morning", "night", "luck"),
        "see" to listOf("you", "it", "later"),
        "call" to listOf("me", "you", "back"),
        "please" to listOf("let", "check", "send"),
        "are" to listOf("you", "we", "they"),
        "is" to listOf("this", "it", "that"),
        "do" to listOf("you", "not", "we"),
        "you" to listOf("are", "can", "have"),
        "we" to listOf("are", "will", "can"),
        "they" to listOf("are", "will", "were"),
        "it" to listOf("is", "was", "will"),
        "this" to listOf("is", "was", "will"),
        "bhai" to listOf("kya", "kaha", "bol"),
        "kya" to listOf("hua", "hai", "kar"),
        "theek" to listOf("hai", "h", "bhai"),
        "kaise" to listOf("ho", "kare", "hoga"),
        "aap" to listOf("kaise", "kaha", "kya")
    )

    // ───────────── MASSIVE EMOJI CATALOGS (500+ EMOJIS) ─────────────
    private val smileyEmojis = listOf(
        "😀","😃","😄","😁","😆","😅","😂","🤣","🥲","🥹","😊","😇","🙂","🙃","😉","😌","😍","🥰","😘","😗",
        "😙","😚","😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🥸","🤩","🥳","😏","😒","😞","😔","😟","😕",
        "🙁","☹️","😣","😖","😫","😩","🥺","😢","😭","😮‍💨","😤","😠","😡","🤬","🤯","😳","🥵","🥶","😱","😨",
        "😰","😥","😓","🤗","🤔","🫣","🤭","🫢","🤫","🤥","😶","😶‍🌫️","😐","😑","😬","🫨","🫠","🙄","😯","😦",
        "😧","😮","😲","🥱","😴","🤤","😪","😵","😵‍💫","🤐","🥴","🤢","🤮","🤧","😷","🤒","🤕","🤑","🤠","😈",
        "👿","💀","☠️","👽","👾","🤖","🎃","😺","😸","😹","😻","😼","😽","🙀","😿","😾"
    )

    private val gestureEmojis = listOf(
        "👍","👎","👌","🤌","🤏","✌️","🤞","🫰","🤟","🤘","🤙","👈","👉","👆","🖕","👇","☝️","🫵","👋","🤚",
        "🖐️","✋","🖖","🫱","🫲","🫸","🫷","👏","🙌","🫶","👐","🤲","🤝","🙏","✍️","💅","🤳","💪","🦾","🦿",
        "🦵","🦶","👂","🦻","👃","🧠","🫀","🫁","🦷","🦴","👀","👁️","👅","👄","🫦","💋","🫂"
    )

    private val heartEmojis = listOf(
        "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝",
        "💟","💌","💋","💯","💢","💥","💫","💦","💨","🕳️","💣","💬","👁️‍🗨️","🗨️","🗯️","💭","💤","✨","⭐","🌟"
    )

    private val fireEmojis = listOf(
        "🔥","✨","⭐","🌟","⚡","🎉","🎊","🚀","🏆","🥇","🥈","🥉","👑","💎","🎯","🔮","💡","📌","🔑","🔔",
        "📢","🎵","🎶","🎤","🎧","🎮","🕹️","🎲","🧩","🎨","🎬","📸","💻","📱","⌚","💰","💵","💸","🎁","🧨",
        "🎈","🎆","🎇","🥂","🍻","🍾","🏅","🎖️","🪄","🪅","🏮","🪙"
    )

    private val animalEmojis = listOf(
        "🐶","🐱","🐭","🐹","🐰","🦊","🐻","🐼","🐻‍❄️","🐨","🐯","🦁","🐮","🐷","🐸","🐵","🐔","🐧","🐦","🐤",
        "🦆","🦅","🦉","🦇","🐺","🐗","🐴","🦄","🐝","🪱","🐛","🦋","🐌","🐞","🐜","🪰","🪲","🪳","🦟","🦗",
        "🕷️","🦂","🐢","🐍","🦎","🐙","🦑","🦐","🦞","🦀","🐡","🐠","🐟","🐬","🐳","🐋","🦈","🐊","🐅","🐆",
        "🦓","🦍","🦧","🐘","🦛","🦏","🐪","🐫","🦒","🦘","🦬","🐃","🐂","🐄","🐎","🐖","🐏","🐑","🦙","🐐"
    )

    private val foodEmojis = listOf(
        "🍕","🍔","🍟","🌭","🍿","🥓","🍳","🧇","🥞","🥪","🥗","🍱","🍣","🍜","🍩","🍫","🍰","🍦","🍨","🍧",
        "🍪","🎂","🧁","🥧","🍮","🍭","🍬","🍫","🍿","🧈","🧂","🥫","🍲","🥘","🥣","🥗","🥪","🌯","🌮","🧆",
        "🥟","🥠","🥡","🍙","🍚","🍘","🍢","🍡","🍧","🍨","🍦","☕","🧋","🍵","🍶","🍾","🍷","🍸","🍹","🍺",
        "🍻","🥂","🥃","🥤","🧋","🧃","🧉","🧊"
    )

    private val travelEmojis = listOf(
        "🚗","🏎️","🚙","🚕","🚘","🛻","🚌","🚓","🚑","🚒","🚐","🛺","🚜","🛴","🚲","🛵","🏍️","🚨","✈️","🛫",
        "🛬","🚀","🚁","🛸","⛵","🚤","🛥️","🛳️","🚢","🚂","🚆","🚇","🚊","Station","🏝️","🏔️","🌋","🗽","🗼","🏰",
        "🌃","🌅","🌄","⛺","⛺","🗺️","🏖️","🏕️","🏠","🏡","🏢","🏬","🏦","🏥","🏨","🏪","🏫","🏭","🏯"
    )

    private val objectEmojis = listOf(
        "💡","📱","💻","⌨️","⌚","📷","🔍","🔒","🔑","💰","💳","💎","📦","✉️","📌","⏰","🔋","🛠️","🧰","🪛",
        "🔧","🔨","⚙️","✂️","📐","📏","📎","🖊️","🖋️","✏️","📝","📁","📂","📅","📊","📈","📉","🗑️","🚪","🛏️",
        "🛋️","🪑","🧴","🧼","🪥","🪒","🩹","🩺","💉","💊","🔭","🔬","🧪","🧯","🛒","🚬","⚰️","🪦"
    )

    // Emoji search keywords map for real-time query matching
    private val emojiKeywords: Map<String, List<String>> = mapOf(
        "smile" to listOf("😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌"),
        "laugh" to listOf("😂","🤣","😆","😄","😃","😁","😹"),
        "love" to listOf("❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞","💓","💗","💖","💘","💝","💟","💌","😍","🥰","😘"),
        "heart" to listOf("❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞","💓","💗","💖","💘","💝"),
        "fire" to listOf("🔥","💥","⚡","🌟","💫","🧨","🥵"),
        "hot" to listOf("🔥","🥵","☀️","🌶️","♨️"),
        "cool" to listOf("😎","🥶","🧊","🤙","🕶️"),
        "cry" to listOf("😭","😢","🥺","😿","💧","😥","😰"),
        "sad" to listOf("😞","😔","😟","😕","🙁","☹️","😣","😖","😫","😩","🥺","😢","😭"),
        "angry" to listOf("😠","😡","🤬","😤","👿","💢"),
        "think" to listOf("🤔","🧐","🤨","💭","💡"),
        "kiss" to listOf("😘","😗","😙","😚","💋","😽"),
        "hand" to listOf("👍","👎","👌","✌️","🤞","🤟","🤘","🤙","👈","👉","👆","👇","☝️","👋","🤚","🖐️","✋","🖖","👏","🙌","👐","🤲","🤝","🙏"),
        "clap" to listOf("👏","🙌","🎉"),
        "dog" to listOf("🐶","🐕","🦮","🐩","🐾","🐺","🦊"),
        "cat" to listOf("🐱","🐈","😸","😹","😻","😼","😽","🙀","😿","😾","🦁","🐯"),
        "food" to listOf("🍕","🍔","🍟","🌭","🍿","🥓","🍳","🧇","🥞","🥪","🥗","🍱","🍣","🍜","🍩","🍫","🍰","🍦","🍧","🍪"),
        "pizza" to listOf("🍕"),
        "burger" to listOf("🍔"),
        "coffee" to listOf("☕","🧋","🍵"),
        "beer" to listOf("🍻","🍺","🥂","🍷","🍾"),
        "party" to listOf("🎉","🎊","🥳","🍾","🎈","🎂","🎁"),
        "money" to listOf("💰","💵","💸","🤑","💳","💎","🪙"),
        "work" to listOf("💼","💻","⌨️","🖥️","📱","📊","📈","📉","📝"),
        "car" to listOf("🚗","🏎️","🚙","🚕","🚘","🛻","🚌","🚓","🚑","🚒"),
        "flight" to listOf("✈️","🛫","🛬","🚀","🚁"),
        "plane" to listOf("✈️","🛫","🛬"),
        "star" to listOf("⭐","🌟","✨","💫","🤩","🌠"),
        "game" to listOf("🎮","🕹️","🎲","🎯","🧩","🎰"),
        "music" to listOf("🎵","🎶","🎤","🎧","🎸","🎹","🎺","🎻","🥁"),
        "sport" to listOf("⚽","🏀","🏈","⚾","🎾","🏐","🏉","🎱","🏓","🏸","🥊","🚴","🏋️","🛹"),
        "ok" to listOf("👌","👍","🙆","🆗","✅"),
        "yes" to listOf("👍","✅","✔️","☑️","🙌"),
        "no" to listOf("👎","❌","🚫","🙅","⛔"),
        "flag" to listOf("🇮🇳","🇺🇸","🇬🇧","🇨🇦","🇦🇺","🇯🇵","🇩🇪","🇫🇷","🇧🇷","🏁")
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
        userLexiconDb = UserLexiconDatabase.getInstance(this)

        // Toolbar Views
        voiceToolbar = view.findViewById(R.id.voiceToolbar)
        statusText = view.findViewById(R.id.statusText)
        micButton = view.findViewById(R.id.micButton)
        polishButton = view.findViewById(R.id.polishButton)
        suggestionBar = view.findViewById(R.id.suggestionBar)
        suggestion1 = view.findViewById(R.id.suggestion1)
        suggestion2 = view.findViewById(R.id.suggestion2)
        suggestion3 = view.findViewById(R.id.suggestion3)
        aiActionsBar = view.findViewById(R.id.aiActionsBar)
        chipToneFormal = view.findViewById(R.id.chipToneFormal)
        chipToneCasual = view.findViewById(R.id.chipToneCasual)
        chipToneShorten = view.findViewById(R.id.chipToneShorten)
        chipToneTranslate = view.findViewById(R.id.chipToneTranslate)
        btnClipboard = view.findViewById(R.id.btnClipboard)
        btnNumberRowToggle = view.findViewById(R.id.btnNumberRowToggle)
        btnLangToggle = view.findViewById(R.id.btnLangToggle)
        btnSnippets = view.findViewById(R.id.btnSnippets)

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
        emojiSearchInput = view.findViewById(R.id.emojiSearchInput)
        btnClearEmojiSearch = view.findViewById(R.id.btnClearEmojiSearch)
        tabSmiley = view.findViewById(R.id.tabSmiley)
        tabGestures = view.findViewById(R.id.tabGestures)
        tabHearts = view.findViewById(R.id.tabHearts)
        tabFire = view.findViewById(R.id.tabFire)
        tabAnimals = view.findViewById(R.id.tabAnimals)
        tabFood = view.findViewById(R.id.tabFood)
        tabTravel = view.findViewById(R.id.tabTravel)
        tabObjects = view.findViewById(R.id.tabObjects)
        btnReturnToAbc = view.findViewById(R.id.btnReturnToAbc)
        btnEmojiBackspace = view.findViewById(R.id.btnEmojiBackspace)
        modeOverlay = view.findViewById(R.id.modeOverlay)

        currentActiveEmojiCategory = smileyEmojis

        setupToolbarActions(view)
        setupKeypadActions()
        setupClipboardDrawer()
        setupEmojiDrawer()

        populateNumberRow()
        populateKeys()
        applyAccentTheme()
        updateSuggestions()
        updateEnterKeyActionVisual()

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
            toggleAiActionsBar()
        }

        chipToneFormal.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish("formal")
            aiActionsBar.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        }

        chipToneCasual.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish("casual")
            aiActionsBar.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        }

        chipToneShorten.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish("concise")
            aiActionsBar.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        }

        chipToneTranslate.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish("english")
            aiActionsBar.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        }

        btnClipboard.setOnClickListener {
            performKeyHaptic()
            toggleClipboardDrawer()
        }

        btnNumberRowToggle.setOnClickListener {
            performKeyHaptic()
            isNumberRowVisible = !isNumberRowVisible
            rowNumbers.visibility = if (isNumberRowVisible) View.VISIBLE else View.GONE
            btnNumberRowToggle.setTextColor(if (isNumberRowVisible) currentAccentColor else 0xFF8E8E9E.toInt())
        }

        view.findViewById<ImageButton>(R.id.switchKeyboardButton)?.setOnClickListener {
            performKeyHaptic()
            val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager
            imm?.showInputMethodPicker()
        }

        btnLangToggle.setOnClickListener {
            performKeyHaptic()
            switchLanguage()
        }

        btnSnippets.setOnClickListener {
            performKeyHaptic()
            switchMode(Mode.SNIPPETS)
        }

        suggestion1.setOnClickListener { applySuggestion(suggestion1.text.toString()) }
        suggestion2.setOnClickListener { applySuggestion(suggestion2.text.toString()) }
        suggestion3.setOnClickListener { applySuggestion(suggestion3.text.toString()) }
    }

    private fun toggleAiActionsBar() {
        if (aiActionsBar.visibility == View.VISIBLE) {
            aiActionsBar.visibility = View.GONE
            suggestionBar.visibility = View.VISIBLE
        } else {
            aiActionsBar.visibility = View.VISIBLE
            suggestionBar.visibility = View.GONE
        }
    }

    private fun setupKeypadActions() {
        keyShift.setOnClickListener {
            performKeyHaptic()
            handleShiftKey()
        }

        keyShift.setOnLongClickListener {
            performKeyHaptic()
            isCapsLock = !isCapsLock
            isShifted = isCapsLock
            updateShiftKeyVisual()
            populateKeys()
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

        keySpace.setOnClickListener {
            performKeyHaptic()
            val ic = currentInputConnection ?: return@setOnClickListener

            // Record word for personal dictionary
            val textBefore = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
            val currentWord = textBefore.substringAfterLast(" ", textBefore).trim()
            if (currentWord.isNotEmpty()) {
                if (::userLexiconDb.isInitialized) {
                    userLexiconDb.recordWordTyped(currentWord)
                    if (lastCompletedWord != null) {
                        userLexiconDb.recordTransition(lastCompletedWord!!, currentWord)
                    }
                }
                lastCompletedWord = currentWord
                lastAutocorrectRecord = null
            }

            // 1. Check snippet trigger
            val word = currentWord
            val snippetExpansion = snippets[word.lowercase(Locale.getDefault())]
            if (snippetExpansion != null) {
                ic.deleteSurroundingText(word.length + 1, 0)
                ic.commitText(snippetExpansion + " ", 1)
                updateSuggestions()
                return@setOnClickListener
            }

            // 2. Live transliteration if in Hindi mode
            if (currentLang.language == "hi" && word.isNotEmpty()) {
                val translit = tryTransliterate(word)
                if (translit != word) {
                    ic.deleteSurroundingText(word.length, 0)
                    ic.commitText(translit + " ", 1)
                    updateSuggestions()
                    return@setOnClickListener
                }
            }

            // 3. Regular space
            ic.commitText(" ", 1)
            if (!isCapsLock && isShifted) {
                isShifted = false
                updateShiftKeyVisual()
                populateKeys()
            }
            updateSuggestions()
        }

        keyDot.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.commitText(".", 1)
            updateSuggestions()
        }

        keyComma.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.commitText(",", 1)
            updateSuggestions()
        }

        keyEnter.setOnClickListener {
            performKeyHaptic()
            handleEnterKey()
        }

        keyEnter.setOnLongClickListener {
            performKeyHaptic()
            insertNewline()
            updateSuggestions()
            true
        }

        setupBackspaceKey()
    }

    // ───────────── KEY POPULATION & RENDERING ─────────────
    private fun populateNumberRow() {
        rowNumbers.removeAllViews()
        for (num in numberKeys) {
            val keyView = createKeyButton(num, 1.0f)
            keyView.setOnClickListener {
                performKeyHaptic()
                currentInputConnection?.commitText(num, 1)
                updateSuggestions()
            }
            rowNumbers.addView(keyView)
        }
    }

    private fun populateKeys() {
        currentKeyButtons.clear()
        row1.removeAllViews()
        row2.removeAllViews()
        row3Letters.removeAllViews()

        if (isSymbolsMode) {
            populateSymbols()
        } else {
            populateAlphabet()
        }
        updateShiftKeyVisual()
    }

    private fun populateAlphabet() {
        keySymbols.text = "?123"

        for (char in alphabetKeysRow1) {
            val displayChar = if (isShifted || isCapsLock) char.uppercase() else char
            val key = createKeyButton(displayChar, 1.0f, altSymbolMap[char])
            setupKeyTouchAndLongPress(key, displayChar, altSymbolMap[char])
            row1.addView(key)
            currentKeyButtons.add(key)
        }

        for (char in alphabetKeysRow2) {
            val displayChar = if (isShifted || isCapsLock) char.uppercase() else char
            val key = createKeyButton(displayChar, 1.0f, altSymbolMap[char])
            setupKeyTouchAndLongPress(key, displayChar, altSymbolMap[char])
            row2.addView(key)
            currentKeyButtons.add(key)
        }

        for (char in alphabetKeysRow3) {
            val displayChar = if (isShifted || isCapsLock) char.uppercase() else char
            val key = createKeyButton(displayChar, 1.0f, altSymbolMap[char])
            setupKeyTouchAndLongPress(key, displayChar, altSymbolMap[char])
            row3Letters.addView(key)
            currentKeyButtons.add(key)
        }
    }

    private fun populateSymbols() {
        keySymbols.text = "ABC"

        val page1 = !isSymbolsSecondaryPage
        val r1 = if (page1) symbolKeysRow1 else symbolPage2Row1
        val r2 = if (page1) symbolKeysRow2 else symbolPage2Row2
        val r3 = if (page1) symbolKeysRow3 else symbolPage2Row3

        for (sym in r1) {
            val key = createKeyButton(sym, 1.0f)
            key.setOnClickListener {
                performKeyHaptic()
                currentInputConnection?.commitText(sym, 1)
                updateSuggestions()
            }
            row1.addView(key)
            currentKeyButtons.add(key)
        }

        for (sym in r2) {
            val key = createKeyButton(sym, 1.0f)
            key.setOnClickListener {
                performKeyHaptic()
                currentInputConnection?.commitText(sym, 1)
                updateSuggestions()
            }
            row2.addView(key)
            currentKeyButtons.add(key)
        }

        for (sym in r3) {
            val key = createKeyButton(sym, 1.0f)
            key.setOnClickListener {
                performKeyHaptic()
                currentInputConnection?.commitText(sym, 1)
                updateSuggestions()
            }
            row3Letters.addView(key)
            currentKeyButtons.add(key)
        }
    }

    private fun createKeyButton(label: String, weight: Float, altSymbol: String? = null): TextView {
        val tv = TextView(this).apply {
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, weight).apply {
                marginStart = 2
                marginEnd = 2
            }
            layoutParams = params
            gravity = Gravity.CENTER
            setBackgroundResource(R.drawable.key_bg)
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 18f
            isClickable = true
            isFocusable = false
            text = label
        }
        return tv
    }

    private fun setupKeyTouchAndLongPress(keyView: TextView, primaryChar: String, altChar: String?) {
        keyView.setOnClickListener {
            performKeyHaptic()
            lastAutocorrectRecord = null
            currentInputConnection?.commitText(primaryChar, 1)
            if (isShifted && !isCapsLock) {
                isShifted = false
                updateShiftKeyVisual()
                populateKeys()
            }
            updateSuggestions()
        }

        if (altChar != null) {
            keyView.setOnLongClickListener {
                performKeyHaptic()
                currentInputConnection?.commitText(altChar, 1)
                updateSuggestions()
                true
            }
        }
    }

    private fun handleShiftKey() {
        if (isSymbolsMode) {
            isSymbolsSecondaryPage = !isSymbolsSecondaryPage
            keyShift.text = if (isSymbolsSecondaryPage) "1/2" else "2/2"
            populateKeys()
        } else {
            if (isCapsLock) {
                isCapsLock = false
                isShifted = false
            } else {
                isShifted = !isShifted
            }
            updateShiftKeyVisual()
            populateKeys()
        }
    }

    private fun updateShiftKeyVisual() {
        if (!::keyShift.isInitialized) return
        if (isSymbolsMode) {
            keyShift.text = if (isSymbolsSecondaryPage) "1/2" else "2/2"
            keyShift.setTextColor(currentAccentColor)
        } else {
            keyShift.text = "⇧"
            when {
                isCapsLock -> keyShift.setTextColor(currentAccentColor)
                isShifted -> keyShift.setTextColor(0xFFD7FB52.toInt())
                else -> keyShift.setTextColor(0xFFFFFFFF.toInt())
            }
        }
    }

    private fun toggleSymbolsMode() {
        isSymbolsMode = !isSymbolsMode
        isSymbolsSecondaryPage = false
        isShifted = false
        isCapsLock = false
        populateKeys()
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Mode Switching (TEXT / EMOJI / HINDI / SNIPPETS)
    // ══════════════════════════════════════════════════════════════════════════

    private fun switchMode(mode: Mode) {
        currentMode = mode
        modeOverlay.removeAllViews()
        when (mode) {
            Mode.TEXT -> {
                qwertyContainer.visibility = View.VISIBLE
                modeOverlay.visibility = View.GONE
            }
            Mode.EMOJI -> showEmojiDrawer()
            Mode.HINDI -> showHindiKeyboard()
            Mode.SNIPPETS -> showSnippetKeyboard()
        }
    }

    private fun switchLanguage() {
        currentLang = when (currentLang.language) {
            "en" -> Locale("hi")
            "hi" -> Locale.ENGLISH
            else -> Locale.ENGLISH
        }
        btnLangToggle.text = if (currentLang.language == "hi") "अ" else "A"
        if (currentMode == Mode.TEXT) {
            switchMode(Mode.TEXT)
        }
    }

    private fun setModeOverlayVisible(visible: Boolean) {
        if (visible) {
            qwertyContainer.visibility = View.GONE
            emojiDrawer.visibility = View.GONE
            modeOverlay.visibility = View.VISIBLE
        } else {
            modeOverlay.visibility = View.GONE
            qwertyContainer.visibility = View.VISIBLE
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Hindi Keyboard (Devanagari Inscript Layout)
    // ══════════════════════════════════════════════════════════════════════════

    private fun showHindiKeyboard() {
        setModeOverlayVisible(true)
        modeOverlay.removeAllViews()

        val scroll = ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        scroll.addView(container)
        modeOverlay.addView(scroll)

        container.addView(TextView(this).apply {
            text = "Type in Devanagari (Inscript layout)"
            setTextColor(Color.parseColor("#888888"))
            textSize = 12f
            setPadding(dp(4), dp(2), dp(4), dp(6))
        })

        container.addView(buildHindiRow(hindiRow0, isSpecial = false))
        container.addView(buildHindiRow(hindiRow1, isSpecial = false))
        container.addView(buildHindiRow(hindiRow2, isSpecial = false))
        container.addView(buildHindiRow(hindiRow3, isSpecial = false))
        container.addView(buildHindiRow(hindiRow4, isSpecial = false))

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
        }.also {
            it.setOnClickListener { commitHindiText(output) }
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // Snippet Keyboard
    // ══════════════════════════════════════════════════════════════════════════

    private fun showSnippetKeyboard() {
        setModeOverlayVisible(true)
        modeOverlay.removeAllViews()

        val scroll = ScrollView(this)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        scroll.addView(container)
        modeOverlay.addView(scroll)

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

            row.addView(Button(this).apply {
                text = shortcut
                textSize = 16f
                setTypeface(null, Typeface.BOLD)
                minWidth = 0
                minHeight = 0
                setPadding(dp(10), dp(8), dp(10), dp(8))
                layoutParams = LinearLayout.LayoutParams(dp(100), dp(44)).apply {
                    rightMargin = dp(4)
                }
                background = resources.getDrawable(android.R.attr.selectableItemBackground, theme)
                setTextColor(Color.parseColor("#D7FB52"))
                setOnClickListener { commitSnippet(shortcut, expansion) }
            })

            row.addView(TextView(this).apply {
                text = "→"
                textSize = 20f
                setTextColor(Color.parseColor("#888888"))
                layoutParams = LinearLayout.LayoutParams(dp(36), dp(44)).apply {
                    gravity = Gravity.CENTER
                }
            })

            row.addView(Button(this).apply {
                text = expansion
                textSize = 14f
                minWidth = 0
                minHeight = 0
                setPadding(dp(10), dp(8), dp(10), dp(8))
                layoutParams = LinearLayout.LayoutParams(0, dp(44), 1f).apply {
                    leftMargin = dp(4)
                }
                background = resources.getDrawable(android.R.attr.selectableItemBackground, theme)
                setTextColor(Color.WHITE)
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                gravity = Gravity.START
                setOnClickListener { commitSnippet(shortcut, expansion) }
            })

            container.addView(row)
        }

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

    private fun commitHindiText(text: String) {
        val ic = currentInputConnection ?: return
        ic.commitText(text, 1)
        if (text.length <= 1) {
            lastBuffer.append(text)
        }
    }

    // ───────────── INTERACTIVE AUTOCORRECT & CONTEXTUAL PREDICTION ─────────────
    private fun checkIsSentenceStart(textBefore: String): Boolean {
        val trimmed = textBefore.trimEnd()
        if (trimmed.isEmpty()) return true
        val lastChar = trimmed.last()
        return lastChar == '.' || lastChar == '?' || lastChar == '!' || lastChar == '\n'
    }

    private fun formatSuggestion(word: String, input: String, isSentenceStart: Boolean): String {
        if (word.equals("Kritix", ignoreCase = true)) return "Kritix"
        if (word.equals("KVIE", ignoreCase = true)) return "KVIE"
        if (word.equals("I", ignoreCase = true) || word.equals("I'm", ignoreCase = true) ||
            word.equals("I've", ignoreCase = true) || word.equals("I'd", ignoreCase = true) ||
            word.equals("I'll", ignoreCase = true)) {
            return word.replaceFirstChar { it.uppercase() }
        }
        return when {
            input.length > 1 && input.all { it.isUpperCase() } -> word.uppercase()
            (input.isNotEmpty() && input[0].isUpperCase()) || isSentenceStart -> word.replaceFirstChar { it.uppercase() }
            else -> word.lowercase()
        }
    }

    private fun updateSuggestions() {
        val ic = currentInputConnection ?: return
        val textBefore = ic.getTextBeforeCursor(80, 0)?.toString().orEmpty()
        val isSentenceStart = checkIsSentenceStart(textBefore.dropLastWhile { !it.isWhitespace() })

        val hasTrailingSpace = textBefore.endsWith(" ") || textBefore.isEmpty()
        val currentWord = if (hasTrailingSpace) "" else textBefore.substringAfterLast(" ", textBefore).trim()

        // ───────────── 1. HIGH-ACCURACY SENTENCE PREDICTION (Space or Sentence Start) ─────────────
        if (currentWord.isEmpty()) {
            val scoredList = SentencePredictor.predictNextWords(
                textBefore = textBefore,
                isSentenceStart = isSentenceStart,
                userLexiconDb = if (::userLexiconDb.isInitialized) userLexiconDb else null,
                limit = 3
            )

            val c1 = scoredList.getOrNull(0)?.let { formatSuggestion(it.word, "", isSentenceStart) } ?: "I"
            val c2 = scoredList.getOrNull(1)?.let { formatSuggestion(it.word, "", isSentenceStart) } ?: "the"
            val c3 = scoredList.getOrNull(2)?.let { formatSuggestion(it.word, "", isSentenceStart) } ?: "you"

            suggestion1.text = c1
            suggestion2.text = c2
            suggestion3.text = c3

            // Candidate 0 is the highest accuracy candidate for the sentence -> GREEN HIGHLIGHT
            highlightBestSuggestion(0)
            return
        }

        // ───────────── 2. WORD COMPLETION & AUTOCORRECT WITH COMMONALITY SCORING ─────────────
        val lower = currentWord.lowercase()

        // Tier 1: Personal Dynamic Lexicon (Learned words with frequency >= 2)
        val personalMatches = if (::userLexiconDb.isInitialized) {
            userLexiconDb.getMatchingFrequentWords(currentWord, 3)
        } else emptyList()

        if (personalMatches.isNotEmpty() && personalMatches[0].equals(lower, ignoreCase = true)) {
            val c1 = formatSuggestion(personalMatches[0], currentWord, isSentenceStart)
            val fallbackMatches = commonWords.filter { it.startsWith(lower, ignoreCase = true) && !it.equals(lower, ignoreCase = true) }
            val c2 = personalMatches.getOrNull(1)?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                ?: fallbackMatches.getOrNull(0)?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                ?: currentWord
            val c3 = personalMatches.getOrNull(2)?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                ?: fallbackMatches.getOrNull(1)?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                ?: "..."

            suggestion1.text = c1
            suggestion2.text = c2
            suggestion3.text = c3

            val (w1, w2) = extractContextWords(textBefore.removeSuffix(currentWord))
            val s1 = getWordCommonalityScore(c1, currentWord, w1, w2)
            val s2 = getWordCommonalityScore(c2, currentWord, w1, w2)
            val s3 = getWordCommonalityScore(c3, currentWord, w1, w2)
            val bestIdx = when {
                s2 > s1 && s2 >= s3 -> 1
                s3 > s1 && s3 > s2 -> 2
                else -> 0
            }
            highlightBestSuggestion(bestIdx)
            return
        }

        // Tier 2: Grammar, Typo & Brand Corrections (Unless suppressed by user undo)
        val correction = grammarCorrections[lower]
        val isSuppressed = ::userLexiconDb.isInitialized && correction != null && userLexiconDb.isCorrectionSuppressed(currentWord, correction)
        if (correction != null && !isSuppressed) {
            val formatted = formatSuggestion(correction, currentWord, isSentenceStart)
            val c1 = formatted
            val c2 = currentWord // Keep literal
            val matches = commonWords.filter { it.startsWith(lower, ignoreCase = true) && !it.equals(correction, ignoreCase = true) }
            val c3 = matches.firstOrNull()?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: "..."

            suggestion1.text = c1
            suggestion2.text = c2
            suggestion3.text = c3

            // Correction has higher accuracy than the typo: Pill 1 is GREEN
            highlightBestSuggestion(0)
            return
        }

        // Tier 3: Spatial Neighbor QWERTY Correction (e.g. 'yiu' -> 'you', 'wprk' -> 'work')
        val isKnownWord = commonWordsSet.contains(lower) || (::userLexiconDb.isInitialized && userLexiconDb.isPersonalWord(lower))
        if (!isKnownWord && currentWord.length >= 2) {
            val spatialCandidates = SpatialCorrector.findCorrections(
                currentWord,
                isWordValid = { cand ->
                    val inDict = commonWordsSet.contains(cand) || (::userLexiconDb.isInitialized && userLexiconDb.isPersonalWord(cand))
                    inDict && !(::userLexiconDb.isInitialized && userLexiconDb.isCorrectionSuppressed(currentWord, cand))
                },
                maxResults = 2
            )
            if (spatialCandidates.isNotEmpty()) {
                val c1 = formatSuggestion(spatialCandidates[0], currentWord, isSentenceStart)
                val c2 = currentWord // Keep literal typed
                val secondSpatial = spatialCandidates.getOrNull(1)
                val fallbackMatches = commonWords.filter { it.startsWith(lower, ignoreCase = true) }
                val c3 = secondSpatial?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                    ?: fallbackMatches.firstOrNull()?.let { formatSuggestion(it, currentWord, isSentenceStart) }
                    ?: "..."

                suggestion1.text = c1
                suggestion2.text = c2
                suggestion3.text = c3

                // Spatial correction is higher accuracy than typo: Pill 1 is GREEN
                highlightBestSuggestion(0)
                return
            }
        }

        // Tier 4: Standard Prefix Autocomplete (Prioritizing Personal Lexicon matches)
        val candidatePool = if (personalMatches.isNotEmpty()) {
            (personalMatches + commonWords.filter { it.startsWith(lower, ignoreCase = true) }).distinct()
        } else {
            commonWords.filter { it.startsWith(lower, ignoreCase = true) }
        }

        val c1 = candidatePool.getOrNull(0)?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: currentWord
        val c2 = if (candidatePool.size > 1) formatSuggestion(candidatePool[1], currentWord, isSentenceStart) else currentWord
        val c3 = candidatePool.getOrNull(2)?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: "..."

        suggestion1.text = c1
        suggestion2.text = c2
        suggestion3.text = c3

        // Dynamically score all three pills with contextual bandit weighting
        val (w1, w2) = extractContextWords(textBefore.removeSuffix(currentWord))
        val s1 = getWordCommonalityScore(c1, currentWord, w1, w2)
        val s2 = getWordCommonalityScore(c2, currentWord, w1, w2)
        val s3 = getWordCommonalityScore(c3, currentWord, w1, w2)

        val bestIdx = when {
            s2 > s1 && s2 >= s3 -> 1
            s3 > s1 && s3 > s2 -> 2
            else -> 0
        }
        highlightBestSuggestion(bestIdx)
    }

    private fun applySuggestion(candidate: String) {
        if (candidate.isBlank() || candidate == "...") return
        val ic = currentInputConnection ?: return
        performKeyHaptic()

        val textBefore = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
        val currentWord = textBefore.substringAfterLast(" ", textBefore).trim()
        val (w1, w2) = extractContextWords(textBefore.removeSuffix(currentWord))

        if (currentWord.isNotEmpty()) {
            ic.deleteSurroundingText(currentWord.length, 0)
        }
        ic.commitText(candidate + " ", 1)

        // Set up undo record if autocorrect changed the word
        if (currentWord.isNotEmpty() && !currentWord.equals(candidate, ignoreCase = true)) {
            lastAutocorrectRecord = AutocorrectRecord(currentWord, candidate)
        } else {
            lastAutocorrectRecord = null
        }

        // Increment frequency in personal lexicon and record word transition
        if (::userLexiconDb.isInitialized) {
            userLexiconDb.recordWordTyped(candidate)
            if (lastCompletedWord != null) {
                userLexiconDb.recordTransition(lastCompletedWord!!, candidate)
            }
            // Reward the Contextual Bandit (+1.0 for explicit user tap)
            ContextualBanditEngine.rewardSuggestionAccepted(w1, w2, candidate, userLexiconDb)
        }
        lastCompletedWord = candidate

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
            emojiDrawer.visibility = View.GONE
            refreshClipboardDrawer()
            clipboardDrawer.visibility = View.VISIBLE
        }
    }

    private fun refreshClipboardDrawer() {
        clipboardItemsContainer.removeAllViews()
        if (recentClips.isEmpty()) {
            val emptyTv = TextView(this).apply {
                text = "Clipboard is empty"
                setTextColor(0xFF8E8E9E.toInt())
                textSize = 12f
                setPadding(16, 0, 16, 0)
            }
            clipboardItemsContainer.addView(emptyTv)
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

    // ───────────── EMOJI DRAWER & REAL-TIME SEARCH ─────────────
    private fun setupEmojiDrawer() {
        tabSmiley.setOnClickListener { selectEmojiCategory(smileyEmojis) }
        tabGestures.setOnClickListener { selectEmojiCategory(gestureEmojis) }
        tabHearts.setOnClickListener { selectEmojiCategory(heartEmojis) }
        tabFire.setOnClickListener { selectEmojiCategory(fireEmojis) }
        tabAnimals.setOnClickListener { selectEmojiCategory(animalEmojis) }
        tabFood.setOnClickListener { selectEmojiCategory(foodEmojis) }
        tabTravel.setOnClickListener { selectEmojiCategory(travelEmojis) }
        tabObjects.setOnClickListener { selectEmojiCategory(objectEmojis) }

        emojiSearchInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val query = s?.toString().orEmpty()
                btnClearEmojiSearch.visibility = if (query.isNotEmpty()) View.VISIBLE else View.GONE
                filterEmojis(query)
            }
            override fun afterTextChanged(s: Editable?) {}
        })

        btnClearEmojiSearch.setOnClickListener {
            performKeyHaptic()
            emojiSearchInput.setText("")
            populateEmojiGrid(currentActiveEmojiCategory)
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

    private fun selectEmojiCategory(category: List<String>) {
        performKeyHaptic()
        currentActiveEmojiCategory = category
        emojiSearchInput.setText("")
        populateEmojiGrid(category)
    }

    private fun filterEmojis(query: String) {
        val q = query.trim().lowercase()
        if (q.isEmpty()) {
            populateEmojiGrid(currentActiveEmojiCategory)
            return
        }

        val results = mutableSetOf<String>()
        for ((keyword, list) in emojiKeywords) {
            if (keyword.contains(q) || q.contains(keyword)) {
                results.addAll(list)
            }
        }
        if (results.isEmpty()) {
            results.addAll(smileyEmojis.take(28))
        }
        populateEmojiGrid(results.toList())
    }

    private fun showEmojiDrawer() {
        qwertyContainer.visibility = View.GONE
        clipboardDrawer.visibility = View.GONE
        aiActionsBar.visibility = View.GONE
        emojiDrawer.visibility = View.VISIBLE
        selectEmojiCategory(smileyEmojis)
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

                    // ───────────── AUTOCORRECT UNDO-LEARNING LOOP ─────────────
                    val undoRecord = lastAutocorrectRecord
                    val ic = currentInputConnection
                    if (undoRecord != null && ic != null && (System.currentTimeMillis() - undoRecord.timestamp < 5000)) {
                        val textBefore = ic.getTextBeforeCursor(undoRecord.appliedWord.length + 2, 0)?.toString().orEmpty()
                        val withSpace = undoRecord.appliedWord + " "
                        val withoutSpace = undoRecord.appliedWord

                        if (textBefore.endsWith(withSpace)) {
                            // Immediately revert text buffer back to what the user actually typed
                            ic.deleteSurroundingText(withSpace.length, 0)
                            ic.commitText(undoRecord.originalWord, 1)
                            if (::userLexiconDb.isInitialized) {
                                userLexiconDb.suppressCorrection(undoRecord.originalWord, undoRecord.appliedWord)
                                val fullText = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
                                val (w1, w2) = extractContextWords(fullText)
                                ContextualBanditEngine.rewardAutocorrectUndone(
                                    w1 = w1,
                                    w2 = w2,
                                    originalTyped = undoRecord.originalWord,
                                    rejectedCorrection = undoRecord.appliedWord,
                                    userLexiconDb = userLexiconDb
                                )
                            }
                            lastAutocorrectRecord = null
                            updateSuggestions()
                            return@setOnTouchListener true
                        } else if (textBefore.endsWith(withoutSpace)) {
                            ic.deleteSurroundingText(withoutSpace.length, 0)
                            ic.commitText(undoRecord.originalWord, 1)
                            if (::userLexiconDb.isInitialized) {
                                userLexiconDb.suppressCorrection(undoRecord.originalWord, undoRecord.appliedWord)
                                val fullText = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
                                val (w1, w2) = extractContextWords(fullText)
                                ContextualBanditEngine.rewardAutocorrectUndone(
                                    w1 = w1,
                                    w2 = w2,
                                    originalTyped = undoRecord.originalWord,
                                    rejectedCorrection = undoRecord.appliedWord,
                                    userLexiconDb = userLexiconDb
                                )
                            }
                            lastAutocorrectRecord = null
                            updateSuggestions()
                            return@setOnTouchListener true
                        }
                    }
                    lastAutocorrectRecord = null

                    // If user is backspacing right after voice dictation, penalize that word in the bandit
                    if (pendingVoiceValidationJob?.isActive == true && lastDictatedWords.isNotEmpty()) {
                        pendingVoiceValidationJob?.cancel()
                        val fullText = ic?.getTextBeforeCursor(60, 0)?.toString().orEmpty()
                        val (w1, w2) = extractContextWords(fullText)
                        val deletedWord = lastDictatedWords.lastOrNull().orEmpty()
                        if (::userLexiconDb.isInitialized && deletedWord.isNotEmpty()) {
                            ContextualBanditEngine.rewardVoiceWordDeleted(w1, w2, deletedWord, userLexiconDb)
                        }
                        lastDictatedWords = emptyList()
                    }

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

    private val chatAppPackages = hashSetOf(
        "whatsapp",
        "telegram",
        "challegram",
        "instagram",
        "facebook.orca",
        "facebook.mlite",
        "discord",
        "slack",
        "thoughtcrime.securesms",
        "messaging",
        "mms",
        "twitter",
        "snapchat",
        "linkedin",
        "reddit",
        "viber",
        "skype",
        "teams",
        "line"
    )

    private fun isMultilineField(info: EditorInfo?): Boolean {
        if (info == null) return false
        val inputType = info.inputType
        val inputClass = inputType and EditorInfo.TYPE_MASK_CLASS
        if (inputClass != EditorInfo.TYPE_CLASS_TEXT) return false
        return (inputType and EditorInfo.TYPE_TEXT_FLAG_MULTI_LINE) != 0 ||
               (inputType and EditorInfo.TYPE_TEXT_FLAG_IME_MULTI_LINE) != 0
    }

    /**
     * Decides whether the Enter key should produce a newline or an IME action.
     * Checks the app-declared IME action FIRST (fastest, most reliable), then
     * falls back to the live Accessibility scan, then to the hardcoded app list.
     */
    private fun isSendButtonPresent(editorInfo: EditorInfo?): Boolean {
        val info = editorInfo ?: currentInputEditorInfo ?: return false
        val pkg = (info.packageName ?: lastActivePackageName).orEmpty().lowercase()
        val imeAction = info.imeOptions and EditorInfo.IME_MASK_ACTION

        // 1. App-declared SEND action means Enter acts as send
        if (imeAction == EditorInfo.IME_ACTION_SEND) return true

        // 2. NO_ENTER_ACTION flag → field wants newline, not send
        if ((info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) != 0) return false

        // 3. Search/Go fields should never show send behavior
        if (imeAction == EditorInfo.IME_ACTION_SEARCH || imeAction == EditorInfo.IME_ACTION_GO) return false

        // 4. Live Accessibility scan for on-screen send buttons
        if (KVIEAccessibilityService.hasSendButtonOnScreen()) return true

        // 5. Known chat apps always have an on-screen send button in their composer
        if (chatAppPackages.any { pkg.contains(it) }) return true

        // 6. Multiline fields (notes, comments, emails) have external submit/send
        if (isMultilineField(info)) return true

        return false
    }

    private fun updateEnterKeyActionVisual() {
        val editorInfo = currentInputEditorInfo ?: return
        if (!::keyEnter.isInitialized) return

        val sendPresent = isSendButtonPresent(editorInfo)
        val hasNoEnterAction = (editorInfo.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) != 0
        val imeAction = editorInfo.imeOptions and EditorInfo.IME_MASK_ACTION

        // Where an on-screen send button is present: show newline "↵"
        if (sendPresent || hasNoEnterAction) {
            keyEnter.text = "↵"
            keyEnter.textSize = 20f
            return
        }

        // Where an on-screen send button is NOT present: show action button (Send, Search, Go, Next, Done)
        when (imeAction) {
            EditorInfo.IME_ACTION_SEARCH -> {
                keyEnter.text = "🔍"
                keyEnter.textSize = 16f
            }
            EditorInfo.IME_ACTION_GO -> {
                keyEnter.text = "Go"
                keyEnter.textSize = 15f
            }
            EditorInfo.IME_ACTION_NEXT -> {
                keyEnter.text = "Next"
                keyEnter.textSize = 14f
            }
            EditorInfo.IME_ACTION_DONE -> {
                keyEnter.text = "✓"
                keyEnter.textSize = 18f
            }
            EditorInfo.IME_ACTION_SEND -> {
                keyEnter.text = "➤"
                keyEnter.textSize = 18f
            }
            else -> {
                keyEnter.text = "➤"
                keyEnter.textSize = 18f
            }
        }
    }

    private fun handleEnterKey() {
        val ic = currentInputConnection ?: return
        val editorInfo = currentInputEditorInfo

        if (editorInfo == null) {
            insertNewline()
            updateSuggestions()
            return
        }

        val action = resolveEnterAction(editorInfo)

        // Primary: try the action (send/search/go/etc.)
        val handled = ic.performEditorAction(action)
        if (handled) {
            updateSuggestions()
            return
        }

        // Fallback 1: try commitText for newline (works in WebViews, many custom EditTexts)
        val fallback = commitTextFallback(editorInfo, action)
        if (fallback) {
            updateSuggestions()
            return
        }

        // Fallback 2: raw key event (last resort)
        sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER)
        updateSuggestions()
    }

    /**
     * Determines the correct IME action for Enter based on EditorInfo + live app context.
     */
    private fun resolveEnterAction(editorInfo: EditorInfo): Int {
        val imeAction = editorInfo.imeOptions and EditorInfo.IME_MASK_ACTION

        // If the app explicitly declares SEND action, use it
        if (imeAction == EditorInfo.IME_ACTION_SEND) return EditorInfo.IME_ACTION_SEND

        // If NO_ENTER_ACTION flag is set, the field wants a newline
        if ((editorInfo.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) != 0) {
            return IME_ACTION_NEWLINE_FALLBACK
        }

        // Check if an on-screen send button is present → use newline
        if (isSendButtonPresent(editorInfo)) {
            return IME_ACTION_NEWLINE_FALLBACK
        }

        // No send button present: use whatever action the app declared,
        // defaulting to SEND if nothing was set
        return when (imeAction) {
            EditorInfo.IME_ACTION_SEARCH,
            EditorInfo.IME_ACTION_GO,
            EditorInfo.IME_ACTION_NEXT,
            EditorInfo.IME_ACTION_DONE,
            EditorInfo.IME_ACTION_SEND -> imeAction
            else -> EditorInfo.IME_ACTION_SEND
        }
    }

    /**
     * Attempts to commit newline or action text directly via commitText.
     * This is the most reliable method for WebViews, React Native, Flutter,
     * and custom EditText fields that don't handle performEditorAction well.
     */
    private fun commitTextFallback(editorInfo: EditorInfo, action: Int): Boolean {
        val ic = currentInputConnection ?: return false

        return when (action) {
            IME_ACTION_NEWLINE_FALLBACK -> {
                // Commit a literal newline character
                val inputType = editorInfo.inputType
                if ((inputType and EditorInfo.TYPE_MASK_CLASS) == EditorInfo.TYPE_NULL) {
                    // Non-text field: can't commit text, try key event
                    false
                } else {
                    ic.commitText("\n", 1)
                }
            }
            EditorInfo.IME_ACTION_SEND -> {
                // For single-line send fields, commit text doesn't make sense.
                // Only try for non-text types.
                val inputType = editorInfo.inputType
                if ((inputType and EditorInfo.TYPE_MASK_CLASS) == EditorInfo.TYPE_NULL) {
                    ic.commitText("\n", 1)
                } else {
                    false
                }
            }
            else -> {
                // For SEARCH, GO, NEXT, DONE — try commitText with a newline
                // Some apps (especially WebViews) handle this better than performEditorAction
                ic.commitText("\n", 1)
            }
        }
    }

    private fun insertNewline() {
        val ic = currentInputConnection ?: return
        val editorInfo = currentInputEditorInfo
        val inputType = editorInfo?.inputType ?: 0

        if ((inputType and EditorInfo.TYPE_MASK_CLASS) == EditorInfo.TYPE_NULL) {
            sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER)
            return
        }

        // Try \n first (most common)
        val success = ic.commitText("\n", 1)
        if (success) return

        // Fallback 1: try \r\n for apps that expect CR+LF (some editors, terminals)
        val success2 = ic.commitText("\r\n", 1)
        if (success2) return

        // Fallback 2: raw key event
        sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER)
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

    private fun triggerAIPolish(style: String = "clean") {
        val ic = currentInputConnection ?: return
        val textBefore = ic.getTextBeforeCursor(200, 0)?.toString() ?: ""
        if (textBefore.isBlank()) return

        scope.launch {
            try {
                val polished = AutoEditClient.refine(textBefore, this@KVIEInputMethodService)
                if (polished != null && polished.isNotBlank() && polished != textBefore) {
                    ic.deleteSurroundingText(textBefore.length, 0)
                    ic.commitText(polished, 1)
                    val targetPkg = currentInputEditorInfo?.packageName ?: lastActivePackageName ?: KVIEAccessibilityService.currentActivePackage
                    val targetApp = SessionManager.resolveAppName(this@KVIEInputMethodService, targetPkg)
                    val label = if (style == "clean") "AI Polish" else "$style Polish"
                    SessionManager.recordSession(this@KVIEInputMethodService, polished, "$targetApp ($label)")
                    updateSuggestions()
                }
            } catch (_: Exception) {}
        }
    }

    // ───────────── SPEECH DICTATION ENGINE ─────────────
    private fun startListening() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            val intent = Intent(this, SetupActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)
            return
        }

        destroySpeechRecognizer()

        isListening = true
        micButton.isSelected = true
        suggestionBar.visibility = View.GONE
        aiActionsBar.visibility = View.GONE
        statusText.visibility = View.VISIBLE
        statusText.text = "🎙️ Listening..."

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: android.os.Bundle?) {
                    statusText.text = "🎙️ Listening..."
                }

                override fun onBeginningOfSpeech() {
                    statusText.text = "🎙️ Dictating..."
                }

                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}

                override fun onEndOfSpeech() {
                    statusText.text = "✨ Processing..."
                }

                override fun onError(error: Int) {
                    stopListening()
                }

                override fun onResults(results: android.os.Bundle?) {
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if (!matches.isNullOrEmpty()) {
                        handleFinalTranscript(matches[0])
                    }
                    stopListening()
                }

                override fun onPartialResults(partialResults: android.os.Bundle?) {
                    val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    if (!matches.isNullOrEmpty()) {
                        statusText.text = matches[0]
                    }
                }

                override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
            })
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        speechRecognizer?.startListening(intent)
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
        isListening = false
        destroySpeechRecognizer()
        micButton.isSelected = false
        statusText.visibility = View.GONE
        suggestionBar.visibility = View.VISIBLE
        updateSuggestions()
    }

    private fun handleFinalTranscript(rawTranscript: String) {
        if (rawTranscript.isBlank()) return
        val ic = currentInputConnection ?: return

        // 1. Real-Time Voice Editing Command Interception
        val command = SmolLMEngine.parseVoiceCommand(rawTranscript)
        if (command != null) {
            performKeyHaptic()
            when (command.type) {
                SmolLMEngine.VoiceCommandType.DELETE_LAST_WORD -> {
                    val before = ic.getTextBeforeCursor(60, 0)?.toString() ?: ""
                    val trimmed = before.trimEnd()
                    val lastWord = trimmed.substringAfterLast(" ", "")
                    if (lastWord.isNotEmpty()) {
                        ic.deleteSurroundingText(before.length - trimmed.lastIndexOf(lastWord), 0)
                    } else if (before.isNotEmpty()) {
                        ic.deleteSurroundingText(before.length, 0)
                    }
                    updateSuggestions()
                    return
                }
                SmolLMEngine.VoiceCommandType.DELETE_LAST_SENTENCE -> {
                    val before = ic.getTextBeforeCursor(300, 0)?.toString() ?: ""
                    val idx = maxOf(before.lastIndexOf('.'), before.lastIndexOf('?'), before.lastIndexOf('!'))
                    if (idx != -1 && idx < before.length - 1) {
                        ic.deleteSurroundingText(before.length - (idx + 1), 0)
                    } else {
                        ic.deleteSurroundingText(before.length, 0)
                    }
                    updateSuggestions()
                    return
                }
                SmolLMEngine.VoiceCommandType.CLEAR_ALL -> {
                    val before = ic.getTextBeforeCursor(2000, 0)?.toString() ?: ""
                    ic.deleteSurroundingText(before.length, 0)
                    updateSuggestions()
                    return
                }
                SmolLMEngine.VoiceCommandType.NEW_LINE -> {
                    insertNewline()
                    updateSuggestions()
                    return
                }
                SmolLMEngine.VoiceCommandType.MAKE_FORMAL -> {
                    triggerAIPolish("formal")
                    return
                }
                SmolLMEngine.VoiceCommandType.MAKE_CASUAL -> {
                    triggerAIPolish("casual")
                    return
                }
            }
        }

        // 2. Normal Dictation Commit
        val cleanText = SmolLMEngine.stripFillersAndPunctuate(rawTranscript)
        if (cleanText.isBlank()) return

        val targetPkg = currentInputEditorInfo?.packageName 
            ?: lastActivePackageName 
            ?: KVIEAccessibilityService.currentActivePackage
        val targetApp = SessionManager.resolveAppName(this, targetPkg)
        val prefix = if (ic.getTextBeforeCursor(1, 0)?.endsWith(" ") == true || ic.getTextBeforeCursor(1, 0).isNullOrEmpty()) "" else " "
        ic.commitText(prefix + cleanText + " ", 1)
        SessionManager.recordSession(this, cleanText, targetApp)

        // Track voice dictation for Contextual Bandit self-learning
        val dictatedWords = cleanText.split(Regex("[^\\p{L}\\p{Nd}]+")).filter { it.isNotBlank() }
        lastDictatedWords = dictatedWords
        pendingVoiceValidationJob?.cancel()
        pendingVoiceValidationJob = scope.launch {
            delay(4500)
            if (lastDictatedWords.isNotEmpty()) {
                ContextualBanditEngine.rewardVoiceSentenceAccepted(
                    lastDictatedWords,
                    if (::userLexiconDb.isInitialized) userLexiconDb else null
                )
            }
        }

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
            adaptAppTone(pkg)
        }
        isShifted = false
        isCapsLock = false
        isSymbolsMode = false
        emojiDrawer.visibility = View.GONE
        clipboardDrawer.visibility = View.GONE
        aiActionsBar.visibility = View.GONE
        qwertyContainer.visibility = View.VISIBLE
        statusText.visibility = View.GONE
        suggestionBar.visibility = View.VISIBLE
        applyAccentTheme()
        populateKeys()
        updateSuggestions()
        updateEnterKeyActionVisual()
    }

    private fun adaptAppTone(packageName: String) {
        when {
            packageName.contains("whatsapp", ignoreCase = true) ||
            packageName.contains("instagram", ignoreCase = true) ||
            packageName.contains("telegram", ignoreCase = true) ||
            packageName.contains("snapchat", ignoreCase = true) -> {
                chipToneCasual.setTextColor(0xFFD7FB52.toInt())
                chipToneFormal.setTextColor(0xFF8E8E9E.toInt())
            }
            packageName.contains("gmail", ignoreCase = true) ||
            packageName.contains("outlook", ignoreCase = true) ||
            packageName.contains("linkedin", ignoreCase = true) ||
            packageName.contains("slack", ignoreCase = true) ||
            packageName.contains("teams", ignoreCase = true) -> {
                chipToneFormal.setTextColor(currentAccentColor)
                chipToneCasual.setTextColor(0xFF8E8E9E.toInt())
            }
            else -> {
                chipToneFormal.setTextColor(currentAccentColor)
                chipToneCasual.setTextColor(0xFFD7FB52.toInt())
            }
        }
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
        private const val IME_ACTION_NEWLINE_FALLBACK = -1

        fun commitFromExternal(text: String): Boolean {
            return instance?.directCommitText(text) ?: false
        }
    }
}
