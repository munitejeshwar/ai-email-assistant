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

Generate a SHORT friendly human-like email reply.
Answer their message.

IMPORTANT RULES:
- Reply as muni' AI assistent 
- Sound natural
- Friendly tone
- Keep under 5 sentences
- Never sound robotic
- Do not use corporate language
- Reply casually if friend-like message
- If someone asks for contact details,
  Instagram,
  social media,
  or faster communication,
  include:

Instagram:
@muni_tejeshwar

Also mention:
"Thank you for contacting Muni. This AI assistant received your email successfully.
Muni will respond shortly"

EMAIL DETAILS:

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
