import os
import threading
from collections import deque

from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()  # en tu PC lee el archivo .env; en el servidor usa las variables de entorno

import chatbot
import utils
import whatsapp_service

# Palabra que se pone en Meta como "Identificador de verificación" del webhook
VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "ekhrgjswfelhdbf20836jkhbshdopf")

app = Flask(__name__)


@app.route('/welcome', methods=['GET'])
def index():
    return "Welcome developer"


PRIVACY_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de privacidad</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#222}</style>
</head><body>
<h1>Política de privacidad</h1>
<p>Este es un proyecto de prueba de un chatbot de WhatsApp, usado solo para probar el envío y la
recepción de mensajes con la WhatsApp Cloud API.</p>
<h2>Datos que se tratan</h2>
<p>Número de teléfono, nombre de perfil de WhatsApp y el contenido de los mensajes enviados al número de prueba.</p>
<h2>Uso</h2>
<p>Los datos se usan únicamente para responder los mensajes de prueba. No se venden ni se comparten con
terceros, salvo Meta Platforms como proveedor de WhatsApp.</p>
<h2>Eliminación</h2>
<p>Puedes pedir la eliminación de tus datos respondiendo por WhatsApp al mismo número.</p>
</body></html>"""


@app.route('/privacy', methods=['GET'])
def privacy():
    return PRIVACY_HTML


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

        # Meta reintenta el envío si tardamos; no procesar dos veces el mismo mensaje
        if _ya_procesado(message.get("id")):
            return "EVENT_RECEIVED"

        contacts = value.get("contacts") or [{}]
        nombre = contacts[0].get("profile", {}).get("name")

        text = utils.GetTextUser(message)
        print(f"Mensaje de {number}: {text}")

        # El modelo puede tardar varios segundos: respondemos 200 a Meta de inmediato
        # y generamos la respuesta en segundo plano.
        threading.Thread(target=GenerateMessage, args=(text, number, nombre), daemon=True).start()

        return "EVENT_RECEIVED"
    except Exception as e:
        print("Error procesando el webhook:", e)
        return "EVENT_RECEIVED"


_procesados = deque(maxlen=500)


def _ya_procesado(message_id):
    if not message_id:
        return False
    if message_id in _procesados:
        return True
    _procesados.append(message_id)
    return False


def GenerateMessage(text, number, nombre=None):
    try:
        if not text:
            respuesta = "Por ahora solo puedo leer mensajes de texto. ¿Me escribes qué productos te interesan?"
        elif chatbot.habilitado():
            respuesta = chatbot.responder(number, text, nombre)
        else:
            respuesta = "El usuario dijo: " + text  # sin DEEPSEEK_API_KEY: modo eco
        whatsapp_service.SendMessageWhatsapp(respuesta, number)
    except Exception as e:
        print("Error generando respuesta:", e)


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)))
