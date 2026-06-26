# server_linux.py - Minimal Flask backend for Linux without GUI dependencies

print("Starting Jarvis server (Linux minimal mode)...")
import os
import sys
import platform

# Only run this on Linux
if platform.system() != "Linux":
    print("This is the Linux version. Use server.py on Windows.")
    sys.exit(1)

from flask import Flask
from flask_socketio import SocketIO, emit
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# Global state
current_status = 'inactivo'
mic_active = False

print("Skipping GUI-dependent modules on Linux (openwakeword, etc.)")

def voice_loop():
    """Dummy voice loop for Linux - listening mode disabled by default"""
    global current_status
    try:
        from openwakeword.model import Model
        print("Wake-word model initialized")
        have_wakeword = True
    except Exception as e:
        print(f"Wake-word not available: {e}")
        have_wakeword = False
    
    while True:
        # For Linux, keep the service alive but don't actively listen
        if mic_active and have_wakeword:
            current_status = 'escuchando'
            socketio.emit('status', {'status': current_status})
            # In Linux mode, we would listen here but it's disabled for service stability
            time.sleep(1)
        else:
            current_status = 'inactivo'
            socketio.emit('status', {'status': current_status})
            time.sleep(2)

@socketio.on('connect')
def handle_connect():
    print("Cliente Socket.IO conectado")
    emit('status', {'status': current_status})

@socketio.on('client_ready')
def handle_client_ready():
    print("Cliente listo recibido")
    emit('status', {'status': current_status})

@socketio.on('disconnect')
def handle_disconnect():
    print("Cliente Socket.IO desconectado")

@socketio.on('toggle_mic')
def handle_toggle_mic(data):
    global mic_active
    mic_active = data.get('active', False)
    print(f"Mic toggled to {mic_active}")
    emit('status', {'status': 'escuchando' if mic_active else 'inactivo'})

@socketio.on('new_conversation')
def handle_new_conversation():
    pass

@socketio.on('clear_history')
def handle_clear_history():
    pass

if __name__ == '__main__':
    # Start voice loop in a thread
    threading.Thread(target=voice_loop, daemon=True).start()
    print("Server running on 0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True, debug=False)
