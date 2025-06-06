import telebot
import requests
import os
import PyPDF2
from dotenv import load_dotenv
from groq import Groq
import nest_asyncio
import threading
from fastapi import FastAPI
import uvicorn

nest_asyncio.apply()

app = FastAPI()

load_dotenv()

@app.get("/")
def health_check():
    return {"status": "Bot is running", "version": "1.0"}

BOT_TOKEN = os.environ.get('BOT_TOKEN')

bot = telebot.TeleBot(BOT_TOKEN)

model="mistral-saba-24b"

user_docs = {}
user_histories = {} 
MAX_HISTORY = 10

def update_user_history(user_id, role, content):
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({'role': role, 'content': content})
    # Keep only the last 10 messages
    user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

def build_messages_with_history(user_id, system_prompt=None):
    history = user_histories.get(user_id, [])
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    return messages

def format_for_telegram(text):
    """
    Format text for proper Telegram Markdown display
    """
    # Replace ** with * for Telegram markdown bold
    formatted_text = text.replace('**', '*')
    
    # Replace ### with * for proper markdown headers
    formatted_text = formatted_text.replace('### ', '*')
    formatted_text = formatted_text.replace('###', '*')
    
    return formatted_text

def summarize_with_groq(text):
    # Initialize the Groq client (requires GROQ_API_KEY in environment)
    client = Groq()

    # Create a chat completion request with a summarization prompt
    completion = client.chat.completions.create(
        model="mistral-saba-24b",
        messages=[
            {
                "role": "system",
                "content": "Summarize this document clearly and concisely."
            },
            {
                "role": "user",
                "content": text
            }
        ],
        temperature=0.5,
        max_completion_tokens=1024,
        top_p=1,
        stream=True,
        stop=None,
    )

    # Collect the streamed chunks into a full response
    summary = ""
    for chunk in completion:
        content = chunk.choices[0].delta.content or ""
        print(content, end="", flush=True)
        summary += content

    return summary

def extract_text_from_pdf(path):
    text = ""
    with open(path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ''
    return text

def ask_groq_about(text, question):
    client = Groq()

    # Create a chat completion request with a summarization prompt
    completion = client.chat.completions.create(
        model="mistral-saba-24b",
        messages=[
            {
                "role": "system",
                "content": "You are an assistant helping answer questions about a document."
            },
            {
                "role": "user",
                "content": f"Here is the document:\n{text[:15000]}"
            },
            {
                "role" : "user",
                "content" : f"My question: {question}"
            }
        ],
        temperature=0.5,
        max_completion_tokens=1024,
        top_p=1,
        stream=True,
        stop=None,
    )

    # Collect the streamed chunks into a full response
    summary = ""
    for chunk in completion:
        content = chunk.choices[0].delta.content or ""
        print(content, end="", flush=True)
        summary += content

    return summary

@bot.message_handler(commands=['start', 'hello'])
def greet(message):
    user_histories[message.from_user.id] = []
    bot.reply_to(message, "👋 Hello! Send me a PDF or TXT document, and I can summarize it or answer questions about it.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        filename = message.document.file_name
        with open(filename, 'wb') as f:
            f.write(downloaded_file)

        # Extract text
        if filename.endswith('.pdf'):
            text = extract_text_from_pdf(filename)
        elif filename.endswith('.txt'):
            with open(filename, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            bot.reply_to(message, "❌ Please send a .txt or .pdf file.")
            return

        # Save user's doc text
        user_docs[message.from_user.id] = text

        bot.reply_to(message, "📄 Summarizing your document...")

        summary = summarize_with_groq(text)
        formatted_summary = format_for_telegram(summary)
        
        # Send with Markdown formatting enabled
        bot.reply_to(message, f"✅ *Summary:*\n\n{formatted_summary}", parse_mode='Markdown')

        os.remove(filename)

    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_question(message):
    user_id = message.from_user.id
    if user_id not in user_docs:
        bot.reply_to(message, "📄 Please upload a document first.")
        return

    question = message.text
    doc_text = user_docs[user_id]
    bot.reply_to(message, "🤔 Thinking...")

    try:
        update_user_history(user_id, 'user', question)
        messages = build_messages_with_history(
            user_id,
            system_prompt="You are an assistant helping answer questions about a document."
        )
        # Add the document as context (trim if too long)
        messages.insert(1, {"role": "user", "content": f"Here is the document:\n{doc_text[:15000]}"})

        # Use messages in the Groq API call
        client = Groq()
        completion = client.chat.completions.create(
            model="mistral-saba-24b",
            messages=messages,
            temperature=0.5,
            max_completion_tokens=1024,
            top_p=1,
            stream=True,
            stop=None,
        )
        answer = ""
        for chunk in completion:
            content = chunk.choices[0].delta.content or ""
            answer += content

        update_user_history(user_id, 'assistant', answer)
        formatted_answer = format_for_telegram(answer)
        
        # Send with Markdown formatting enabled
        bot.reply_to(message, f"💡 *Answer:*\n\n{formatted_answer}", parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"⚠️ Failed to answer: {str(e)}")

def run_bot():
    print("Bot is running...")
    bot.infinity_polling()

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)