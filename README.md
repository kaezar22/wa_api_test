# whatsapp_chat

Bot de prueba para la WhatsApp Cloud API (Flask). Recibe mensajes por webhook y responde "El usuario dijo: ...".

## Variables de entorno

| Variable | Qué es |
|---|---|
| `WA_TOKEN` | Token de acceso de Meta (secreto) |
| `WA_PHONE_NUMBER_ID` | Phone Number ID del número que envía |
| `WA_VERIFY_TOKEN` | Palabra que se pone en Meta como "Identificador de verificación" |

En tu PC van en el archivo `.env` (ver `env.example`). En el servidor se configuran en el panel (Render: *Environment*; Azure: *Configuración → Variables de entorno*).

## Correr en tu PC

```
py -m pip install -r requirements.txt
py app.py
```
Prueba: http://localhost:5000/welcome

## Desplegar en Render

1. New → Web Service → elegir este repositorio.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Environment: agregar `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`.

## Desplegar en Azure App Service (Linux, Python)

- Variable `SCM_DO_BUILD_DURING_DEPLOYMENT=true` y las tres variables de arriba.
- Comando de inicio: `gunicorn --bind=0.0.0.0 --timeout 600 app:app`

## Webhook en Meta

- URL de devolución de llamada: `https://TU-URL/whatsapp`
- Identificador de verificación: el valor de `WA_VERIFY_TOKEN`
- Suscribir el campo `messages`.

## Probar sin WhatsApp

Enviar `TextModel.json` o `ButtonModel.json` como body (POST, JSON) a `/whatsapp`.
