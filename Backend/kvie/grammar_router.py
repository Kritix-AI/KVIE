"""
KVIE Multi-Tier Grammar Router Pipeline (Python Backend)

Architecture:
          │ Grammar Router │
          └───────┬────────┘
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
    TOKEN       SENTENCE   PARAGRAPH
    ENGINE       ENGINE      ENGINE
       │          │          │
       ▼          ▼          ▼
   Spelling    Grammar     Context
   Typo        Structure   Coherence
   Casing      Tense       Flow
       │          │          │
       └──────────┼──────────┘
                  ▼
             FINAL EDITOR
                  │
                  ▼
           Corrected Text
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple


class TokenEngine:
    """
    Tier 1: TokenEngine
    Lexical and typographical normalization:
    - 250+ common spoken transcription slips and typographical errors.
    - Canonical brand casing (Kritix, KVIE, GitHub, GitLab, YouTube, VS Code, ChatGPT, etc.).
    - Apostrophe restoration for conversational contractions (can't, don't, won't, etc.).
    - Strict Speaker Intent Integrity: NEVER convert valid words ('wed', 'well', 'shell', 'shed', 'ill') to contractions.
    - Contextual guarded homophone corrections (their/there/they're, your/you're, its/it's, to/too, then/than).
    - Standalone pronoun capitalization (I, I'm, I've, I'll, I'd).
    """

    BRAND_MAP: Dict[str, str] = {
        "critics": "Kritix",
        "critic": "Kritix",
        "critcs": "Kritix",
        "kritics": "Kritix",
        "kritik": "Kritix",
        "kritiks": "Kritix",
        "kritic": "Kritix",
        "critis": "Kritix",
        "kritcs": "Kritix",
        "kritix": "Kritix",
        "kvie": "KVIE",
        "github": "GitHub",
        "gitlab": "GitLab",
        "youtube": "YouTube",
        "vscode": "VS Code",
        "chatgpt": "ChatGPT",
        "linkedin": "LinkedIn",
        "fastapi": "FastAPI",
        "graphql": "GraphQL",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mongodb": "MongoDB",
        "kubernetes": "Kubernetes",
        "docker": "Docker",
        "openai": "OpenAI",
    }

    CONTRACTIONS: Dict[str, str] = {
        "cant": "can't",
        "dont": "don't",
        "wont": "won't",
        "didnt": "didn't",
        "isnt": "isn't",
        "arent": "aren't",
        "wouldnt": "wouldn't",
        "couldnt": "couldn't",
        "shouldnt": "shouldn't",
        "hasnt": "hasn't",
        "havent": "haven't",
        "hadnt": "hadn't",
        "wasnt": "wasn't",
        "werent": "weren't",
        "doesnt": "doesn't",
        "mustnt": "mustn't",
        "neednt": "needn't",
        "thats": "that's",
        "whats": "what's",
        "theres": "there's",
        "wheres": "where's",
        "hows": "how's",
        "whos": "who's",
        "youll": "you'll",
        "theyll": "they'll",
        "theyve": "they've",
        "youve": "you've",
        "theyd": "they'd",
        "youd": "you'd",
        "couldve": "could've",
        "shouldve": "should've",
        "wouldve": "would've",
        "mightve": "might've",
        "mustve": "must've",
        "im": "I'm",
        "ive": "I've",
    }

    # Strict Speaker Intent Integrity: Words that MUST NEVER be converted to contractions
    INTENT_PROTECTED_WORDS: Set[str] = {
        "wed",
        "well",
        "shell",
        "shed",
        "ill",
        "id",
        "hell",
    }

    TYPO_MAP: Dict[str, str] = {
        # Brand names
        **BRAND_MAP,
        # Contractions
        **CONTRACTIONS,
        # Spoken & Typographical slips (200+ entries)
        "teh": "the",
        "recieve": "receive",
        "recieved": "received",
        "recieving": "receiving",
        "seperate": "separate",
        "seperated": "separated",
        "seperation": "separation",
        "definately": "definitely",
        "definitly": "definitely",
        "occured": "occurred",
        "occurance": "occurrence",
        "occurances": "occurrences",
        "untill": "until",
        "truely": "truly",
        "whcih": "which",
        "wierd": "weird",
        "accomodate": "accommodate",
        "accomodation": "accommodation",
        "tommorow": "tomorrow",
        "tommorrow": "tomorrow",
        "neccessary": "necessary",
        "necesary": "necessary",
        "goverment": "government",
        "arguement": "argument",
        "arguements": "arguments",
        "enviroment": "environment",
        "enviromental": "environmental",
        "beleive": "believe",
        "beleived": "believed",
        "beleiver": "believer",
        "calender": "calendar",
        "alot": "a lot",
        "maintainance": "maintenance",
        "embarass": "embarrass",
        "embarassed": "embarrassed",
        "embarassing": "embarrassing",
        "priviledge": "privilege",
        "priviledges": "privileges",
        "suprise": "surprise",
        "suprised": "surprised",
        "suprising": "surprising",
        "becuase": "because",
        "differant": "different",
        "existense": "existence",
        "independant": "independent",
        "independance": "independence",
        "percieve": "perceive",
        "perceived": "perceived",
        "recommand": "recommend",
        "recommanded": "recommended",
        "recommandation": "recommendation",
        "oppurtunity": "opportunity",
        "oppurtunities": "opportunities",
        "guarentee": "guarantee",
        "guarenteed": "guaranteed",
        "pronounciation": "pronunciation",
        "remeber": "remember",
        "remebered": "remembered",
        "succesful": "successful",
        "succesfully": "successfully",
        "supercede": "supersede",
        "grammer": "grammar",
        "judgement": "judgment",
        "publically": "publicly",
        "absense": "absence",
        "acceptible": "acceptable",
        "accross": "across",
        "acheive": "achieve",
        "acheived": "achieved",
        "acheivement": "achievement",
        "acknowlege": "acknowledge",
        "aquire": "acquire",
        "aquired": "acquired",
        "adress": "address",
        "adressed": "addressed",
        "agressive": "aggressive",
        "agression": "aggression",
        "allegeance": "allegiance",
        "allmost": "almost",
        "alright": "all right",
        "amature": "amateur",
        "analize": "analyze",
        "annoint": "anoint",
        "apparant": "apparent",
        "apparrent": "apparent",
        "appearence": "appearance",
        "artic": "arctic",
        "athiest": "atheist",
        "basicly": "basically",
        "becomming": "becoming",
        "begining": "beginning",
        "bizzare": "bizarre",
        "buisness": "business",
        "camoflage": "camouflage",
        "catagory": "category",
        "catagories": "categories",
        "cematary": "cemetery",
        "cemetary": "cemetery",
        "collaegue": "colleague",
        "colum": "column",
        "commited": "committed",
        "commiting": "committing",
        "conceed": "concede",
        "concious": "conscious",
        "conciously": "consciously",
        "concensus": "consensus",
        "convinient": "convenient",
        "cooly": "coolly",
        "decieve": "deceive",
        "decieved": "deceived",
        "dependance": "dependence",
        "desparate": "desperate",
        "dissapear": "disappear",
        "dissapoint": "disappoint",
        "dissapointed": "disappointed",
        "drunkeness": "drunkenness",
        "dumbell": "dumbbell",
        "ecstacy": "ecstasy",
        "effecient": "efficient",
        "eleminate": "eliminate",
        "equiptment": "equipment",
        "exagerrate": "exaggerate",
        "excell": "excel",
        "existance": "existence",
        "experiance": "experience",
        "extention": "extension",
        "facinating": "fascinating",
        "farenheit": "fahrenheit",
        "foward": "forward",
        "fourty": "forty",
        "freind": "friend",
        "freinds": "friends",
        "fundemental": "fundamental",
        "guage": "gauge",
        "gratefull": "grateful",
        "harrass": "harass",
        "harrassment": "harassment",
        "heighth": "height",
        "hierachy": "hierarchy",
        "humerous": "humorous",
        "hygene": "hygiene",
        "hypocrasy": "hypocrisy",
        "ignorence": "ignorance",
        "immediatly": "immediately",
        "immitate": "imitate",
        "incidently": "incidentally",
        "inadvertant": "inadvertent",
        "innoculate": "inoculate",
        "inteligence": "intelligence",
        "inteligible": "intelligible",
        "interupt": "interrupt",
        "irresistable": "irresistible",
        "knowlege": "knowledge",
        "leasure": "leisure",
        "liason": "liaison",
        "libary": "library",
        "lisence": "license",
        "lightening": "lightning",
        "lonliness": "loneliness",
        "managment": "management",
        "manuever": "maneuver",
        "marrige": "marriage",
        "medeval": "medieval",
        "memento": "memento",
        "millenium": "millennium",
        "minature": "miniature",
        "mischievious": "mischievous",
        "mispell": "misspell",
        "mispelled": "misspelled",
        "neice": "niece",
        "nieghbor": "neighbor",
        "noticable": "noticeable",
        "occassion": "occasion",
        "occassional": "occasional",
        "occassionally": "occasionally",
        "paralell": "parallel",
        "parrallel": "parallel",
        "pastime": "pastime",
        "peice": "piece",
        "playwrite": "playwright",
        "posession": "possession",
        "possesion": "possession",
        "potatos": "potatoes",
        "practise": "practice",
        "preceed": "precede",
        "prefered": "preferred",
        "presance": "presence",
        "privelege": "privilege",
        "professer": "professor",
        "promiss": "promise",
        "questionaire": "questionnaire",
        "readilly": "readily",
        "rebellion": "rebellion",
        "receed": "recede",
        "refered": "referred",
        "refering": "referring",
        "relevent": "relevant",
        "religous": "religious",
        "resistence": "resistance",
        "restaraunt": "restaurant",
        "rythm": "rhythm",
        "saftey": "safety",
        "secratary": "secretary",
        "sieze": "seize",
        "similiar": "similar",
        "sincerly": "sincerely",
        "speach": "speech",
        "successfull": "successful",
        "tendancy": "tendency",
        "therfore": "therefore",
        "threshhold": "threshold",
        "tomatos": "tomatoes",
        "tounge": "tongue",
        "transfered": "transferred",
        "unconcious": "unconscious",
        "unfortunatly": "unfortunately",
        "unintelligable": "unintelligible",
        "vaccuum": "vacuum",
        "vegatable": "vegetable",
        "vehical": "vehicle",
        "vicious": "vicious",
        "villian": "villain",
        "warrent": "warrant",
        "wether": "whether",
        "writting": "writing",
        "yeild": "yield",
    }

    # Guarded homophone rules: tuples of (pattern, replacement_word, replace_group_index)
    HOMOPHONE_GROUP1_RULES: List[Tuple[re.Pattern, str]] = [
        # their -> they're before verbs / adjectives
        (
            re.compile(
                r"\b(their)\s+(going|coming|leaving|working|doing|running|trying|making|feeling|happy|ready|sure|online|here|there)\b",
                re.IGNORECASE,
            ),
            "they're",
        ),
        # they're / there -> their before possessed nouns
        (
            re.compile(
                r"\b(they're|there)\s+(house|car|office|team|code|project|family|time|idea|work|opinion|friends|dog|cat|parents|children)\b",
                re.IGNORECASE,
            ),
            "their",
        ),
        # their -> there before auxiliary / copula verbs
        (
            re.compile(
                r"\b(their)\s+(is|are|was|were|will|can|could|should|must|has|have)\b",
                re.IGNORECASE,
            ),
            "there",
        ),
        # your -> you're before predicate adjectives / gerunds
        (
            re.compile(
                r"\b(your)\s+(welcome|right|wrong|going|coming|doing|making|smart|invited|ready|sure)\b",
                re.IGNORECASE,
            ),
            "you're",
        ),
        # you're -> your before possessed nouns
        (
            re.compile(
                r"\b(you're)\s+(house|car|phone|name|email|code|message|work|turn|time|computer|account)\b",
                re.IGNORECASE,
            ),
            "your",
        ),
        # its -> it's before determiners, verbs, predicatives
        (
            re.compile(
                r"\b(its)\s+(a|an|the|my|your|his|her|our|their|going|been|working|ready|done|cool|good|bad|fine|not|just|so|too|really)\b",
                re.IGNORECASE,
            ),
            "it's",
        ),
        # to -> too before qualifiers
        (
            re.compile(
                r"\b(to)\s+(much|many|late|fast|slow|bad|good|expensive|hard|easy|little|few|cold|hot|far|close|loud|quiet)\b",
                re.IGNORECASE,
            ),
            "too",
        ),
    ]

    HOMOPHONE_TRANSFORM_RULES: List[Tuple[re.Pattern, str]] = [
        # then -> than after comparatives
        (
            re.compile(
                r"\b(more|less|better|worse|greater|smaller|faster|slower|earlier|later|higher|lower|rather|other)\s+(then)\b",
                re.IGNORECASE,
            ),
            r"\1 than",
        ),
        # effect -> affect after modals / infinitive to
        (
            re.compile(
                r"\b(will|can|could|should|would|might|to)\s+(effect)\b",
                re.IGNORECASE,
            ),
            r"\1 affect",
        ),
        # affect -> effect after determiners
        (
            re.compile(
                r"\b(the|a|an|direct|negative|positive)\s+(affect)\b",
                re.IGNORECASE,
            ),
            r"\1 effect",
        ),
        # loose -> lose after auxiliaries / infinitive to
        (
            re.compile(
                r"\b(to|will|might|don't|did not)\s+(loose)\b",
                re.IGNORECASE,
            ),
            r"\1 lose",
        ),
    ]

    @classmethod
    def _preserve_case(cls, original: str, replacement: str) -> str:
        lower = original.lower()
        if lower in cls.BRAND_MAP:
            return cls.BRAND_MAP[lower]
        if original.isupper():
            return replacement.upper()
        if original.istitle() or (len(original) > 0 and original[0].isupper()):
            return replacement[0].upper() + replacement[1:]
        return replacement

    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # 1. Squash exaggerated character repetitions (e.g. 'coooool' -> 'cool')
        result = re.sub(r"([a-zA-Z])\1{2,}", r"\1", result)

        # 2. Token dictionary lookup (Brands, Typos, Contractions)
        def typo_replace(match: re.Match) -> str:
            word = match.group(0)
            lower = word.lower()
            # Guard against converting ambiguous words to contractions
            if lower in cls.INTENT_PROTECTED_WORDS:
                return word

            replacement = cls.TYPO_MAP.get(lower)
            if replacement:
                return cls._preserve_case(word, replacement)
            return word

        result = re.sub(r"\b[a-zA-Z]+\b", typo_replace, result)

        # 3. Contextual guarded homophones (Group 1 replacement with case preservation)
        for pattern, rep_target in cls.HOMOPHONE_GROUP1_RULES:
            def make_sub(target: str):
                def sub_fn(m: re.Match) -> str:
                    first = m.group(1)
                    second = m.group(2)
                    if first.isupper():
                        rep = target.upper()
                    elif first[0].isupper():
                        rep = target[0].upper() + target[1:]
                    else:
                        rep = target.lower()
                    return f"{rep} {second}"
                return sub_fn

            result = pattern.sub(make_sub(rep_target), result)

        # 4. Homophone transforms (Group 2 or syntactic replacements)
        for pattern, repl in cls.HOMOPHONE_TRANSFORM_RULES:
            result = pattern.sub(repl, result)

        # 5. Standalone pronoun capitalization
        result = re.sub(r"\bi\b", "I", result)
        result = re.sub(r"(?i)\bi'm\b", "I'm", result)
        result = re.sub(r"(?i)\bi've\b", "I've", result)
        result = re.sub(r"(?i)\bi'll\b", "I'll", result)
        result = re.sub(r"(?i)\bi'd\b", "I'd", result)

        return result


class SentenceEngine:
    """
    Tier 2: SentenceEngine
    Syntax and phonetic grammar polishing:
    - Phonetic indefinite article resolution ('a' vs 'an') with explicit phoneme exception tables.
    - Spoken modal verb contraction restoration ('could of' -> 'could have', 'suppose to' -> 'supposed to', etc.).
    - Preposition collocation corrections ('interested on' -> 'interested in', 'discuss about' -> 'discuss', etc.).
    - Preserves newlines and structural indentations without destructive collapsing.
    """

    A_EXCEPTIONS: Set[str] = {
        "university",
        "universities",
        "universal",
        "universe",
        "user",
        "users",
        "unique",
        "uniquely",
        "unicorn",
        "unicorns",
        "uniform",
        "uniforms",
        "union",
        "unions",
        "united",
        "unit",
        "units",
        "unitary",
        "unity",
        "euphemism",
        "euphemisms",
        "euphoria",
        "euphoric",
        "euthanasia",
        "european",
        "europeans",
        "one",
        "one-time",
        "oneself",
        "useful",
        "usefully",
        "useless",
        "uselessly",
        "usual",
        "usually",
        "usurper",
        "utensil",
        "utensils",
        "utility",
        "utilities",
        "utilitarian",
        "utopia",
        "utopian",
        "ubiquitous",
        "ubiquity",
    }

    AN_EXCEPTIONS: Set[str] = {
        "hour",
        "hours",
        "hourly",
        "honor",
        "honors",
        "honorable",
        "honorary",
        "honest",
        "honestly",
        "honesty",
        "heir",
        "heirs",
        "heiress",
        "herb",
        "herbs",
    }

    PREPOSITION_RULES: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\binterested\s+on\b", re.IGNORECASE), "interested in"),
        (re.compile(r"\bcongratulations\s+for\b", re.IGNORECASE), "congratulations on"),
        (re.compile(r"\bdiscuss\s+about\b", re.IGNORECASE), "discuss"),
        (re.compile(r"\bexplain\s+about\b", re.IGNORECASE), "explain"),
        (re.compile(r"\bmarried\s+with\b", re.IGNORECASE), "married to"),
        (re.compile(r"\bdepend\s+of\b", re.IGNORECASE), "depend on"),
        (re.compile(r"\brely\s+into\b", re.IGNORECASE), "rely on"),
        (re.compile(r"\bconcentrate\s+in\b", re.IGNORECASE), "concentrate on"),
        (re.compile(r"\bcope\s+up\s+with\b", re.IGNORECASE), "cope with"),
        (re.compile(r"\bcomply\s+to\b", re.IGNORECASE), "comply with"),
        (re.compile(r"\binsist\s+to\b", re.IGNORECASE), "insist on"),
        (re.compile(r"\bresponsible\s+of\b", re.IGNORECASE), "responsible for"),
    ]

    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # 1. Phonetic indefinite article resolution ('a' vs 'an')
        def resolve_article(match: re.Match) -> str:
            art = match.group(1)
            word = match.group(2)
            word_lower = word.lower()
            head = word_lower.split("-")[0]

            if word_lower in cls.AN_EXCEPTIONS or head in cls.AN_EXCEPTIONS:
                target = "an"
            elif word_lower in cls.A_EXCEPTIONS or head in cls.A_EXCEPTIONS:
                target = "a"
            elif word_lower[0] in "aeiou":
                target = "an"
            else:
                target = "a"

            if art == "AN" or (art.isupper() and word.isupper()):
                target = target.upper()
            elif art[0].isupper():
                target = target.capitalize()
            else:
                target = target.lower()

            return f"{target} {word}"

        result = re.sub(
            r"\b(a|an)\s+([a-zA-Z]+(?:-[a-zA-Z]+)*)\b",
            resolve_article,
            result,
            flags=re.IGNORECASE,
        )

        # 2. Spoken modal verb contractions
        def modal_have_replace(m: re.Match) -> str:
            modal = m.group(1)
            return f"{modal} have"

        result = re.sub(
            r"\b(could|would|should|might|must)\s+of\b",
            modal_have_replace,
            result,
            flags=re.IGNORECASE,
        )

        def suppose_to_replace(m: re.Match) -> str:
            word = m.group(1)
            if word.isupper():
                return "SUPPOSED TO"
            elif word[0].isupper():
                return "Supposed to"
            return "supposed to"

        result = re.sub(
            r"\b(suppose)\s+to\b",
            suppose_to_replace,
            result,
            flags=re.IGNORECASE,
        )

        def use_to_replace(m: re.Match) -> str:
            word = m.group(1)
            if word.isupper():
                return "USED TO"
            elif word[0].isupper():
                return "Used to"
            return "used to"

        result = re.sub(
            r"(?<!\bdid\s)(?<!\bdidn't\s)(?<!\bdid not\s)\b(use)\s+to\b",
            use_to_replace,
            result,
            flags=re.IGNORECASE,
        )

        # 3. Preposition collocations
        for pattern, rep_str in cls.PREPOSITION_RULES:
            def make_prep_sub(repl: str):
                def sub_fn(m: re.Match) -> str:
                    orig = m.group(0)
                    if orig.isupper():
                        return repl.upper()
                    elif orig[0].isupper():
                        return repl[0].upper() + repl[1:]
                    return repl
                return sub_fn

            result = pattern.sub(make_prep_sub(rep_str), result)

        # 4. Capitalize after sentence boundary punctuation without altering newlines
        result = re.sub(
            r"([.!?]\s+)([a-z])",
            lambda m: m.group(1) + m.group(2).upper(),
            result,
        )

        return result


class ParagraphEngine:
    """
    Tier 3: ParagraphEngine
    Disfluency, stutter, and discourse polishing:
    - Safe word deduplication strictly scoped to function words.
    - Preserves valid repetitions ('had had', 'that that', 'Bora Bora', 'Duran Duran').
    - Strips acoustic vocal stalls and verbal hesitations ('um', 'uh', 'er', 'umm', 'uhh', 'aah', 'ahh').
    - Cleans up false starts ('at 2... actually 3' -> 'at 3').
    """

    FUNC_WORDS = (
        "the|a|an|and|or|but|is|are|was|were|be|been|"
        "to|of|in|on|at|for|with|from|by|it|this"
    )
    DEDUP_PATTERN = re.compile(rf"\b({FUNC_WORDS})\s+\1\b", re.IGNORECASE)

    FALSE_START_PREP_PATTERN = re.compile(
        r"(?i)\b(at|on|in|for|from|to|by|about|with)\s+(\w+)\s*[,]?\s*(?:actually|wait no|no wait|wait|i mean|or rather)\s+(?:\1\s+)?"
    )
    FALSE_START_NUM_PATTERN = re.compile(
        r"(?i)\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*[,]?\s*(?:actually|wait no|no wait|wait|i mean|or rather)\s+(?=\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    )
    FALSE_START_PUNCT_PATTERN = re.compile(
        r"(?i)\b\w+\s*(?:,\s*|\s*(?:\.\.\.|—|-{1,2})\s*)(?:actually|wait no|no wait|wait|i mean|or rather)\s*"
    )

    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # 1. Safe word deduplication restricted to function words
        while cls.DEDUP_PATTERN.search(result):
            result = cls.DEDUP_PATTERN.sub(r"\1", result)

        # 2. Verbal hesitation stripping
        # Hesitation surrounded by commas: ", um," -> ""
        result = re.sub(
            r"(?i),\s*\b(?:um+|uh+|umm+|uhh+|er+|err+|aah+|ahh+)\b\s*,",
            "",
            result,
        )
        # Leading hesitation with comma: "Um, " -> ""
        result = re.sub(
            r"(?i)^\s*\b(?:um+|uh+|umm+|uhh+|er+|err+|aah+|ahh+)\b\s*,\s*",
            "",
            result,
        )
        # Trailing comma + hesitation: ", um." -> "."
        result = re.sub(
            r"(?i),\s*\b(?:um+|uh+|umm+|uhh+|er+|err+|aah+|ahh+)\b\s*([.!?]?)$",
            r"\1",
            result,
        )
        # Standalone hesitation words: "\bum\b"
        result = re.sub(
            r"(?i)\b(?:um+|uh+|umm+|uhh+|er+|err+|aah+|ahh+)\b",
            "",
            result,
        )
        # Clean up stray commas or multiple spaces left by hesitation removal
        result = re.sub(r",\s*,+", ",", result)
        result = re.sub(r"^\s*,\s*", "", result)
        result = re.sub(r"[^\S\r\n]{2,}", " ", result).strip()

        # 3. Conversational filler word stripping
        # Leading "So basically, " / "Basically, "
        result = re.sub(r"(?i)^\s*(?:so\s+)?basically\b\s*,?\s*", "", result)
        # Fillers surrounded by commas: ", you know," -> ","
        result = re.sub(
            r"(?i),\s*\b(?:you know|basically|i mean|so yeah|matlab ki|matlab|yaani)\b\s*,?",
            ",",
            result,
        )
        # Standalone like between commas
        result = re.sub(r"(?i),\s*like\s*,", ",", result)
        result = re.sub(r",\s*,+", ",", result)
        result = re.sub(r"^\s*,\s*", "", result)
        result = re.sub(r"[^\S\r\n]{2,}", " ", result).strip()

        # 4. False-start & verbal backtrack cleanup
        # Preposition false-starts: "at 2 actually 3 pm" -> "at 3 pm"
        result = cls.FALSE_START_PREP_PATTERN.sub(r"\1 ", result)
        # Number false-starts: "we need 5 actually 6 licenses" -> "we need 6 licenses"
        result = cls.FALSE_START_NUM_PATTERN.sub("", result)
        # Punctuation-delimited false-starts: "at 2... actually 3", "at 2, actually 3"
        result = cls.FALSE_START_PUNCT_PATTERN.sub("", result)

        return result


class FinalEditor:
    """
    Tier 4: FinalEditor
    Typography, technical string shielding, and punctuation guardrails:
    - Shields URLs, domains, and technical filenames against punctuation mangling ('node.js', 'test.py').
    - Normalizes horizontal whitespace while strictly preserving multiline formatting and indentation.
    - Controlled sentence capitalization without forcing periods on command lines or code snippets.
    """

    TECH_PATTERN = re.compile(
        r"(?:https?://\S+|www\.\S+|\b[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+\b|\b[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+\b)"
    )

    CLI_PREFIXES: Set[str] = {
        "npm",
        "npx",
        "yarn",
        "pnpm",
        "git",
        "cargo",
        "pip",
        "python",
        "docker",
        "kubectl",
        "cd",
        "ls",
        "dir",
        "node",
        "uvicorn",
        "pytest",
    }

    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # 1. Shield technical tokens (URLs, domains, filenames, code modules)
        tokens: List[str] = []

        def shield(match: re.Match) -> str:
            placeholder = f"__KVIE_TECH_TOKEN_{len(tokens)}__"
            tokens.append(match.group(0))
            return placeholder

        result = cls.TECH_PATTERN.sub(shield, result)

        # 2. Punctuation spacing (around commas, periods, colons, etc.)
        # Remove whitespace before punctuation
        result = re.sub(r"[^\S\r\n]+([,.:;?!])", r"\1", result)
        # Ensure single space after punctuation when followed by word character
        result = re.sub(r"([,.:;?!])([a-zA-Z0-9])", r"\1 \2", result)

        # 3. Restore shielded technical tokens
        for i, token in enumerate(tokens):
            result = result.replace(f"__KVIE_TECH_TOKEN_{i}__", token)

        # 4. Whitespace sanitization preserving newlines and indentation
        lines: List[str] = []
        for line in result.split("\n"):
            match = re.match(r"^(\s*)(.*)", line)
            indent = match.group(1) if match else ""
            content = match.group(2) if match else line
            cleaned_content = re.sub(r"[^\S\r\n]+", " ", content).rstrip()
            if cleaned_content:
                lines.append(f"{indent}{cleaned_content}")
            else:
                lines.append("")
        result = "\n".join(lines).strip()

        # 5. Controlled capitalization without forcing periods on command lines
        first_token = result.split()[0].lower() if result.split() else ""
        if first_token not in cls.CLI_PREFIXES and not cls.TECH_PATTERN.match(first_token):
            # Capitalize first character if lowercase letter
            if result and result[0].islower():
                result = result[0].upper() + result[1:]

        return result


class GrammarRouter:
    """
    Multi-Tier Grammar Polisher Engine entry point.
    Routes text deterministically through all 4 engine tiers:
    TokenEngine -> SentenceEngine -> ParagraphEngine -> FinalEditor.
    """

    @classmethod
    def route(cls, text: str, enabled: bool = True) -> str:
        if not enabled or not text or not text.strip():
            return text.strip() if text else ""

        step1 = TokenEngine.process(text)
        step2 = SentenceEngine.process(step1)
        step3 = ParagraphEngine.process(step2)
        step4 = FinalEditor.process(step3)
        return step4
