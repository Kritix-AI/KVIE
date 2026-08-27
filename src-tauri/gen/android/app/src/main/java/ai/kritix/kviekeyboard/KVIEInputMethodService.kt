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
import android.text.TextWatcher
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.EditText
import android.widget.GridLayout
import android.widget.HorizontalScrollView
import android.widget.ImageButton
import android.widget.ImageView
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
 * 1. Full QWERTY with Number Row Toggle & Long-Press Alt-Symbols (q->1, w->2, a->@, etc.)
 * 2. Real-Time Autocorrect & Contextual Next-Word 3-Candidate Suggestion Bar (Case-Aware)
 * 3. Native Multi-Item Clipboard History Drawer
 * 4. Massive 500+ Emoji Drawer with Real-Time Search across 8 Categories
 * 5. Instant 1-Tap AI Voice Dictation with 6 Voice Editing Commands
 * 6. Quick AI Action Chips (Formal, Casual, Shorten, To English) & Per-App Tone Defaults
 * 7. Dual Tactile Haptic & Acoustic Mechanical Key Click Feedback
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

        currentActiveEmojiCategory = smileyEmojis

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
            btnNumberRowToggle.setTextColor(if (isNumberRowVisible) 0xFF00E5FF.toInt() else 0xFF8E8E9E.toInt())
        }

        view.findViewById<ImageButton>(R.id.switchKeyboardButton)?.setOnClickListener {
            performKeyHaptic()
            val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager
            imm?.showInputMethodPicker()
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
            currentInputConnection?.commitText(" ", 1)
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
        if (isSymbolsMode) {
            keyShift.text = if (isSymbolsSecondaryPage) "1/2" else "2/2"
            keyShift.setTextColor(0xFF00E5FF.toInt())
        } else {
            keyShift.text = "⇧"
            when {
                isCapsLock -> keyShift.setTextColor(0xFF00E5FF.toInt())
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
        val textBefore = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
        val isSentenceStart = checkIsSentenceStart(textBefore.dropLastWhile { !it.isWhitespace() })

        val hasTrailingSpace = textBefore.endsWith(" ") || textBefore.isEmpty()
        val currentWord = if (hasTrailingSpace) "" else textBefore.substringAfterLast(" ", textBefore).trim()

        if (currentWord.isEmpty()) {
            val prevWord = textBefore.trimEnd().substringAfterLast(" ", "").lowercase()
            val nextWordPredictions = bigramContext[prevWord]

            if (!nextWordPredictions.isNullOrEmpty()) {
                suggestion1.text = formatSuggestion(nextWordPredictions[0], "", isSentenceStart)
                suggestion2.text = formatSuggestion(nextWordPredictions.getOrElse(1) { "the" }, "", isSentenceStart)
                suggestion3.text = formatSuggestion(nextWordPredictions.getOrElse(2) { "I" }, "", isSentenceStart)
            } else {
                if (isSentenceStart) {
                    suggestion1.text = "The"
                    suggestion2.text = "I"
                    suggestion3.text = "How"
                } else {
                    suggestion1.text = "the"
                    suggestion2.text = "and"
                    suggestion3.text = "to"
                }
            }
            return
        }

        val lower = currentWord.lowercase()
        val correction = grammarCorrections[lower]

        if (correction != null) {
            val formatted = formatSuggestion(correction, currentWord, isSentenceStart)
            suggestion1.text = formatted
            suggestion2.text = currentWord
            val matches = commonWords.filter { it.startsWith(lower, ignoreCase = true) && !it.equals(correction, ignoreCase = true) }
            suggestion3.text = matches.firstOrNull()?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: "..."
            return
        }

        val matches = commonWords.filter { it.startsWith(lower, ignoreCase = true) }
        val c1 = matches.getOrNull(0)?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: currentWord
        val c2 = if (matches.size > 1) formatSuggestion(matches[1], currentWord, isSentenceStart) else currentWord
        val c3 = matches.getOrNull(2)?.let { formatSuggestion(it, currentWord, isSentenceStart) } ?: "..."

        suggestion1.text = c1
        suggestion2.text = c2
        suggestion3.text = c3
    }

    private fun applySuggestion(candidate: String) {
        if (candidate.isBlank() || candidate == "...") return
        val ic = currentInputConnection ?: return
        performKeyHaptic()

        val textBefore = ic.getTextBeforeCursor(60, 0)?.toString().orEmpty()
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
                    ic.commitText("\n", 1)
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
        populateKeys()
        updateSuggestions()
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
                chipToneFormal.setTextColor(0xFF00E5FF.toInt())
                chipToneCasual.setTextColor(0xFF8E8E9E.toInt())
            }
            else -> {
                chipToneFormal.setTextColor(0xFF00E5FF.toInt())
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

        fun commitFromExternal(text: String): Boolean {
            return instance?.directCommitText(text) ?: false
        }
    }
}
