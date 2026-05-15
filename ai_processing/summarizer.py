# ai_processing/summarizer.py

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)


def summarize_email(email_text):
    """
    Uses AI to summarize an email body.
    """

    prompt = f"""
    Summarize this email in 3 concise bullet points:

    {email_text}
    """

    try:
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

    except Exception as e:
        return f"AI ERROR: {str(e)}"