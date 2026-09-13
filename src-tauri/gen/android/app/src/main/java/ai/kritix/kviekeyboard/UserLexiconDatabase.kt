package ai.kritix.kviekeyboard

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap

/**
 * On-Device Dynamic User Lexicon, Transitions & Autocorrect Suppression Database.
 * Backed by native Android SQLite with a thread-safe, 0ms latency in-memory cache.
 */
class UserLexiconDatabase private constructor(context: Context) :
    SQLiteOpenHelper(context.applicationContext, DATABASE_NAME, null, DATABASE_VERSION) {

    private val dbScope = CoroutineScope(Dispatchers.IO)

    // In-memory cache for ultra-fast <0.01ms lookups on every keystroke
    private val frequentWordsCache = ConcurrentHashMap<String, Int>()
    private val suppressedCorrectionsCache = Collections.synchronizedSet(HashSet<String>())
    private val transitionCache = ConcurrentHashMap<String, ConcurrentHashMap<String, Int>>()
    private val banditScoresCache = ConcurrentHashMap<String, ConcurrentHashMap<String, Float>>()

    init {
        loadCacheFromDb()
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS user_lexicon (
                word TEXT PRIMARY KEY,
                frequency INTEGER NOT NULL DEFAULT 1,
                last_used INTEGER NOT NULL
            );
            """.trimIndent()
        )

        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS suppressed_corrections (
                original_word TEXT NOT NULL,
                corrected_word TEXT NOT NULL,
                PRIMARY KEY (original_word, corrected_word)
            );
            """.trimIndent()
        )

        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS user_transitions (
                prev_word TEXT NOT NULL,
                next_word TEXT NOT NULL,
                frequency INTEGER NOT NULL DEFAULT 1,
                last_used INTEGER NOT NULL,
                PRIMARY KEY (prev_word, next_word)
            );
            """.trimIndent()
        )

        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS contextual_bandit_scores (
                context_key TEXT NOT NULL,
                candidate TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.0,
                last_updated INTEGER NOT NULL,
                PRIMARY KEY (context_key, candidate)
            );
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS user_transitions (
                    prev_word TEXT NOT NULL,
                    next_word TEXT NOT NULL,
                    frequency INTEGER NOT NULL DEFAULT 1,
                    last_used INTEGER NOT NULL,
                    PRIMARY KEY (prev_word, next_word)
                );
                """.trimIndent()
            )
        }
        if (oldVersion < 3) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS contextual_bandit_scores (
                    context_key TEXT NOT NULL,
                    candidate TEXT NOT NULL,
                    score REAL NOT NULL DEFAULT 0.0,
                    last_updated INTEGER NOT NULL,
                    PRIMARY KEY (context_key, candidate)
                );
                """.trimIndent()
            )
        }
    }

    private fun loadCacheFromDb() {
        dbScope.launch {
            try {
                val db = readableDatabase

                // 1. Load words with frequency >= 2 into in-memory cache
                val wordCursor = db.query(
                    "user_lexicon",
                    arrayOf("word", "frequency"),
                    "frequency >= 2",
                    null,
                    null,
                    null,
                    "frequency DESC",
                    "1000"
                )
                wordCursor.use { cursor ->
                    val wordIdx = cursor.getColumnIndexOrThrow("word")
                    val freqIdx = cursor.getColumnIndexOrThrow("frequency")
                    while (cursor.moveToNext()) {
                        val w = cursor.getString(wordIdx)
                        val f = cursor.getInt(freqIdx)
                        frequentWordsCache[w] = f
                    }
                }

                // 2. Load suppressed corrections
                val supCursor = db.query(
                    "suppressed_corrections",
                    arrayOf("original_word", "corrected_word"),
                    null,
                    null,
                    null,
                    null,
                    null,
                    "500"
                )
                supCursor.use { cursor ->
                    val origIdx = cursor.getColumnIndexOrThrow("original_word")
                    val corrIdx = cursor.getColumnIndexOrThrow("corrected_word")
                    while (cursor.moveToNext()) {
                        val orig = cursor.getString(origIdx)
                        val corr = cursor.getString(corrIdx)
                        suppressedCorrectionsCache.add(buildKey(orig, corr))
                    }
                }

                // 3. Load user transitions
                val transCursor = db.query(
                    "user_transitions",
                    arrayOf("prev_word", "next_word", "frequency"),
                    null,
                    null,
                    null,
                    null,
                    "frequency DESC",
                    "1000"
                )
                transCursor.use { cursor ->
                    val pIdx = cursor.getColumnIndexOrThrow("prev_word")
                    val nIdx = cursor.getColumnIndexOrThrow("next_word")
                    val fIdx = cursor.getColumnIndexOrThrow("frequency")
                    while (cursor.moveToNext()) {
                        val p = cursor.getString(pIdx)
                        val n = cursor.getString(nIdx)
                        val f = cursor.getInt(fIdx)
                        transitionCache.computeIfAbsent(p) { ConcurrentHashMap() }[n] = f
                    }
                }

                // 4. Load contextual bandit scores
                val banditCursor = db.query(
                    "contextual_bandit_scores",
                    arrayOf("context_key", "candidate", "score"),
                    null,
                    null,
                    null,
                    null,
                    "last_updated DESC",
                    "2000"
                )
                banditCursor.use { cursor ->
                    val kIdx = cursor.getColumnIndexOrThrow("context_key")
                    val cIdx = cursor.getColumnIndexOrThrow("candidate")
                    val sIdx = cursor.getColumnIndexOrThrow("score")
                    while (cursor.moveToNext()) {
                        val k = cursor.getString(kIdx)
                        val c = cursor.getString(cIdx)
                        val s = cursor.getFloat(sIdx)
                        banditScoresCache.computeIfAbsent(k) { ConcurrentHashMap() }[c] = s
                    }
                }
            } catch (_: Exception) {}
        }
    }

    /**
     * Records a word typed by the user.
     * Increments its usage frequency.
     * Once frequency reaches >= 2, it is promoted to the active candidate pool.
     */
    fun recordWordTyped(rawWord: String) {
        val word = rawWord.trim().lowercase()
        if (word.length < 2 || word.length > 35) return
        if (!word.all { it.isLetter() || it == '\'' || it == '-' }) return

        val currentCount = frequentWordsCache.getOrDefault(word, 1) + 1
        frequentWordsCache[word] = currentCount

        dbScope.launch {
            try {
                val db = writableDatabase
                val now = System.currentTimeMillis()
                val cv = ContentValues().apply {
                    put("word", word)
                    put("frequency", currentCount)
                    put("last_used", now)
                }
                db.insertWithOnConflict("user_lexicon", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            } catch (_: Exception) {}
        }
    }

    /**
     * Checks if a word is recognized in the personal lexicon with frequency >= 2.
     */
    fun isPersonalWord(word: String): Boolean {
        val count = frequentWordsCache[word.lowercase().trim()] ?: return false
        return count >= 2
    }

    /**
     * Gets matching words from the user's personal lexicon matching the prefix,
     * sorted by frequency descending.
     */
    fun getMatchingFrequentWords(prefix: String, limit: Int = 3): List<String> {
        if (prefix.isBlank()) return emptyList()
        val lowerPrefix = prefix.lowercase().trim()

        return frequentWordsCache.entries
            .asSequence()
            .filter { it.key.startsWith(lowerPrefix) && it.value >= 2 }
            .sortedByDescending { it.value }
            .map { it.key }
            .take(limit)
            .toList()
    }

    /**
     * Suppresses an autocorrect pair permanently because the user hit Undo/Backspace.
     */
    fun suppressCorrection(originalWord: String, correctedWord: String) {
        val orig = originalWord.trim().lowercase()
        val corr = correctedWord.trim().lowercase()
        if (orig.isBlank() || corr.isBlank() || orig == corr) return

        suppressedCorrectionsCache.add(buildKey(orig, corr))

        dbScope.launch {
            try {
                val db = writableDatabase
                val cv = ContentValues().apply {
                    put("original_word", orig)
                    put("corrected_word", corr)
                }
                db.insertWithOnConflict("suppressed_corrections", null, cv, SQLiteDatabase.CONFLICT_IGNORE)
            } catch (_: Exception) {}
        }
    }

    /**
     * Checks if the user previously rejected this exact correction via Backspace.
     */
    fun isCorrectionSuppressed(originalWord: String, correctedWord: String): Boolean {
        val orig = originalWord.trim().lowercase()
        val corr = correctedWord.trim().lowercase()
        return suppressedCorrectionsCache.contains(buildKey(orig, corr))
    }

    /**
     * Records a word-pair transition typed by the user (prevWord -> nextWord).
     */
    fun recordTransition(prevRaw: String, nextRaw: String) {
        val prev = prevRaw.trim().lowercase()
        val next = nextRaw.trim().lowercase()
        if (prev.length < 2 || next.length < 2) return
        if (!prev.all { it.isLetter() || it == '\'' } || !next.all { it.isLetter() || it == '\'' }) return

        val innerMap = transitionCache.computeIfAbsent(prev) { ConcurrentHashMap() }
        val currentCount = innerMap.getOrDefault(next, 0) + 1
        innerMap[next] = currentCount

        dbScope.launch {
            try {
                val db = writableDatabase
                val cv = ContentValues().apply {
                    put("prev_word", prev)
                    put("next_word", next)
                    put("frequency", currentCount)
                    put("last_used", System.currentTimeMillis())
                }
                db.insertWithOnConflict("user_transitions", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            } catch (_: Exception) {}
        }
    }

    /**
     * Returns learned next words for a given previous word, sorted by frequency descending.
     */
    fun getLearnedNextWords(prevWord: String, limit: Int = 3): List<String> {
        val prev = prevWord.trim().lowercase()
        val innerMap = transitionCache[prev] ?: return emptyList()

        return innerMap.entries
            .asSequence()
            .sortedByDescending { it.value }
            .map { it.key }
            .take(limit)
            .toList()
    }

    /**
     * Updates bandit score for (contextKey, candidate) using Exponential Moving Average (EMA).
     * newScore = currentScore * 0.85 + signal * 0.15, clamped in [-1.0, 1.0].
     */
    fun recordBanditReward(contextKey: String, rawCandidate: String, signal: Float) {
        val candidate = rawCandidate.trim().lowercase()
        val key = contextKey.trim().lowercase()
        if (key.isBlank() || candidate.isBlank()) return

        val innerMap = banditScoresCache.computeIfAbsent(key) { ConcurrentHashMap() }
        val currentScore = innerMap.getOrDefault(candidate, 0.0f)
        val updatedScore = (currentScore * 0.85f + signal * 0.15f).coerceIn(-1.0f, 1.0f)
        innerMap[candidate] = updatedScore

        dbScope.launch {
            try {
                val db = writableDatabase
                val now = System.currentTimeMillis()
                val cv = ContentValues().apply {
                    put("context_key", key)
                    put("candidate", candidate)
                    put("score", updatedScore)
                    put("last_updated", now)
                }
                db.insertWithOnConflict("contextual_bandit_scores", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
            } catch (_: Exception) {}
        }
    }

    /**
     * Retrieves the contextual bandit score for a candidate in a given context.
     * Returns 0.0f if not yet learned.
     */
    fun getBanditScore(contextKey: String, rawCandidate: String): Float {
        val candidate = rawCandidate.trim().lowercase()
        val key = contextKey.trim().lowercase()
        return banditScoresCache[key]?.get(candidate) ?: 0.0f
    }

    /**
     * Retrieves all positively learned candidates for a context, sorted by score descending.
     */
    fun getTopBanditCandidates(contextKey: String, limit: Int = 3): List<Pair<String, Float>> {
        val key = contextKey.trim().lowercase()
        val innerMap = banditScoresCache[key] ?: return emptyList()

        return innerMap.entries
            .asSequence()
            .filter { it.value > 0.05f }
            .sortedByDescending { it.value }
            .map { Pair(it.key, it.value) }
            .take(limit)
            .toList()
    }

    private fun buildKey(original: String, corrected: String): String = "$original:$corrected"

    companion object {
        private const val DATABASE_NAME = "kvie_user_lexicon.db"
        private const val DATABASE_VERSION = 3

        @Volatile
        private var INSTANCE: UserLexiconDatabase? = null

        fun getInstance(context: Context): UserLexiconDatabase {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: UserLexiconDatabase(context).also { INSTANCE = it }
            }
        }
    }
}
