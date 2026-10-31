#!/usr/bin/env python3
"""
api_gateway.py v2 - Puente HTTP entre la UI y ReActAgent.
Puerto 5001. NO toca server.py ni sus rutas Socket.IO.
Solo escucha en 127.0.0.1 — el agente ejecuta comandos: NUNCA exponer a la red.
v2: codigos HTTP reales (200/400/500/503) + acepta campo opcional "history".
"""
from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from assistant import ReActAgent
except Exception as e:
    print(f"[GATEWAY] ERROR importando assistant: {e}")
    raise SystemExit(1)

print("[GATEWAY] Instanciando ReActAgent() ...")
AGENTE = ReActAgent()
AGENTE_LISTO = True
print("[GATEWAY] Agente listo.")

app = Flask(__name__)
CORS(app)


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "agente": "listo"})


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True, silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Cuerpo JSON invalido"}), 400   # peticion malformada

    mensaje = (data.get('message') or '').strip()
    history = data.get('history') or []

    if not mensaje:
        return jsonify({"error": "Campo 'message' vacio"}), 400
    if history:
        print(f"[GATEWAY] history recibido ({len(history)} msgs) — "
              f"por ahora el agente usa su memoria interna")

    if not AGENTE_LISTO:
        return jsonify({"error": "Agente no disponible"}), 503   # agente caido

    try:
        resultado = AGENTE.process(mensaje)
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500  # fallo del agente

    if isinstance(resultado, tuple):
        respuesta = resultado[0] if resultado else ""
        acciones = resultado[1] if len(resultado) > 1 else []
    else:
        respuesta, acciones = resultado, []

    respuesta = str(respuesta or "").strip()
    if not respuesta:
        return jsonify({"error": "El agente devolvio respuesta vacia"}), 500

    return jsonify({                                             # 200: exito
        "response": respuesta,
        "acciones": acciones if isinstance(acciones, list) else [],
    })


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)
