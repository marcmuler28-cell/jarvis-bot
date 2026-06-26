import os
import requests
import json
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from database import MemoryManager
from skills.blackboard_skill import BlackboardSkill

app = Flask(__name__)

db = MemoryManager()
skill = BlackboardSkill(db_manager=db)

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
OLLAMA_MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"


def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    print("Envío:", response.json())
    return response


def guardar_chat(sender, message, response):
    db.execute(
        "INSERT INTO chat_logs (timestamp, sender, message, response) VALUES (?, ?, ?, ?)",
        (datetime.now(), sender, message, response)
    )


def interpretar_pedido(mensaje):
    prompt = f"""Eres un asistente que extrae pedidos de mensajes informales de WhatsApp.
El cliente a menudo se corrige a sí mismo o descarta opciones. Debes aplicar reglas lógicas estrictas de negocio.

Reglas de negocio obligatorias:
1. **Descarte de productos/marcas**: Si el cliente dice frases como "no aguanta", "mejor no", "olvídalo", "me equivoqué", "no quiero ese", descarta completamente esa opción. Solo conserva en el campo 'producto' la decisión final del cliente. Enfócate en la última opción válida mencionada después del descarte.
2. **Presupuesto real vs regateo**: El campo 'precio_max' debe reflejar el "presupuesto total" o "límite máximo" que el cliente declara explícitamente. Ignora frases condicionales como "si me lo dejas a menos de X" para fijar el precio máximo; esas son ofertas de regateo, no el presupuesto real. El presupuesto real suele ir acompañado de frases como "mi presupuesto es de", "tengo hasta", "máximo tengo", "no me paso de".
3. **Método de entrega**: Si el cliente cambia de opinión sobre cómo recibir el pedido (recojo vs delivery), quédate con la última indicación. Si dice "coordinamos delivery... o mejor voy yo a recogerlo", el método final es "Recojo en tienda". Si dice "envíamelo... o mejor paso a recoger", igual. Siempre la última decisión.
4. **Fecha de entrega/recojo**: Si el cliente propone una fecha y luego la corrige, usa la última. Si no se concreta (ej. "coordinamos por WhatsApp"), pon "Por coordinar". Si es recojo y se indica día, pon ese día.
5. **Descripción**: Solo un resumen de una línea (máx. 20 palabras) indicando la acción principal, sin repetir datos de otros campos.

Formato JSON requerido:
- "tipo": "pedido" (si es una compra), "tarea", "recordatorio", etc.
- "producto": nombre del producto final (solo las marcas/modelos aceptados, sin los descartados).
- "descripcion": resumen ejecutivo breve.
- "precio_max": número (presupuesto real) o null.
- "cliente": nombre del cliente (si aparece).
- "dni": DNI (solo números, sin puntos ni espacios) o null.
- "urgencia": "alta", "media", "baja".
- "metodo_entrega": "Recojo en tienda" o "Delivery" (según última decisión).
- "fecha_entrega": fecha concreta o "Por coordinar" o null.
- "canal_coordinacion": "WhatsApp", "Teléfono", etc. o null.
- "direccion": dirección de envío o tienda de recojo, o null.
- "responsable": null.

Ejemplo:
Mensaje: "necesito una laptop gamer core i7 15 pulgadas lenovo... no aguanta mejor una hp victus o asus tuf de 16 pulgadas. tengo presupuesto 3500 soles pero si me lo dejas a menos de 3000 te compro ya. coordinamos delivery... mejor voy yo a recogerlo el viernes en la mañana. me llamo gabriel contreras"
Respuesta: {{"tipo": "pedido", "producto": "HP Victus o ASUS TUF 16 pulgadas", "descripcion": "Verificar stock y separar para recojo", "precio_max": 3500, "cliente": "Gabriel Contreras", "dni": null, "urgencia": "alta", "metodo_entrega": "Recojo en tienda", "fecha_entrega": "viernes en la mañana", "canal_coordinacion": null, "direccion": null, "responsable": null}}

Mensaje: {mensaje}
"""
    try:
        respuesta = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0}
            },
            timeout=90
        )
        data = respuesta.json()
        texto = data.get("response", "").strip()
        inicio = texto.find("{")
        fin = texto.rfind("}") + 1
        if inicio != -1 and fin > inicio:
            json_str = texto[inicio:fin]
            return json.loads(json_str)
        else:
            raise ValueError("No se encontró JSON en la respuesta")
    except Exception as e:
        print("Error con Ollama:", e)
        return None


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Error de verificación", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    print("JSON RECIBIDO:", data)
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" not in value:
                    continue
                for message in value["messages"]:
                    if message["type"] != "text":
                        continue
                    msg_id = message["id"]
                    try:
                        db.execute("INSERT INTO processed_messages (message_id) VALUES (%s)", (msg_id,))
                    except Exception:
                        continue

                    user_msg = message["text"]["body"].strip().lower()
                    sender = message["from"]

                    entidades = interpretar_pedido(user_msg)

                    if not entidades:
                        entidades = {
                            "tipo": "tarea",
                            "descripcion": user_msg,
                            "producto": None,
                            "precio_max": None,
                            "cliente": None,
                            "dni": None,
                            "urgencia": "media",
                            "metodo_entrega": None,
                            "fecha_entrega": None,
                            "canal_coordinacion": None,
                            "direccion": None,
                            "responsable": None
                        }

                    db.execute(
                        "INSERT INTO tareas (sender, tipo, descripcion, fecha_hora, responsable, prioridad) VALUES (?, ?, ?, ?, ?, ?)",
                        (sender, entidades.get("tipo", "tarea"), entidades.get("descripcion", user_msg),
                         entidades.get("fecha_entrega", "") or "", entidades.get("responsable", "") or "",
                         entidades.get("urgencia", "media"))
                    )

                    if entidades.get("producto") or entidades.get("cliente"):
                        db.save_extracted_entities(sender, msg_id, entidades)
                    else:
                        print("Extracción insuficiente, no se guardó en extracted_entities.")

                    respuesta = "✅ Pedido registrado:\n"
                    if entidades.get("producto"):
                        respuesta += f"📦 Producto: {entidades['producto']}\n"
                    if entidades.get("precio_max"):
                        respuesta += f"💰 Precio máx: S/ {entidades['precio_max']}\n"
                    if entidades.get("cliente"):
                        respuesta += f"👤 Cliente: {entidades['cliente']}\n"
                    if entidades.get("dni"):
                        respuesta += f"🆔 DNI: {entidades['dni']}\n"
                    if entidades.get("metodo_entrega"):
                        respuesta += f"🚚 Método: {entidades['metodo_entrega']}\n"
                    if entidades.get("fecha_entrega"):
                        respuesta += f"📅 Entrega: {entidades['fecha_entrega']}\n"
                    if entidades.get("canal_coordinacion"):
                        respuesta += f"📞 Coordinar por: {entidades['canal_coordinacion']}\n"
                    if entidades.get("direccion"):
                        respuesta += f"📍 Dirección: {entidades['direccion']}\n"
                    respuesta += f"⚡ Urgencia: {entidades.get('urgencia', 'media')}"

                    send_whatsapp_message(sender, respuesta)
                    guardar_chat(sender, user_msg, respuesta)
    except Exception as e:
        print("Error procesando mensaje:", e)
    return jsonify({"status": "ok"}), 200


# Dashboard con datos estructurados
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JarvisBot - Pedidos Estructurados</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; padding: 20px; }
        h1 { color: #1a73e8; margin-bottom: 20px; font-size: 1.5em; }

        .filtros {
            display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;
        }
        .filtros button {
            padding: 8px 16px; border: none; border-radius: 20px;
            background: #e0e0e0; cursor: pointer; font-weight: bold;
            transition: all 0.2s;
        }
        .filtros button.activo { background: #1a73e8; color: white; }

        .task-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 16px;
        }

        .task-card {
            background: white; border-radius: 12px; padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1); position: relative;
            overflow: hidden; transition: transform 0.15s;
        }
        .task-card:hover { transform: translateY(-2px); }

        .barra-prioridad {
            height: 4px; border-radius: 2px; margin-bottom: 12px;
            transition: background 0.3s;
        }
        .barra-alta { background: #e53935; }
        .barra-media { background: #fdd835; }
        .barra-baja { background: #43a047; }

        .task-header {
            display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
        }
        .icono-tipo {
            font-size: 1.6em; width: 40px; height: 40px;
            display: flex; align-items: center; justify-content: center;
            border-radius: 10px; background: #e8eaf6;
        }
        .tipo-badge {
            font-size: 0.75em; padding: 3px 10px; border-radius: 12px;
            background: #e8eaf6; color: #1a237e; font-weight: bold;
            text-transform: uppercase; letter-spacing: 0.5px;
        }

        .descripcion {
            font-size: 0.95em; color: #333; margin-bottom: 12px;
            line-height: 1.4;
        }

        .task-meta {
            display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;
        }
        .meta-item {
            font-size: 0.8em; padding: 4px 10px; border-radius: 8px;
            background: #f5f5f5; color: #555; display: flex; align-items: center; gap: 4px;
        }

        .task-footer {
            display: flex; justify-content: space-between; align-items: center;
            font-size: 0.75em; color: #999; border-top: 1px solid #eee; padding-top: 10px;
        }
        .sender-tag { background: #e3f2fd; color: #1565c0; padding: 2px 8px; border-radius: 6px; }

        .no-tasks {
            text-align: center; color: #999; padding: 40px; font-size: 1.1em;
            grid-column: 1 / -1;
        }
    </style>
</head>
<body>
    <h1>📦 Pedidos Registrados (Datos Estructurados)</h1>

    <div class="filtros">
        <button class="activo" data-filtro="todas">Todas</button>
        <button data-filtro="alta">🔴 Alta</button>
        <button data-filtro="media">🟡 Media</button>
        <button data-filtro="baja">🟢 Baja</button>
    </div>

    <div class="task-grid" id="taskGrid"></div>

    <script>
        const prioridadBarra = { alta: 'barra-alta', media: 'barra-media', baja: 'barra-baja' };

        async function cargarTareas() {
            const resp = await fetch('/api/entidades');
            const tareas = await resp.json();
            const grid = document.getElementById('taskGrid');
            const filtroActivo = document.querySelector('.filtros .activo')?.dataset?.filtro || 'todas';

            const filtradas = filtroActivo === 'todas'
                ? tareas
                : tareas.filter(t => (t.urgencia || 'media').toLowerCase() === filtroActivo);

            if (filtradas.length === 0) {
                grid.innerHTML = '<div class="no-tasks">✨ No hay pedidos con este filtro</div>';
                return;
            }

            grid.innerHTML = filtradas.map(t => {
                const urgencia = (t.urgencia || 'media').toLowerCase();
                const barraClass = prioridadBarra[urgencia] || 'barra-media';
                const icono = '📦';
                const metodo = t.metodo_entrega || '—';
                const entrega = t.fecha_entrega || '—';
                const coordinacion = t.canal_coordinacion ? ` (coordinar por ${t.canal_coordinacion})` : '';

                return `
                    <div class="task-card">
                        <div class="barra-prioridad ${barraClass}"></div>
                        <div class="task-header">
                            <div class="icono-tipo">${icono}</div>
                            <span class="tipo-badge">pedido</span>
                        </div>
                        <div class="descripcion">
                            <strong>Producto:</strong> ${t.producto || '—'}<br>
                            <strong>Cliente:</strong> ${t.cliente || '—'} ${t.dni ? '(' + t.dni + ')' : ''}<br>
                            <strong>Precio máx:</strong> ${t.precio_max ? 'S/ ' + t.precio_max : '—'}<br>
                            <strong>Método:</strong> ${metodo}<br>
                            <strong>Entrega:</strong> ${entrega}${coordinacion}<br>
                            <strong>Dirección:</strong> ${t.direccion || '—'}
                        </div>
                        <div class="task-meta">
                            <span class="meta-item">🏷 ${urgencia}</span>
                        </div>
                        <div class="task-footer">
                            <span class="sender-tag">${t.sender || '?'}</span>
                            <span>${t.timestamp || ''}</span>
                        </div>
                    </div>
                `;
            }).join('');
        }

        document.querySelectorAll('.filtros button').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filtros button').forEach(b => b.classList.remove('activo'));
                btn.classList.add('activo');
                cargarTareas();
            });
        });

        cargarTareas();
        setInterval(cargarTareas, 5000);
    </script>
</body>
</html>
"""


@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_TEMPLATE)


@app.route("/api/tareas")
def get_tareas():
    rows = db.query("SELECT timestamp, sender, tipo, descripcion, fecha_hora, responsable, prioridad FROM tareas ORDER BY timestamp DESC LIMIT 50")
    tareas = []
    for r in rows:
        tareas.append({
            "timestamp": r[0],
            "sender": r[1],
            "tipo": r[2],
            "descripcion": r[3],
            "fecha_hora": r[4] or "",
            "responsable": r[5] or "",
            "prioridad": r[6]
        })
    return jsonify(tareas)


@app.route("/api/chat_logs")
def get_chat_logs():
    rows = db.query("SELECT timestamp, sender, message, response FROM chat_logs ORDER BY timestamp DESC LIMIT 50")
    logs = []
    for r in rows:
        logs.append({
            "timestamp": r[0],
            "sender": r[1],
            "message": r[2],
            "response": r[3]
        })
    return jsonify(logs)


@app.route("/api/entidades")
def get_entidades():
    rows = db.query("""
        SELECT id, sender, producto, precio_max, cliente, dni, urgencia, 
               metodo_entrega, fecha_entrega, canal_coordinacion, direccion,
               timestamp, 
               JSON_EXTRACT(extracted_json, '$.descripcion') as descripcion
        FROM extracted_entities 
        ORDER BY timestamp DESC 
        LIMIT 50
    """)
    resultado = []
    for r in rows:
        resultado.append({
            "id": r[0],
            "sender": r[1],
            "producto": r[2],
            "precio_max": float(r[3]) if r[3] else None,
            "cliente": r[4],
            "dni": r[5],
            "urgencia": r[6],
            "metodo_entrega": r[7],
            "fecha_entrega": r[8],
            "canal_coordinacion": r[9],
            "direccion": r[10],
            "timestamp": r[11].strftime("%Y-%m-%d %H:%M:%S") if r[11] else "",
            "descripcion": r[12]
        })
    return jsonify(resultado)


if __name__ == "__main__":
    app.run(port=5001, debug=True)