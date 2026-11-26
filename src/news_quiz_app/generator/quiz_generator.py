"""
NewsQuizApp: takes {"Category", "Paragraph"} and returns facts + MCQs using Gemini.

Flow:
  1. Verify that the paragraph is real news and fix its category if needed. If not -> None.
  2. Generate facts and one MCQ per fact (1 correct + 3 wrong options).
  3. Drop any MCQ that is structurally invalid.
  4. Return ONE dict with the paragraph once and all facts/quizzes nested under it.

Setup:
    uv add google-genai python-dotenv
    .env (project root):
        GEMINI_API_KEY=your-key
        GEMINI_MODEL=gemini-3.8-flash   # optional
"""

import json
import os
import random
import re
import time

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types

load_dotenv(find_dotenv())

VALID_CATEGORIES = ["Political Affairs", "Current Affairs", "International Affairs"]


def load_models(override=None) -> list[str]:      # outside the class, no indentation
    # Split the comma-separated list into separate model names
    if isinstance(override, str):
        override = [override]
    if not override:
        override = os.getenv("GEMINI_MODELS", "").split(",")
    models = []
    for m in override:
        m = m.strip()
        if m and m not in models:
            models.append(m)
    if not models:
        raise RuntimeError("Models missing. Set GEMINI_MODELS in .env")
    return models

VALID_CATEGORIES = ["Political Affairs", "Current Affairs", "International Affairs"]
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]

VERIFY_PROMPT = """You are a strict news editor.
Check the paragraph, decide if it is usable news, and decide its correct category.

Allowed categories (use these exact names):
- Political Affairs: government, parliament, parties, elections, politicians, policies, political court cases.
- Current Affairs: important ongoing Pakistan domestic events (economy, security, social issues, disasters, public affairs).
- International Affairs: foreign relations, other countries, global organisations, wars, treaties, world events.

Steps:
1. Check that the paragraph is genuine news/analysis content with enough factual content to make quiz questions.
   It must NOT be an advertisement, entertainment, sports, lifestyle, navigation text or boilerplate.
   If it fails this, set "valid" to false.
2. Pick the single best category for the paragraph from the three allowed categories, based on its content.
   - If the assigned category is the best fit, keep it.
   - If another allowed category fits better, use that one instead (reassign).
   - If the paragraph fits none of the three allowed categories, set "valid" to false.

Assigned category: {category}
Paragraph: {paragraph}

Reply ONLY with JSON:
{{"valid": true or false, "category": "<one of the three allowed categories, or null if valid is false>", "reason": "<short reason>"}}"""

GENERATE_PROMPT = """You are a quiz writer for a news-based Fact/Quiz app used by students preparing for
competitive exams and by readers who want to stay informed.

From the paragraph below, extract up to {max_facts} USEFUL facts and write ONE multiple-choice question
for each fact. If the paragraph has fewer useful facts, return fewer. Quality matters more than quantity.

A fact is USEFUL only if it carries information worth remembering, such as:
- Who did, said, signed, announced or was appointed (names, designations, institutions)
- Key numbers: amounts, percentages, prices, dates, deadlines, rankings, counts
- Decisions, policies, laws, agreements, court rulings and their outcomes
- Places, organisations and countries directly involved in the event
- Cause and effect that is clearly stated (what happened and why)

A fact is NOT useful, so SKIP it, if it is:
- Trivial, obvious or generic (e.g. "a meeting was held", "officials spoke to media")
- Background filler, scene-setting or a repeated detail
- An opinion, prediction, praise, criticism or editorial language
- Too vague to test (e.g. "prices changed", "talks continued")

Rules:
- Use only facts explicitly stated in the paragraph. No outside knowledge, no guessing.
- Each fact must be one clear, self-contained sentence with the key detail (who/what/how much/when/where).
- Each question must make sense on its own without reading the paragraph. Name the subject clearly
  (never "the minister", "the company" or "this decision" without saying which one).
- Test the key detail itself: the answer should be the name, number, date, place or decision that matters.
- Exactly 4 options: 1 correct and 3 plausible but clearly wrong options of the same type
  (all names, all numbers, all places, all decisions).
- Wrong options must be believable but definitely wrong. Do not use "All of the above", "None of the above"
  or options that overlap with the correct answer.
- Numbers and dates in the options must use the same format and units as the correct answer.
- The correct answer must be one of the 4 options, written exactly the same.
- If a question would be illogical, ambiguous, or have more than one correct option, SKIP it.
- If the paragraph has no useful facts, return {{"items": []}}.

Category: {category}
Paragraph: {paragraph}

Reply ONLY with JSON in this format:
{{"items": [
  {{"fact": "<one-sentence fact>",
    "question": "<question>",
    "options": ["<opt1>", "<opt2>", "<opt3>", "<opt4>"],
    "correct_answer": "<exact text of the correct option>"}}
]}}"""


class AllModelsExhausted(Exception):
    # Raised when every model is out of quota or unavailable
    pass

    # inside class NewsQuizApp.__init__ add:
    #     self.exhausted = set()      # models whose daily quota is finished


class quizGenerator:
    LETTERS = ["A", "B", "C", "D"]

    def __init__(
            self,
            api_key: str | None = None,
            models=None,
            max_facts: int = 5,
            max_tries: int = 2,
    ):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Gemini API key missing. Set GEMINI_API_KEY in .env or pass api_key=...")
        self.client = genai.Client(api_key=key)
        self.models = load_models(models)  # list from GEMINI_MODELS
        self.max_facts = max_facts
        self.max_tries = max_tries
        self.exhausted = set()  # models whose daily quota is finished

    # ---------- Gemini helper ----------

    def _ask_json(self, prompt: str) -> dict:
            last_err = None
            for model in self.models:
                if model in self.exhausted:
                    continue  # skip models that hit the daily limit
                for attempt in range(self.max_tries):
                    try:
                        resp = self.client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0,
                                response_mime_type="application/json",
                            ),
                        )
                        if not resp.text:
                            raise ValueError("Empty response from Gemini")
                        raw = re.sub(r"^```(?:json)?|```$", "", resp.text.strip(), flags=re.MULTILINE).strip()
                        return json.loads(raw)
                    except Exception as e:
                        last_err = e
                        code = getattr(e, "code", None)
                        print(f"[{model}] attempt {attempt + 1}/{self.max_tries} failed: {type(e).__name__} ({code})")
                        if code in (400, 401, 403):
                            raise  # wrong key/request
                        if code == 429:
                            self.exhausted.add(model)  # daily quota: no point retrying today
                            break
                        if code == 404:
                            break
                        if attempt < self.max_tries - 1:
                            time.sleep(10 if code == 503 else 3)
            raise AllModelsExhausted(f"No model available. Exhausted today: {sorted(self.exhausted)}") from last_err

    # ---------- Step 1: verify ----------
    def verify(self, category: str, paragraph: str) -> str | None:
        """Returns the final (possibly corrected) category, or None if the paragraph should be ignored."""
        data = self._ask_json(VERIFY_PROMPT.format(category=category, paragraph=paragraph))
        if not isinstance(data, dict) or not data.get("valid", False):
            return None
        final_category = str(data.get("category") or "").strip()
        return final_category if final_category in VALID_CATEGORIES else None

    # ---------- Step 3: validate + format one MCQ ----------
    def _build_item(self, number: int, raw: dict) -> dict | None:
        # Extract the fields; skip the item if any is missing
        try:
            fact = str(raw["fact"]).strip()
            question = str(raw["question"]).strip()
            options = [str(o).strip() for o in raw["options"]]
            correct = str(raw["correct_answer"]).strip()
        except (KeyError, TypeError):
            return None

        # Structural checks: 4 non-empty, unique options and a correct answer that is one of them
        if not fact or not question or len(options) != 4:
            return None
        if any(not o for o in options) or len({o.lower() for o in options}) != 4:
            return None
        if correct not in options:
            return None

        random.shuffle(options)  # so the correct answer is not always in the same position
        letter_map = dict(zip(self.LETTERS, options, strict=False))
        correct_letter = next(letter for letter, o in letter_map.items() if o == correct)

        return {
            "fact": fact,
            f"q{number}": {
                "question": question,
                "Options": letter_map,
                "Ans": correct_letter,
            },
        }

    # ---------- Main entry ----------
    def generate(self, item: dict) -> dict | None:
        """
        item: {"Category": ..., "Paragraph": ...}  (lowercase keys are also accepted)
        Returns {"category", "paragraph", "QuizAndFact": [...]}, or None if the item is ignored.
        """
        # Read the input first
        category = (item.get("Category") or item.get("category") or "").strip()
        paragraph = (item.get("Paragraph") or item.get("paragraph") or "").strip()
        if not category or not paragraph:
            return None

        # Step 1: verify the paragraph and reassign the category if needed
        final_category = self.verify(category, paragraph)
        if not final_category:
            return None
        category = final_category  # use the corrected category from here on

        # Step 2: generate facts + MCQs
        data = self._ask_json(
            GENERATE_PROMPT.format(max_facts=self.max_facts, category=category, paragraph=paragraph)
        )

        # Step 3: keep only valid MCQs, numbered q1, q2, ...
        quiz_and_fact = []
        items = data.get("items", []) if isinstance(data, dict) else []
        for raw in items:
            built = self._build_item(len(quiz_and_fact) + 1, raw)
            if built:
                quiz_and_fact.append(built)

        if not quiz_and_fact:
            return None

        return {
            "category": category,
            "paragraph": paragraph,
            "QuizAndFact": quiz_and_fact,
        }