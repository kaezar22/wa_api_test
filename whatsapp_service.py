import os

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_VERSION = "v25.0"


def SendMessageWhatsapp(textUser, number):
    try:
        token = os.environ.get("WA_TOKEN")
        phone_number_id = os.environ.get("WA_PHONE_NUMBER_ID", "1427742553746866")
        if not token:
            print("Falta la variable WA_TOKEN (en .env o en el servidor)")
            return False

        api_url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_number_id}/messages"
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": textUser
            }
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token
        }
        response = requests.post(api_url, json=data, headers=headers, timeout=15)

        if response.status_code == 200:
            return True

        print("Error de Meta:", response.status_code, response.text)
        return False
    except Exception as exception:
        print(exception)
        return False
