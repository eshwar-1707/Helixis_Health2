from flask import Flask, request, jsonify
from collections import defaultdict, deque
import requests
import openai
import os

app = Flask(__name__)

# ====== CONFIG ======
VERIFY_TOKEN = "hackathon2025"
WHATSAPP_TOKEN = "EAAg0NTccUccBPdNB6DcgyonLIDeObqadZAaOKbMYEsZCoxSfsQV8CG6tf0ZBncZCg0MirPYZAcK3CKubOLG10ZAPO1SKsZBa6H6JpBJTQdL92GTxy7y36jxTOWYAYEfE81lPhshrJCDYgPlMnhSO7HV4IBuuUxfJRgBazeBYc5pBV6PHiI9HzIGlIf0aD05"
PHONE_NUMBER_ID = "822103324313430"
OPENAI_API_KEY = "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"
openai.api_key = OPENAI_API_KEY

# ====== MEMORY ======
user_conversations = defaultdict(lambda: deque(maxlen=20))

# ====== SYSTEM PROMPT ======
SYSTEM_PROMPT = (
    "You are a helpful **medical-only AI assistant**. "
    "You only provide information related to **health, symptoms, first aid, and medical advice**. "
    "If the user asks about something unrelated, politely decline and redirect them back to health topics. "
    "Keep answers concise, clear, and professional. "
    "Always reply in the same language the user uses."
)

# ====== VERIFY WEBHOOK ======


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
        changes = data["entry"][0]["changes"][0]["value"]

        if "messages" not in changes:  # Skip non-message updates
            return "No message", 200

        entry = changes["messages"][0]
        sender_id = entry["from"]
        user_message = entry["text"]["body"]

        # Reset memory
        if user_message.lower().strip() == "reset":
            user_conversations[sender_id].clear()
            send_message(sender_id, "✅ Memory cleared. Let's start fresh.")
            return "OK", 200

        # Store user input
        user_conversations[sender_id].append(
            {"role": "user", "content": user_message})

        # Build prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(list(user_conversations[sender_id]))

        # Get GPT reply
        reply = get_openai_response(messages)

        # Store reply
        user_conversations[sender_id].append(
            {"role": "assistant", "content": reply})

        # Send reply
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
        return resp.choices[0].message["content"].strip()
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
        result[user_id] = {
            "messages_stored": len(history),
            "last_message": history[-1]["content"] if history else "No messages yet"
        }
    return jsonify(result)


# ====== MAIN ======
if __name__ == "__main__":
    app.run(port=5000, debug=True)
