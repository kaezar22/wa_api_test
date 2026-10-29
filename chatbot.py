"""
Chatbot de ventas de prueba (Nutrienti) usando DeepSeek.

- El catálogo, los precios y las reglas de entrega están en catalogo.json.
- Los TOTALES y las FECHAS los calcula Python (función cotizar_pedido), no el modelo,
  para que no se inventen precios ni hagan mal las cuentas.
- Memoria: historial corto por número de WhatsApp, en memoria (se pierde si Render reinicia).

Variables de entorno:
  DEEPSEEK_API_KEY   (obligatoria para usar el chatbot)
  DEEPSEEK_MODEL     (opcional, por defecto "deepseek-chat")
  DEEPSEEK_BASE_URL  (opcional, por defecto "https://api.deepseek.com")
"""
import json
import os
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

CARPETA = Path(__file__).parent
CATALOGO = json.loads((CARPETA / "catalogo.json").read_text(encoding="utf-8"))

BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
MAX_TURNOS = 12          # mensajes de historial que se le pasan al modelo
EXPIRA_SEGUNDOS = 2 * 3600  # si el cliente no escribe en 2 h, se olvida la conversación
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

_memoria = {}  # numero -> {"t": timestamp, "mensajes": [...]}
_lock = threading.Lock()


def habilitado():
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


# ----------------------------------------------------------------------------
# Lógica de negocio (Python, no el modelo)
# ----------------------------------------------------------------------------
def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in texto if not unicodedata.combining(c)).strip()


def _buscar_producto(nombre):
    objetivo = _normalizar(nombre)
    mejor, puntaje = None, 0.0
    for p in CATALOGO["productos"]:
        candidato = _normalizar(p["producto"])
        s = 1.0 if objetivo == candidato else SequenceMatcher(None, objetivo, candidato).ratio()
        if objetivo in candidato or candidato in objetivo:
            s = max(s, 0.9)
        if s > puntaje:
            mejor, puntaje = p, s
    return mejor if puntaje >= 0.75 else None


def fecha_entrega(ahora=None):
    reglas = CATALOGO["entrega"]
    ahora = ahora or datetime.now(BOGOTA)
    dias = reglas["dias_si_antes_del_corte"] if ahora.hour < reglas["hora_corte"] else reglas["dias_si_despues_del_corte"]
    festivos = set(reglas.get("festivos", []))
    sin_entrega = {_normalizar(d) for d in reglas.get("dias_sin_entrega", [])}
    fecha = ahora.date()
    while dias > 0:
        fecha += timedelta(days=1)
        if _normalizar(DIAS[fecha.weekday()]) in sin_entrega or fecha.isoformat() in festivos:
            continue
        dias -= 1
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


def _pesos(valor):
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


def cotizar_pedido(items):
    lineas, no_encontrados, subtotal = [], [], 0
    for it in items or []:
        prod = _buscar_producto(it.get("producto", ""))
        try:
            cantidad = max(1, int(float(it.get("cantidad", 1))))
        except (TypeError, ValueError):
            cantidad = 1
        if not prod:
            no_encontrados.append(it.get("producto", ""))
            continue
        total_linea = prod["precio"] * cantidad
        subtotal += total_linea
        lineas.append({
            "producto": prod["producto"], "unidad": prod["unidad"], "cantidad": cantidad,
            "precio_unitario": _pesos(prod["precio"]), "total": _pesos(total_linea),
        })
    domicilio = 0 if subtotal >= CATALOGO["domicilio_gratis_desde"] else CATALOGO["costo_domicilio"]
    return {
        "lineas": lineas,
        "no_encontrados": no_encontrados,
        "subtotal": _pesos(subtotal),
        "domicilio": _pesos(domicilio) if subtotal else _pesos(0),
        "total": _pesos(subtotal + domicilio) if subtotal else _pesos(0),
        "cumple_pedido_minimo": subtotal >= CATALOGO["pedido_minimo"],
        "pedido_minimo": _pesos(CATALOGO["pedido_minimo"]),
        "fecha_entrega_estimada": fecha_entrega(),
    }


HERRAMIENTAS = [{
    "type": "function",
    "function": {
        "name": "cotizar_pedido",
        "description": "Calcula precios, subtotal, domicilio, total y fecha estimada de entrega de un pedido. "
                       "Úsala SIEMPRE que el cliente pida precios de varios productos, un total o una cotización.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "producto": {"type": "string", "description": "Nombre del producto tal como está en el catálogo"},
                            "cantidad": {"type": "integer", "description": "Número de unidades (bolsas, atados, cajas…)"},
                        },
                        "required": ["producto", "cantidad"],
                    },
                }
            },
            "required": ["items"],
        },
    },
}]


def _prompt_sistema():
    lista = "\n".join(f"- {p['producto']} ({p['unidad']}): {_pesos(p['precio'])}" for p in CATALOGO["productos"])
    e = CATALOGO["entrega"]
    return f"""Eres el asistente de ventas por WhatsApp de Nutrienti, una empresa colombiana de hortalizas y verduras frescas.
Hablas en español de Colombia, con tono cálido, breve y profesional. Mensajes cortos (es WhatsApp), sin tablas.

CATÁLOGO (únicos productos y precios válidos, en pesos colombianos):
{lista}

REGLAS DE NEGOCIO:
- Pedido mínimo: {_pesos(CATALOGO['pedido_minimo'])}.
- Domicilio: {_pesos(CATALOGO['costo_domicilio'])}; gratis para pedidos desde {_pesos(CATALOGO['domicilio_gratis_desde'])}.
- Pedidos antes de las {e['hora_corte']}:00 se entregan en {e['dias_si_antes_del_corte']} día hábil; después, en {e['dias_si_despues_del_corte']} días hábiles. No hay entregas los domingos ni festivos.
- Fecha estimada de entrega si piden hoy: {fecha_entrega()}.

CÓMO RESPONDER:
- Para cotizar varios productos o dar un total, usa SIEMPRE la herramienta cotizar_pedido. Nunca calcules totales tú mismo.
- Si piden algo que no está en el catálogo, dilo con amabilidad y sugiere lo más parecido que sí haya.
- Nunca inventes productos, precios, descuentos ni promociones.
- Al cotizar, muestra cada producto con cantidad y valor, el domicilio, el total y la fecha estimada de entrega.
- Si no se cumple el pedido mínimo, avísalo y sugiere completar.
- Al final de una cotización pregunta si desea confirmar el pedido. Si confirma, pide nombre del negocio y dirección de entrega,
  y aclara que un asesor de Nutrienti lo contactará para finalizar (todavía no puedes registrar pedidos).
- Si preguntan algo que no tiene que ver con productos, precios o entregas, responde que un asesor lo puede ayudar.
- Usa *negrita* de WhatsApp con moderación (un asterisco a cada lado)."""


# ----------------------------------------------------------------------------
# Llamada a DeepSeek
# ----------------------------------------------------------------------------
def _llamar_deepseek(mensajes):
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
        json={
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": mensajes,
            "tools": HERRAMIENTAS,
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_tokens": 700,
        },
        timeout=45,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]


def _historial(numero):
    with _lock:
        entrada = _memoria.get(numero)
        if not entrada or time.time() - entrada["t"] > EXPIRA_SEGUNDOS:
            entrada = {"t": time.time(), "mensajes": []}
            _memoria[numero] = entrada
        return entrada


def responder(numero, texto, nombre=None):
    """Devuelve el texto que el bot debe enviar al cliente."""
    entrada = _historial(numero)
    entrada["mensajes"].append({"role": "user", "content": texto})
    sistema = _prompt_sistema()
    if nombre:
        sistema += f"\nEl cliente se llama {nombre} en WhatsApp."
    mensajes = [{"role": "system", "content": sistema}] + entrada["mensajes"][-MAX_TURNOS:]

    try:
        for _ in range(3):  # máximo 3 rondas de herramientas
            msg = _llamar_deepseek(mensajes)
            llamadas = msg.get("tool_calls") or []
            if not llamadas:
                respuesta = (msg.get("content") or "").strip()
                break
            mensajes.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": llamadas})
            for llamada in llamadas:
                try:
                    args = json.loads(llamada["function"].get("arguments") or "{}")
                    resultado = cotizar_pedido(args.get("items", [])) if llamada["function"]["name"] == "cotizar_pedido" \
                        else {"error": "herramienta desconocida"}
                except Exception as e:  # argumentos mal formados
                    resultado = {"error": str(e)}
                print("Herramienta:", llamada["function"]["name"], json.dumps(resultado, ensure_ascii=False))
                mensajes.append({"role": "tool", "tool_call_id": llamada["id"],
                                 "content": json.dumps(resultado, ensure_ascii=False)})
        else:
            respuesta = ""
    except Exception as e:
        print("Error chatbot:", e)
        entrada["mensajes"].pop()  # no guardar un turno que falló
        return "Disculpa, tuve un problema técnico. ¿Me repites tu mensaje en un momento? 🙏"

    respuesta = respuesta or "¿Me cuentas qué productos te interesan? Con gusto te cotizo."
    with _lock:
        entrada["mensajes"].append({"role": "assistant", "content": respuesta})
        entrada["mensajes"] = entrada["mensajes"][-MAX_TURNOS:]
        entrada["t"] = time.time()
    return respuesta[:4000]  # límite de WhatsApp: 4096 caracteres
