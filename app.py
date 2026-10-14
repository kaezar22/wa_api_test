import os

from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()  # en tu PC lee el archivo .env; en el servidor usa las variables de entorno

import utils
import whatsapp_service

# Palabra que se pone en Meta como "Identificador de verificación" del webhook
VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "ekhrgjswfelhdbf20836jkhbshdopf")

app = Flask(__name__)


@app.route('/welcome', methods=['GET'])
def index():
    return "Welcome developer"


@app.route('/whatsapp', methods=['GET'])
def VerifyToken():
    try:
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if token is not None and challenge is not None and token == VERIFY_TOKEN:
            return challenge
        return "", 400
    except Exception:
        return "", 400


@app.route('/whatsapp', methods=['POST'])
def ReceivedMessage():
    try:
        body = request.get_json()
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Meta también avisa estados (enviado/entregado/leído): esos no traen "messages"
        if "messages" not in value:
            return "EVENT_RECEIVED"

        message = value["messages"][0]
        number = message["from"]

        text = utils.GetTextUser(message)
        print(f"Mensaje de {number}: {text}")
        if text:
            GenerateMessage(text, number)

        return "EVENT_RECEIVED"
    except Exception as e:
        print("Error procesando el webhook:", e)
        return "EVENT_RECEIVED"


def GenerateMessage(text, number):
    text = "El usuario dijo: " + text
    whatsapp_service.SendMessageWhatsapp(text, number)


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
