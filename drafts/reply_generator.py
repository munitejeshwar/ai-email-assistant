from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1"
)


def generate_reply(sender, subject, body):

    prompt = f"""
You are Muni's personal AI email assistant.

Generate a SHORT natural email reply.

VERY IMPORTANT RULES:
- Never use placeholders
- Never write:
  [Your Name]
  Best regards
  Sincerely
- Never sound formal or robotic
- Sound like a real human texting casually
- Maximum 3 short sentences
- Friendly modern tone
- If user asks for contact details or social media,
  include:

Instagram: @muni_tejeshwar

Also say:
"This is Muni's AI assistant."

EMAIL:

FROM:
{sender}

SUBJECT:
{subject}

BODY:
{body}
"""

    response = client.chat.completions.create(
        model="openai/gpt-4o-mini", messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()
