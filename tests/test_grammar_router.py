from __future__ import annotations

import pytest
from Backend.kvie.grammar_router import (
    GrammarRouter,
    TokenEngine,
    SentenceEngine,
    ParagraphEngine,
    FinalEditor,
)


class TestTier1TokenEngine:
    def test_spelling_typos(self):
        assert "the" in TokenEngine.process("teh")
        assert "receive" in TokenEngine.process("recieve")
        assert "separate" in TokenEngine.process("seperate")
        assert "definitely" in TokenEngine.process("definately")
        assert "a lot" in TokenEngine.process("alot")

    def test_typo_case_preservation(self):
        assert TokenEngine.process("Teh") == "The"
        assert TokenEngine.process("TEH") == "THE"
        assert TokenEngine.process("Definately") == "Definitely"
        assert TokenEngine.process("Alot") == "A lot"

    def test_brand_casing(self):
        assert "Kritix" in TokenEngine.process("critics")
        assert "Kritix" in TokenEngine.process("kritix")
        assert "KVIE" in TokenEngine.process("kvie")
        assert "GitHub" in TokenEngine.process("github")
        assert "YouTube" in TokenEngine.process("youtube")
        assert "VS Code" in TokenEngine.process("vscode")
        assert "LinkedIn" in TokenEngine.process("linkedin")
        assert "ChatGPT" in TokenEngine.process("chatgpt")
        assert "FastAPI" in TokenEngine.process("fastapi")
        assert "GraphQL" in TokenEngine.process("graphql")
        assert "PostgreSQL" in TokenEngine.process("postgresql")
        assert "PostgreSQL" in TokenEngine.process("postgres")
        assert "MongoDB" in TokenEngine.process("mongodb")
        assert "Kubernetes" in TokenEngine.process("kubernetes")
        assert "Docker" in TokenEngine.process("docker")
        assert "OpenAI" in TokenEngine.process("openai")

    def test_missing_apostrophes(self):
        assert TokenEngine.process("cant") == "can't"
        assert TokenEngine.process("dont") == "don't"
        assert TokenEngine.process("wont") == "won't"
        assert TokenEngine.process("didnt") == "didn't"
        assert TokenEngine.process("isnt") == "isn't"
        assert TokenEngine.process("arent") == "aren't"
        assert TokenEngine.process("wouldnt") == "wouldn't"
        assert TokenEngine.process("couldnt") == "couldn't"
        assert TokenEngine.process("shouldnt") == "shouldn't"
        assert TokenEngine.process("hasnt") == "hasn't"
        assert TokenEngine.process("havent") == "haven't"
        assert TokenEngine.process("thats") == "that's"
        assert TokenEngine.process("whats") == "what's"
        assert TokenEngine.process("theres") == "there's"
        assert TokenEngine.process("youll") == "you'll"
        assert TokenEngine.process("theyll") == "they'll"

    def test_contraction_case_preservation(self):
        assert TokenEngine.process("Cant") == "Can't"
        assert TokenEngine.process("CANT") == "CAN'T"
        assert TokenEngine.process("Dont") == "Don't"
        assert TokenEngine.process("Thats") == "That's"

    def test_speaker_intent_preservation_ambiguous_words(self):
        # Must NOT convert valid English words to contractions
        assert "wed" in TokenEngine.process("they wed in June")
        assert "well" in TokenEngine.process("doing well")
        assert "ill" in TokenEngine.process("he is ill")
        assert "shell" in TokenEngine.process("sea shell")
        assert "shed" in TokenEngine.process("in the tool shed")

    def test_homophones(self):
        assert "they're going" in TokenEngine.process("their going")
        assert "their house" in TokenEngine.process("there house")
        assert "you're welcome" in TokenEngine.process("your welcome")
        assert "your car" in TokenEngine.process("you're car")
        assert "it's working" in TokenEngine.process("its working")
        assert "too much" in TokenEngine.process("to much")
        assert "better than" in TokenEngine.process("better then")
        assert "affect" in TokenEngine.process("will effect the outcome")
        assert "effect" in TokenEngine.process("the direct affect")
        assert "lose" in TokenEngine.process("to loose the match")

    def test_pronoun_capitalization(self):
        assert TokenEngine.process("i think i'm ready") == "I think I'm ready"
        assert TokenEngine.process("i've seen it") == "I've seen it"
        assert TokenEngine.process("i'll be there") == "I'll be there"
        assert TokenEngine.process("i'd love to") == "I'd love to"

    def test_empty_and_whitespace(self):
        assert TokenEngine.process("") == ""
        assert TokenEngine.process("   ") == ""


class TestTier2SentenceEngine:
    def test_phonetic_articles_a_exceptions(self):
        assert SentenceEngine.process("a university") == "a university"
        assert SentenceEngine.process("an university") == "a university"
        assert SentenceEngine.process("a user") == "a user"
        assert SentenceEngine.process("an user") == "a user"
        assert SentenceEngine.process("a European") == "a European"
        assert SentenceEngine.process("an European") == "a European"
        assert SentenceEngine.process("a unique") == "a unique"
        assert SentenceEngine.process("a one-time") == "a one-time"
        assert SentenceEngine.process("an one-time") == "a one-time"
        assert SentenceEngine.process("a useful") == "a useful"
        assert SentenceEngine.process("an useful") == "a useful"
        assert SentenceEngine.process("a ubiquitous") == "a ubiquitous"

    def test_phonetic_articles_an_exceptions(self):
        assert SentenceEngine.process("an hour") == "an hour"
        assert SentenceEngine.process("a hour") == "an hour"
        assert SentenceEngine.process("an honest mistake") == "an honest mistake"
        assert SentenceEngine.process("a honest mistake") == "an honest mistake"
        assert SentenceEngine.process("an honor") == "an honor"
        assert SentenceEngine.process("a honor") == "an honor"
        assert SentenceEngine.process("an heir") == "an heir"
        assert SentenceEngine.process("a heir") == "an heir"

    def test_phonetic_articles_casing(self):
        assert SentenceEngine.process("An university") == "A university"
        assert SentenceEngine.process("A hour") == "An hour"

    def test_spoken_modal_verbs(self):
        assert "could have" in SentenceEngine.process("could of")
        assert "would have" in SentenceEngine.process("would of")
        assert "should have" in SentenceEngine.process("should of")
        assert "might have" in SentenceEngine.process("might of")
        assert "must have" in SentenceEngine.process("must of")
        assert "supposed to" in SentenceEngine.process("suppose to")
        assert "used to" in SentenceEngine.process("I use to live here")
        assert "use to" in SentenceEngine.process("I didn't use to live here")

    def test_preposition_collocations(self):
        assert "interested in" in SentenceEngine.process("interested on")
        assert "congratulations on" in SentenceEngine.process("congratulations for")
        assert "discuss" in SentenceEngine.process("discuss about")
        assert "explain" in SentenceEngine.process("explain about")
        assert "married to" in SentenceEngine.process("married with")
        assert "depend on" in SentenceEngine.process("depend of")
        assert "rely on" in SentenceEngine.process("rely into")
        assert "concentrate on" in SentenceEngine.process("concentrate in")
        assert "cope with" in SentenceEngine.process("cope up with")
        assert "comply with" in SentenceEngine.process("comply to")
        assert "insist on" in SentenceEngine.process("insist to")
        assert "responsible for" in SentenceEngine.process("responsible of")

    def test_newline_and_formatting_preservation(self):
        multiline = "First line.\nSecond line.\nThird line."
        processed = SentenceEngine.process(multiline)
        assert "\n" in processed
        lines = processed.splitlines()
        assert len(lines) == 3

    def test_empty_and_whitespace(self):
        assert SentenceEngine.process("") == ""
        assert SentenceEngine.process("   ") == ""


class TestTier3ParagraphEngine:
    def test_function_word_deduplication(self):
        assert ParagraphEngine.process("the the cat") == "the cat"
        assert ParagraphEngine.process("the the the cat") == "the cat"
        assert ParagraphEngine.process("and and then") == "and then"
        assert ParagraphEngine.process("is is ready") == "is ready"
        assert ParagraphEngine.process("to to go") == "to go"
        assert ParagraphEngine.process("in in the house") == "in the house"

    def test_preserves_valid_repetitions(self):
        assert "had had" in ParagraphEngine.process("he had had enough")
        assert "that that" in ParagraphEngine.process("I know that that was true")
        assert "Bora Bora" in ParagraphEngine.process("trip to Bora Bora")
        assert "Duran Duran" in ParagraphEngine.process("band Duran Duran")

    def test_verbal_hesitation_stripping(self):
        res1 = ParagraphEngine.process("I think, um, we should go")
        assert "um" not in res1.lower()
        res2 = ParagraphEngine.process("We should, uh, start now")
        assert "uh" not in res2.lower()
        res3 = ParagraphEngine.process("Um, hello world")
        assert "um" not in res3.lower()
        res4 = ParagraphEngine.process("We are ready, er, almost ready")
        assert "er" not in res4.lower().split()

    def test_false_start_cleanup(self):
        res = ParagraphEngine.process("meet at 2... actually 3")
        assert "at 3" in res
        assert "2" not in res

        res_emdash = ParagraphEngine.process("meet at 2 — actually 3")
        assert "at 3" in res_emdash

        res_hyphen = ParagraphEngine.process("start on Monday -- wait Tuesday")
        assert "Tuesday" in res_hyphen

    def test_empty_and_whitespace(self):
        assert ParagraphEngine.process("") == ""
        assert ParagraphEngine.process("   ") == ""


class TestTier4FinalEditor:
    def test_technical_symbol_and_url_protection(self):
        assert "node.js" in FinalEditor.process("Install node.js now")
        assert "test.py" in FinalEditor.process("Run test.py script")
        assert "example.com" in FinalEditor.process("Visit example.com today")
        assert "https://github.com/org/repo" in FinalEditor.process("Check https://github.com/org/repo")
        assert "user@example.com" in FinalEditor.process("Email user@example.com please")

    def test_whitespace_and_newline_preservation(self):
        text = "Line one.\n    Line two with indent.\n\nLine three."
        processed = FinalEditor.process(text)
        assert "\n" in processed
        assert "Line one." in processed
        assert "Line two with indent." in processed

    def test_does_not_force_trailing_period_on_code(self):
        cmd = "npm run build"
        assert not FinalEditor.process(cmd).endswith(".")

        git_cmd = "git status"
        assert not FinalEditor.process(git_cmd).endswith(".")

    def test_empty_and_whitespace(self):
        assert FinalEditor.process("") == ""
        assert FinalEditor.process("   ") == ""


class TestGrammarRouterEndToEnd:
    def test_full_pipeline_transformation(self):
        raw = "we launched critics and teh engine is working"
        polished = GrammarRouter.route(raw)
        assert "Kritix" in polished
        assert "the" in polished

    def test_empty_and_whitespace_input(self):
        assert GrammarRouter.route("") == ""
        assert GrammarRouter.route("   ") == ""

    def test_bypass_when_disabled(self):
        raw = "teh critics"
        assert GrammarRouter.route(raw, enabled=False) == "teh critics"

    def test_idempotence(self):
        sample = "We launched Kritix, and the engine is working."
        assert GrammarRouter.route(sample) == sample

    def test_compound_speech_polishing(self):
        raw = "i think, um, we could of visited an university yesterday"
        polished = GrammarRouter.route(raw)
        assert "I" in polished
        assert "um" not in polished.lower()
        assert "could have" in polished
        assert "a university" in polished
