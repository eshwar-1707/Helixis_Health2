from flask import Flask, request, jsonify
import requests
import os
from collections import defaultdict, deque

app = Flask(__name__)

# ====== CONFIG FROM ENV ======
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# List of API keys (rotate through them)
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
]
current_key_index = 0

# ====== MEMORY ======
user_conversations = defaultdict(lambda: deque(maxlen=20))

# ====== SYSTEM PROMPT ======
SYSTEM_PROMPT = (
    "You are a helpful **medical-only AI assistant**. "
    "You only provide information related to **health, symptoms, first aid, and medical advice**. "
    "If the user asks about something unrelated (like politics, sports, coding, etc.), "
    "politely decline and redirect them back to health-related topics. "
    "Keep your answers concise, clear, and professional. "
    "⚠️ IMPORTANT: Always reply in the **same language** that the user used in their message."
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

        if user_message.lower().strip() == "reset":
            user_conversations[sender_id].clear()
            send_message(sender_id, "✅ Memory cleared. Let's start fresh.")
            return "OK", 200

        # Append user message
        user_conversations[sender_id].append(
            {"role": "user", "content": user_message})

        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(list(user_conversations[sender_id]))

        # Get reply from Gemini
        reply = get_gemini_response(messages)

        # Save bot reply
        user_conversations[sender_id].append(
            {"role": "assistant", "content": reply})

        # Send reply back to WhatsApp
        send_message(sender_id, reply)

    except Exception as e:
        print("❌ Error handling message:", e)

    return "OK", 200

# ====== GEMINI CALL WITH KEY ROTATION ======


def get_gemini_response(messages):
    global current_key_index

    for _ in range(len(GEMINI_API_KEYS)):
        api_key = GEMINI_API_KEYS[current_key_index]
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        contents = []
        for msg in messages:
            if msg["role"] in ["system", "user"]:
                contents.append({"role": "user", "parts": [
                                {"text": msg["content"]}]})
            else:
                contents.append({"role": "model", "parts": [
                                {"text": msg["content"]}]})

        payload = {"contents": contents}

        try:
            resp = requests.post(url, headers=headers,
                                 params=params, json=payload)
            resp_json = resp.json()

            if "error" in resp_json and "quota" in resp_json["error"]["message"].lower():
                print(
                    f"⚠ Quota exceeded for key {current_key_index+1}, switching key...")
                current_key_index = (current_key_index +
                                     1) % len(GEMINI_API_KEYS)
                continue

            return resp_json["candidates"][0]["content"]["parts"][0]["text"]

        except Exception as e:
            print("❌ Gemini API error:", e)
            return "⚠ Sorry, I couldn’t process that."

    return "⚠ All API keys exhausted, try again later."

# ====== SEND MESSAGE TO WHATSAPP ======


def send_message(to, text):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
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
