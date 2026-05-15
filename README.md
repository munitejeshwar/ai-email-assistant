# 📧 AI Email Assistant

An AI-powered email automation system that monitors Gmail inbox activity, analyzes incoming emails using LLMs, classifies importance, sends Telegram alerts, auto-generates replies, and provides a real-time analytics dashboard.

---

#  Features

##  AI Email Processing
- Fetches emails directly from Gmail using Gmail API
- Parses sender, subject, and body content
- Stores processed emails in SQLite database

---

##  AI Intelligence Layer
- AI-generated email summaries
- Email category classification
- Priority & urgency detection
- Spam/noise filtering

Powered using:
- OpenRouter API
- GPT models

---

## 📲 Telegram Notifications
Automatically sends Telegram alerts for:
- Important emails
- High urgency messages
- AI-generated auto replies

---

## ✉️ AI Auto Reply System
For casual/personal emails:
- Generates friendly AI replies
- Sends replies automatically
- Logs sent replies to Telegram

---

#  Streamlit Dashboard

Interactive dashboard with:
- Processed email table
- Priority analytics
- Spam tracking
- Email detail viewer
- AI summary viewer

---

#  Project Architecture

```text
Gmail Inbox
     ↓
Email Fetcher
     ↓
Email Parser
     ↓
AI Processing Layer
 ├── Summarizer
 ├── Classifier
 ├── Priority Analyzer
 └── Reply Generator
     ↓
Database Storage
     ↓
Telegram Alerts
     ↓
Streamlit Dashboard

Tech Stack:
Language-	Python
AI Models-	OpenRouter / GPT
Email API-	Gmail API
Notifications-	Telegram Bot API
Database-	SQLite
Dashboard-	Streamlit
Version Control-	Git + GitHub
 Project Structure
ai-email-assistant/
│
├── ai_processing/
├── auth/
├── dashboard/
├── database/
├── drafts/
├── email_engine/
├── notifications/
├── storage/
├── utils/
│
├── main.py
├── monitor.py
├── requirements.txt
├── README.md
```


 Installation
1. Clone Repository
git clone https://github.com/munitejeshwar/ai-email-assistant.git
cd ai-email-assistant
2. Create Virtual Environment
python -m venv venv

Activate environment:

Windows
venv\Scripts\activate
3. Install Dependencies
pip install -r requirements.txt
4. Configure Environment Variables

Create .env

OPENROUTER_API_KEY=your_api_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
5. Add Gmail API Credentials

Place:

credentials.json

inside project root.

 Running The System
Process Emails
python main.py
Continuous Monitoring
python monitor.py
Launch Dashboard
streamlit run dashboard/app.py
 Screenshots
Dashboard
<img width="1919" height="697" alt="image" src="https://github.com/user-attachments/assets/ff420e5e-9710-4420-b0c6-8f5ca32f525e" />
<img width="1916" height="918" alt="image" src="https://github.com/user-attachments/assets/0ada1c6f-6e80-4bf6-b8f2-7d28e7612e3c" />

Telegram Alerts

<img width="738" height="1600" alt="image" src="https://github.com/user-attachments/assets/d8ad12ee-04cd-42b9-9f8e-dfa2b6098df6" />

Terminal Processing

<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/951cfe93-4aef-42aa-a43e-e07a06e178e7" />

Future Improvements
Gmail auto-labeling
AI memory/context system
Live monitoring dashboard
Multi-user authentication
Vector search memory
Cloud deployment
Voice notifications
Advanced analytics
 Learning Goals Behind This Project

This project was built to learn:

AI workflow automation
API integrations
Gmail OAuth authentication
Notification systems
Dashboard development
Real-world backend architecture
AI-powered productivity systems

Author
Muni Tejeshwar

GitHub:
https://github.com/munitejeshwar


