from news_quiz_app.classifier.paragraph_classifier import paragraphClassifier

# (text, expected label; None means it should be ignored)
SAMPLES = [
    ("The National Assembly passed the finance bill amid opposition protest.", "Political Affairs"),
    ("Flash floods in Swat displaced hundreds of families on Monday.", "Current Affairs"),
    ("The UN Security Council met to discuss the ceasefire in Gaza.", "International Affairs"),
    ("Shop now and get 50% off on all summer collections!", None),
    ("The cricket team won the T20 series by 3 runs.", None),
]

clf = paragraphClassifier()
ok = 0
for text, expected in SAMPLES:
    result = clf.classify(text)
    got = result["Category"] if result else None
    passed = got == expected
    ok += passed
    print(f"{'PASS' if passed else 'FAIL'} | expected={expected} | got={got} | {text[:60]}")
print(f"\n{ok}/{len(SAMPLES)} passed")