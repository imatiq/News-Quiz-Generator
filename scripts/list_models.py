import os

from dotenv import find_dotenv, load_dotenv
from google import genai

load_dotenv(find_dotenv())
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for m in client.models.list():
    # keep only models that can generate text
    if "generateContent" in (m.supported_actions or []):
        print(m.name.replace("models/", ""))