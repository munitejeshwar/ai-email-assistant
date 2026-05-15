from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


def analyze_priority(subject, body):

    prompt = f"""
    Analyze this email carefully.

    Determine:

    1. PRIORITY SCORE (1-10)
    2. URGENCY (LOW, MEDIUM, HIGH)
    3. ACTION NEEDED? (YES or NO)

    EMAIL SUBJECT:
    {subject}

    EMAIL BODY:
    {body[:2000]}

    Return EXACTLY in this format:

    PRIORITY: X/10
    URGENCY: LOW/MEDIUM/HIGH
    ACTION: YES/NO
    """

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content