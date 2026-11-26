"""
ParagraphClassifier: classifies a news text with Llama 3 (via Ollama).

Returns {"Category": ..., "Paragraph": ...} for Political Affairs, Current Affairs
or International Affairs. Anything else (ads, entertainment, sports, etc.) returns None.

Usage:
    from news_quiz_app.classifier.paragraph_classifier import paragraphClassifier

    clf = ParagraphClassifier()          # create once, reuse
    result = clf.classify(text)          # dict, or None if irrelevant
"""

import json
import time

import ollama

SYSTEM_PROMPT = """You are a news paragraph classifier for a Pakistani news pipeline.
Classify the text into exactly ONE category:
- Political Affairs: government, parliament, parties, elections, politicians, policies, political court cases.
- Current Affairs: important ongoing Pakistan domestic events (economy, security, social issues, disasters, public affairs).
- International Affairs: foreign relations, other countries, global organisations, wars, treaties, world events.
- Other: advertisements, entertainment, sports, lifestyle, promotions, navigation/boilerplate text, social media posts or anything else.

Examples:
"The National Assembly passed the finance bill amid opposition protest." -> Political Affairs
"Flash floods in Swat displaced hundreds of families on Monday." -> Current Affairs
"The UN Security Council met to discuss the ceasefire in Gaza." -> International Affairs
"Shop now and get 50% off on all summer collections!" -> Other
"The cricket team won the T20 series by 3 runs." -> Other

Reply ONLY with JSON: {"category": "<Political Affairs | Current Affairs | International Affairs | Other>"}"""


class paragraphClassifier:
    # Maps the model's lowercase label to the exact category name
    ALLOWED = {
        "political affairs": "Political Affairs",
        "current affairs": "Current Affairs",
        "international affairs": "International Affairs",
    }

    def __init__(self, model: str = "llama3", retries: int = 2):
        self.model = model
        self.retries = retries

    def classify(self, text: str) -> dict | None:
        """Classify the text as-is. Returns {"Category", "Paragraph"} or None if irrelevant."""
        for attempt in range(self.retries + 1):
            try:
                resp = ollama.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    format="json",
                    options={"temperature": 0},
                )
                label = str(json.loads(resp["message"]["content"]).get("category", "Other")).strip().lower()
                category = self.ALLOWED.get(label)
                # Anything outside the three allowed categories is ignored
                return {"Category": category, "Paragraph": text} if category else None
            except Exception:
                # Retry with a short, growing wait; raise after the last attempt
                if attempt == self.retries:
                    raise
                time.sleep(1.5 * (attempt + 1))