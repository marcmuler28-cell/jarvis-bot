# server.py - Modified backend to expose API for UI

print("Starting Jarvis server...")
import os
from datetime import datetime
import time
import threading
from flask import Flask
from flask_socketio import SocketIO, emit
from assistant import ReActAgent
from ui import VoiceInterface
from config import MODEL_FAST, MODEL_POWERFUL
from agent import AgentCore

# === Sistema de autenticación por voz ===
try:
    from auth_integration import get_auth, detect_action_from_input, check_action_permission
    AUTH_AVAILABLE = True
    print("[SERVER] Sistema de autenticación disponible")
except ImportError as e:
    AUTH_AVAILABLE = False
    print(f"[SERVER] ⚠️  Sistema de autenticación no disponible: {e}")

app = Flask(__name__)
from flask import send_from_directory
import os

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'jarvis_ai_voice_interface.html')

@app.route('/button')
def button():
    """Sirve el HTML del botón flotante (ventana separada)."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'walkie_button.html')

@app.route('/dashboard')
def dashboard():
    """Sirve el HTML del Dashboard de informes."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')

@app.route('/api/dashboard')
def api_dashboard():
    """Retorna JSON con todos los datos del asistente para el Dashboard."""
    import json as _json
    import psutil

    data = {
        'timestamp': _json.dumps(datetime.now().isoformat()),
        'health': {},
        'system': {},
        'session': {},
        'game': {},
        'triggers': [],
        'recent': [],
    }

    # 1. Health report
    try:
        if hasattr(agent, 'health'):
            data['health'] = {
                'uptime_minutes': round(agent.health.get_uptime() / 60, 1),
                'total_requests': agent.health.stats.get('total_requests', 0),
                'fast_path_hits': agent.health.stats.get('fast_path_hits', 0),
                'llm_calls': agent.health.stats.get('llm_calls', 0),
                'parse_retries': agent.health.stats.get('parse_retries', 0),
                'actions_executed': agent.health.stats.get('actions_executed', 0),
                'actions_failed': agent.health.stats.get('actions_failed', 0),
            }
            if data['health']['llm_calls'] > 0:
                data['health']['avg_llm_time'] = round(
                    agent.health.stats.get('llm_total_time', 0) / data['health']['llm_calls'], 2
                )
            else:
                data['health']['avg_llm_time'] = 0
    except Exception as e:
        data['health']['error'] = str(e)

    # 2. System info (CPU, RAM, Disk)
    try:
        data['system'] = {
            'cpu_percent': psutil.cpu_percent(interval=0.5),
            'cpu_count': psutil.cpu_count(),
            'ram_percent': psutil.virtual_memory().percent,
            'ram_used_gb': round(psutil.virtual_memory().used / (1024**3), 1),
            'ram_total_gb': round(psutil.virtual_memory().total / (1024**3), 1),
            'disk_percent': psutil.disk_usage('/').percent,
            'disk_used_gb': round(psutil.disk_usage('/').used / (1024**3), 1),
            'disk_total_gb': round(psutil.disk_usage('/').total / (1024**3), 1),
        }
    except Exception as e:
        data['system']['error'] = str(e)

    # 3. Session info
    try:
        if auth:
            info = auth.get_session_info()
            if info:
                data['session'] = {
                    'user_id': info['user_id'],
                    'display_name': auth.get_user_display(info['user_id']),
                    'confidence': round(info['confidence'], 3),
                    'remaining_minutes': round(info['remaining_seconds'] / 60, 1),
                    'elapsed_minutes': round(info['elapsed_seconds'] / 60, 1),
                }
            else:
                data['session'] = {'user_id': None, 'display_name': 'No autenticado'}
    except Exception as e:
        data['session']['error'] = str(e)

    # 4. Game time stats
    try:
        if auth and auth.game_monitor:
            current_user = auth.get_current_user()
            if current_user:
                stats = auth.game_monitor.get_user_stats(current_user)
                data['game'] = stats
    except Exception as e:
        data['game']['error'] = str(e)

    # 5. Triggers (scheduled actions)
    try:
        if hasattr(agent, 'agent_core') and agent.agent_core:
            data['triggers'] = agent.agent_core.triggers[:10]  # últimos 10
    except Exception as e:
        data['triggers'] = []

    # 6. Recent interactions (from memory)
    try:
        if hasattr(agent, 'memory'):
            recent = agent.memory.get_recent_interactions(5) if hasattr(agent.memory, 'get_recent_interactions') else []
            data['recent'] = recent
    except Exception as e:
        data['recent'] = []

    return _json.dumps(data, ensure_ascii=False, default=str)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

agent = ReActAgent(MODEL_FAST, MODEL_POWERFUL)
print("Modelos cargados exitosamente")
voice = VoiceInterface()
print("VoiceInterface inicializada")

# ─────────────────────────────────────────────
# Inicializar el núcleo de agentes (triggers, hábitos, etc.)
# ─────────────────────────────────────────────
agent.agent_core = AgentCore(
    tools=agent.tools,
    memory=agent.memory,
    health=agent.health,
    voice=voice,
    skills=agent.skills,
    llm=agent.llm_fast
)

# ─────────────────────────────────────────────
# Inicializar sistema de autenticación por voz
# ─────────────────────────────────────────────
auth = None
if AUTH_AVAILABLE:
    try:
        auth = get_auth()
        auth.initialize(enable_voice_id=False, enable_game_monitor=True)
        # Iniciar auto-monitor de juegos en background
        auth.start_auto_monitor(
            interval_seconds=60,
            broadcast_callback=lambda msg_type, text: broadcast_message(msg_type, text)
        )
    except Exception as e:
        print(f"[SERVER] ⚠️  Auth no inicializado: {e}")
        auth = None

# ─────────────────────────────────────────────
# Hilo 1: Análisis de hábitos (máx. 1 vez al día)
# ─────────────────────────────────────────────
def delayed_habit_analysis():
    """Espera unos segundos y analiza hábitos si corresponde (máx. 1 vez al día)."""
    time.sleep(5)   # Dar tiempo a que el TTS y el servidor estén completamente listos
    last_proposal_file = os.path.expanduser("~/.jarvis/last_proposal.txt")
    now = time.time()
    try:
        if not os.path.exists(last_proposal_file) or now - os.path.getmtime(last_proposal_file) > 86400:
            agent.agent_core.analyze_habits_and_propose()
            # Actualizar la marca de tiempo
            with open(last_proposal_file, 'w') as f:
                f.write(str(int(now)))
    except Exception as e:
        print(f"Error en análisis de hábitos diferido: {e}")

threading.Thread(target=delayed_habit_analysis, daemon=True).start()

# ─────────────────────────────────────────────
# Hilo 2: Evaluación periódica de triggers (cada 30 s)
# ─────────────────────────────────────────────
def trigger_loop():
    """Evalúa los triggers cada 30 segundos."""
    while True:
        try:
            agent.agent_core.check_triggers()
            # Verificar límites de juego también
            if auth:
                auth.check_game_limits(broadcast_callback=lambda msg_type, text: broadcast_message(msg_type, text))
        except Exception as e:
            print(f"[TRIGGER LOOP] Error: {e}")
        time.sleep(30)

threading.Thread(target=trigger_loop, daemon=True).start()

# ─────────────────────────────────────────────
# Estado global y funciones de broadcast
# ─────────────────────────────────────────────
current_status = 'inactivo'
walkie_active = False
walkie_lock = threading.Lock()

def broadcast_status(status_val):
    """Broadcast status to all connected clients."""
    with app.app_context():
        socketio.emit('status', {'status': status_val})

def broadcast_message(msg_type, text):
    """Broadcast message to all connected clients."""
    with app.app_context():
        socketio.emit('message', {'type': msg_type, 'text': text})

def voice_loop():
    global current_status, walkie_active
    # Tras reinicio: deja tiempo a PipeWire y al TTS (edge-tts + mpv).
    time.sleep(3)
    current_user = None  # Variable global de sesión, se actualiza al identificar voz
    try:
        print("Reproduciendo saludo inicial de voz…", flush=True)
        voice.speak("Jarvis en línea. Usa el botón Pulsar para Hablar en la interfaz.")
    except Exception as e:
        print(f"Saludo inicial no reproducido: {e}", flush=True)
    while True:
        with walkie_lock:
            wt = walkie_active
        
        if wt:
            current_status = 'escuchando'
            broadcast_status(current_status)
            print(f"[WALKIE] Escuchando...", flush=True)
            t0 = time.time()
            # voice.listen() ahora devuelve (texto, wav_path)
            temp_wav = None
            try:
                result = voice.listen(timeout=4)
                # Desempacar tupla de forma segura
                if isinstance(result, tuple) and len(result) >= 1:
                    user_input = result[0]
                    if len(result) >= 2 and result[1]:
                        temp_wav = result[1]
                else:
                    user_input = result
            except Exception as e:
                print(f"[WALKIE] Error escuchando: {e}", flush=True)
                socketio.emit('listen_error', {'error': str(e)[:200]})
                user_input = None
                temp_wav = None
                with walkie_lock:
                    walkie_active = False
                    current_status = 'inactivo'
                broadcast_status(current_status)
                continue
            t1 = time.time()
            print(f"[WALKIE] {t1-t0:.2f}s -> '{user_input}'", flush=True)

            # === Sesión manejada por PIN ===
            # Ya no intentamos identificar la voz en cada comando
            if auth:
                current_user = auth.get_current_user()
            
            # Limpiar WAV temporal si existe
            if 'temp_wav' in locals() and temp_wav and os.path.exists(temp_wav):
                try:
                    os.unlink(temp_wav)
                except:
                    pass

            if user_input:
                current_status = 'procesando'
                broadcast_status(current_status)
                broadcast_message('user', user_input)
                print(f"[WALKIE] User: {user_input}", flush=True)
                
                t2 = time.time()
                # Verificar permisos antes de ejecutar
                if auth and current_user is not None:
                    action = detect_action_from_input(user_input)
                    allowed, deny_msg = auth.check_permission(current_user, action)
                    if not allowed:
                        respuesta = deny_msg
                        acciones = []
                        print(f"[AUTH] ❌ Permiso denegado: {deny_msg}", flush=True)
                        t3 = time.time()
                        # Saltar al bloque que envía la respuesta
                        current_status = 'hablando'
                        broadcast_status(current_status)
                        broadcast_message('assistant', respuesta)
                        socketio.emit('command_result', {
                            'command': user_input,
                            'response': respuesta[:120],
                            'success': False
                        })
                        print(f"[WALKIE] Assistant: {respuesta}", flush=True)
                        t4 = time.time()
                        voice.speak(respuesta)
                        t5 = time.time()
                        print(f"[⏱ SPEAK] {t5-t4:.2f}s", flush=True)
                        with walkie_lock:
                            if not walkie_active:
                                current_status = 'inactivo'
                            else:
                                current_status = 'escuchando'
                        broadcast_status(current_status)
                        continue

                # Si permitido o no hay auth, ejecutar normalmente
                respuesta, acciones = agent.process(user_input)
                t3 = time.time()
                print(f"[⏱️ PROCESS] {t3-t2:.2f}s", flush=True)
                
                current_status = 'hablando'
                broadcast_status(current_status)
                broadcast_message('assistant', respuesta)
                socketio.emit('command_result', {
                    'command': user_input,
                    'response': respuesta[:120],
                    'success': True
                })
                # Emitir notificación nativa de KDE
                socketio.emit('notification', {
                    'title': 'JarvisBot',
                    'message': respuesta[:100],
                    'type': 'success'
                })
                print(f"[WALKIE] Assistant: {respuesta}", flush=True)
                
                t4 = time.time()
                voice.speak(respuesta)
                t5 = time.time()
                print(f"[⏱️ SPEAK] {t5-t4:.2f}s", flush=True)
                
                with walkie_lock:
                    if not walkie_active:
                        current_status = 'inactivo'
                    else:
                        current_status = 'escuchando'
                broadcast_status(current_status)
            else:
                with walkie_lock:
                    if not walkie_active:
                        current_status = 'inactivo'
                broadcast_status(current_status)
        else:
            # En reposo, solo esperar sin consumir recursos
            time.sleep(0.3)

# ─────────────────────────────────────────────
# Eventos de Socket.IO
# ─────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    print("Cliente Socket.IO conectado")
    emit('status', {'status': current_status})
    
    # Enviar estado de la sesión al botón flotante
    if auth:
        user = auth.get_current_user()
        if user:
            emit('login_result', {
                'success': True,
                'message': 'Sesión restaurada',
                'user_id': user,
                'display_name': auth.get_user_display(user)
            })
        else:
            # No hay sesión activa, pedir PIN
            emit('login_result', {'success': False, 'message': 'No hay sesión activa'})
    else:
        emit('login_result', {'success': False, 'message': 'Auth no disponible'})

@socketio.on('client_ready')
def handle_client_ready():
    print("Cliente listo recibid0")
    emit('status', {'status': current_status})

@socketio.on('disconnect')
def handle_disconnect():
    print("Cliente Socket.IO desconectado")

@socketio.on('walkie_talkie_start')
def handle_walkie_start():
    global walkie_active, current_status
    with walkie_lock:
        walkie_active = True
        current_status = 'escuchando'
    broadcast_status(current_status)
    print("[WALKIE] Botón pulsado — escuchando...", flush=True)

@socketio.on('walkie_talkie_stop')
def handle_walkie_stop():
    global walkie_active, current_status
    with walkie_lock:
        walkie_active = False
        current_status = 'inactivo'
    broadcast_status(current_status)
    print("[WALKIE] Botón soltado — modo inactivo", flush=True)

@socketio.on('new_conversation')
def handle_new_conversation():
    # Reset conversation if needed
    pass

@socketio.on('clear_history')
def handle_clear_history():
    # Clear history logic
    pass


@socketio.on('login_pin')
def handle_login_pin(data):
    global auth
    if not auth:
        socketio.emit('login_result', {'success': False, 'message': 'Auth no disponible'})
        return
    pin = data.get('pin', '')
    success, message = auth.login_with_pin(pin)
    if success:
        user_info = auth.get_session_info()
        socketio.emit('login_result', {
            'success': True,
            'message': message,
            'user_id': user_info['user_id'],
            'display_name': auth.get_user_display(user_info['user_id'])
        })
        print(f"[AUTH] 🔑 Login por PIN exitoso: {user_info['user_id']}", flush=True)
    else:
        socketio.emit('login_result', {'success': False, 'message': message})
        print(f"[AUTH] ❌ Login por PIN fallido", flush=True)

if __name__ == '__main__':
    # Start voice loop in a thread
    threading.Thread(target=voice_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)