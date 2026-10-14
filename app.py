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


PRIVACY_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de privacidad</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#222}</style>
</head><body>
<h1>Política de privacidad</h1>
<p>Este servicio es un asistente de WhatsApp de Grupo Nutrienti S.A.S. (Colombia) que responde
mensajes enviados por los usuarios a nuestro número de WhatsApp Business.</p>
<h2>Datos que tratamos</h2>
<p>Número de teléfono, nombre de perfil de WhatsApp y el contenido de los mensajes que nos envías.</p>
<h2>Para qué los usamos</h2>
<p>Únicamente para responder tus mensajes y gestionar tus solicitudes (pedidos, información de cuenta).
No vendemos ni compartimos tus datos con terceros, salvo Meta Platforms como proveedor de WhatsApp.</p>
<h2>Tus derechos</h2>
<p>De acuerdo con la Ley 1581 de 2012, puedes conocer, actualizar, rectificar o pedir la eliminación de
tus datos escribiendo a contacto@nutrienti.co.</p>
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
