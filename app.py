from flask import Flask, request, jsonify
from collections import defaultdict, deque
import requests
from deep_translator import GoogleTranslator
import openai
import os

app = Flask(__name__)

# ====== CONFIG ======
VERIFY_TOKEN = "hackathon2025"
WHATSAPP_TOKEN = "EAAg0NTccUccBPdNB6DcgyonLIDeObqadZAaOKbMYEsZCoxSfsQV8CG6tf0ZBncZCg0MirPYZAcK3CKubOLG10ZAPO1SKsZBa6H6JpBJTQdL92GTxy7y36jxTOWYAYEfE81lPhshrJCDYgPlMnhSO7HV4IBuuUxfJRgBazeBYc5pBV6PHiI9HzIGlIf0aD05"
PHONE_NUMBER_ID = "822103324313430"
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY_HERE"
openai.api_key = OPENAI_API_KEY

# ====== MEMORY ======
user_conversations = defaultdict(lambda: deque(maxlen=20))

# ====== SYSTEM PROMPT ======
SYSTEM_PROMPT = (
    "You are a helpful **medical-only AI assistant**. "
    "You only provide information related to **health, symptoms, first aid, and medical advice**. "
    "If the user asks about something unrelated, politely decline and redirect them back to health topics. "
    "Keep answers concise, clear, and professional."
)

# ====== WHATSAPP VERIFY WEBHOOK ======


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Verification failed", 403

# ====== RECEIVE & PROCESS MESSAGES ======


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        entry = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender_id = entry["from"]
        user_message = entry["text"]["body"]

        # Reset memory
        if user_message.lower().strip() == "reset":
            user_conversations[sender_id].clear()
            send_message(sender_id, "✅ Memory cleared. Let's start fresh.")
            return "OK", 200

        # Detect language and translate to English
        detected_lang = GoogleTranslator().detect(user_message)
        if detected_lang != "en":
            user_message_en = GoogleTranslator(
                source=detected_lang, target="en").translate(user_message)
        else:
            user_message_en = user_message

        # Append user message
        user_conversations[sender_id].append(
            {"role": "user", "content": user_message_en})

        # Build prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(list(user_conversations[sender_id]))

        # Get GPT-3.5 reply
        reply_en = get_openai_response(messages)

        # Translate back to user language if needed
        if detected_lang != "en":
            reply = GoogleTranslator(
                source="en", target=detected_lang).translate(reply_en)
        else:
            reply = reply_en

        # Append assistant reply
        user_conversations[sender_id].append(
            {"role": "assistant", "content": reply_en})

        # Send message
        send_message(sender_id, reply)

    except Exception as e:
        print("❌ Error handling message:", e)

    return "OK", 200

# ====== OPENAI GPT CALL ======


def get_openai_response(messages):
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("❌ OpenAI API error:", e)
        return "⚠ Sorry, I couldn’t process that."

# ====== SEND MESSAGE TO WHATSAPP ======


def send_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}",
               "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp",
               "to": to, "type": "text", "text": {"body": text}}
    requests.post(url, headers=headers, json=payload)

# ====== DEBUG STATUS ======


@app.route("/status", methods=["GET"])
def status():
    result = {}
    for user_id, history in user_conversations.items():
        result[user_id] = {"messages_stored": len(
            history), "last_message": history[-1]["content"] if history else "No messages yet"}
    return jsonify(result)


# ====== MAIN ======
if __name__ == "__main__":
    app.run(port=5000, debug=True)
