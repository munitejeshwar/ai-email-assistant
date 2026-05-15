# ai_processing/priority_analyzer.py

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)


def analyze_priority(subject, body):

    prompt = f"""
You are an AI email priority analyzer.

Analyze this email and determine:

1. Priority score out of 10
2. Urgency level
3. Whether user should take action

Respond EXACTLY in this format:

PRIORITY: X/10
URGENCY: LOW/MEDIUM/HIGH
ACTION: YES/NO

EMAIL SUBJECT:
{subject}

EMAIL BODY:
{body[:3000]}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b:free",

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content