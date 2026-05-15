from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


def classify_email(subject, body):

    prompt = f"""
    Classify this email into ONE category only.

    Categories:
    - IMPORTANT
    - PROMOTION
    - SOCIAL
    - SPAM
    - UPDATES

    SUBJECT:
    {subject}

    BODY:
    {body[:2000]}

    Return ONLY the category name.
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

    return response.choices[0].message.content.strip()