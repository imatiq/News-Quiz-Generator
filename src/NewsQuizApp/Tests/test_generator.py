import json
from NewsQuizApp.Generator.QuizGenerator import quizGenerator

qg = quizGenerator()
item = {
    "Category": "Current Affairs",
    "Paragraph": (
        "Punjab Chief Minister Maryam Nawaz Sharif on Tuesday announced plans to introduce "
        "5,000 more Green Buses and extend the 'Apni Chhat, Apna Ghar' programme to 500,000 "
        "homes across the province."
    ),
}

print("verify ->", qg.verify(item["Category"], item["Paragraph"]))
result = qg.generate(item)
print(json.dumps(result, indent=2, ensure_ascii=False) if result else "None (rejected or no valid MCQ)")

# Structure checks
if result:
    for entry in result["QuizAndFact"]:
        q = next(v for k, v in entry.items() if k.startswith("q"))
        assert len(q["Options"]) == 4 and q["Ans"] in q["Options"], "bad MCQ structure"
    print("\nStructure OK")