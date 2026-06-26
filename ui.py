#!/usr/bin/env python3
# ui.py – VoiceInterface con grabación directa a 16 kHz (compatible con enroll_user.py)

import os
import sys
import time
import tempfile
import wave
import subprocess
import shutil
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from config import (
    AUDIO_INPUT_DEVICE,
    AUDIO_OUTPUT_DEVICE,
    WHISPER_SIZE,
    SILENCE_THRESHOLD,
    SILENCE_DURATION,
    MAX_RECORDING_AFTER_SPEECH,
    MAX_WAIT_FOR_SPEECH,
    TEXT_MODE,
)

# ========== TTS helpers ==========
try:
    import pygame
except Exception:
    pygame = None

# ElevenLabs ya no se usa, pero mantenemos la detección por si se quiere reutilizar
ELEVENLABS_API_KEY = None
_key_file = os.path.expanduser("~/.jarvis/elevenlabs_key.txt")
if os.path.exists(_key_file):
    with open(_key_file) as f:
        ELEVENLABS_API_KEY = f.read().strip()
ELEVENLABS_AVAILABLE = False  # Desactivamos ElevenLabs; Piper es prioridad

# Verificar si edge-tts está disponible como fallback
try:
    import edge_tts
except ImportError:
    edge_tts = None

print("TTS: Piper (local) será usado. Edge‑tts queda como fallback si Piper falla.")


class VoiceInterface:
    def __init__(self, whisper_model_size=WHISPER_SIZE):
        print("Cargando Faster-Whisper...")
        self.whisper = WhisperModel(whisper_model_size, device="cpu", compute_type="int8")

        # Frecuencia objetivo para la IA (Whisper y PyAnnote REQUIEREN 16kHz)
        self.target_sample_rate = 16000

        # Forzar el backend de audio a PulseAudio/ALSA (evita errores de JACK)
        try:
            apis = sd.query_hostapis()
            for i, api in enumerate(apis):
                if 'ALSA' in api['name']:
                    sd.default.hostapi = i
                    print(f"[AUDIO] Usando backend ALSA/PulseAudio")
                    break
        except Exception:
            pass

        # Frecuencia nativa del micrófono (para abrir el InputStream sin errores)
        try:
            target_dev = AUDIO_INPUT_DEVICE if AUDIO_INPUT_DEVICE is not None else None
            input_info = sd.query_devices(target_dev, "input")
            self.native_sample_rate = int(input_info["default_samplerate"])
            print(f"DEBUG: Micrófono nativo a {self.native_sample_rate}Hz. Se remuestreará a {self.target_sample_rate}Hz para IA.")
        except Exception as e:
            print(f"Advertencia al consultar dispositivo: {e}")
            self.native_sample_rate = 48000  # Fallback seguro

        sd.default.channels = 1
        self.block_size = 1024

        # Wake word local
        self.wake_keyword = "alexa"
        self.wake_model = True
        self.wake_aliases = (
            "alexa", "ál exa", "al exa", "lexa",
            "jarvis", "hey jarvis", "hei jarvis", "hey yavis",
        )
        print(f"Wake word local activado: '{self.wake_keyword}' (+ alias)")

        self.passive_mode = False
        self.autotest_mode = "--autotest" in sys.argv

        # pygame (opcional)
        self._tts_pygame_ok = False
        if pygame is not None:
            try:
                pygame.mixer.init()
                pygame.mixer.quit()
                self._tts_pygame_ok = True
                print("TTS: pygame.mixer disponible")
            except Exception as e:
                print(f"Advertencia: pygame.mixer no disponible ({e})")

        mpv = shutil.which("mpv")
        ffplay = shutil.which("ffplay")
        if not self._tts_pygame_ok and not mpv and not ffplay:
            print("AVISO: Instala mpv o ffmpeg para oír al asistente en Linux.")

    # ========== Reproducción de audio ==========
    @staticmethod
    def _play_mp3_external(path):
        """Reproduce un archivo de audio (mp3, wav, etc.) con mpv o ffplay."""
        mpv = shutil.which("mpv")
        if mpv:
            r = subprocess.run([mpv, "--no-video", "--really-quiet", path],
                               timeout=300, capture_output=True)
            return r.returncode == 0
        ffplay = shutil.which("ffplay")
        if ffplay:
            r = subprocess.run([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                               timeout=300, capture_output=True)
            return r.returncode == 0
        return False

    # ========== TTS ==========
    def speak(self, text):
        """Sintetiza y reproduce el texto con la mejor opción disponible."""
        try:
            print(f"Asistente: {text}")
        except UnicodeEncodeError:
            print(f"Asistente: {text.encode('ascii', 'ignore').decode('ascii')}")

        # === PRIORIDAD 1: Piper TTS (local, offline, rápido) ===
        if self._speak_piper(text):
            return
        print("TTS: Piper falló, intentando edge-tts...")

        # === PRIORIDAD 2: edge-tts (fallback online) ===
        self._speak_edge_tts(text)

    def _speak_piper(self, text) -> bool:
        """Genera audio con Piper TTS (100% local). Retorna True si tuvo éxito."""
        tmp_path = None
        try:
            # Ruta del modelo Piper (debe existir)
            model_path = os.path.expanduser("~/.jarvis/piper_models/es_ES-davefx-medium.onnx")
            if not os.path.exists(model_path):
                print("Piper: Modelo no encontrado en", model_path)
                return False

            # Crear archivo temporal .wav
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_path = tmp_file.name

            # Ejecutar Piper
            result = subprocess.run(
                ['piper', '-m', model_path, '-f', tmp_path],
                input=text.encode('utf-8'),
                capture_output=True,
                timeout=30
            )

            if result.returncode != 0 or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 64:
                error_msg = result.stderr.decode('utf-8', 'ignore')[:200]
                print(f"Piper falló: {error_msg}")
                return False

            # Reproducir con el reproductor externo (mpv/ffplay)
            played = self._play_mp3_external(tmp_path)
            return played

        except Exception as e:
            print(f"Error en Piper TTS: {e}")
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _speak_edge_tts(self, text):
        """Sintetiza con edge-tts (requiere conexión a internet)."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                tmp_path = tmp_file.name

            gen = subprocess.run([
                sys.executable, "-m", "edge_tts",
                "--voice", "es-MX-DaliaNeural",
                "--text", text,
                "--write-media", tmp_path,
            ], capture_output=True, timeout=90)
            if gen.returncode != 0 or os.path.getsize(tmp_path) < 64:
                return

            played = False
            if self._tts_pygame_ok:
                try:
                    pygame.mixer.init()
                    pygame.mixer.music.load(tmp_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.08)
                    pygame.mixer.music.unload()
                    played = True
                except Exception:
                    pass
            if not played:
                self._play_mp3_external(tmp_path)
        except Exception as e:
            print(f"edge-tts error: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ========== Captura de voz ==========
    def listen(self, timeout=10):
        """Escucha y transcribe con Faster-Whisper. Devuelve (texto, ruta_wav_para_voice_id)."""
        if TEXT_MODE:
            try:
                return input("\n[MODO TEXTO] Escribe tu comando: ").strip() or None
            except EOFError:
                return None

        print("Escuchando...")
        audio_buffer = []
        recording = False
        silence_start = None
        voice_start_time = None
        start_time = time.time()

        def callback(indata, frames, time_info, status):
            nonlocal recording, silence_start, voice_start_time
            rms = np.sqrt(np.mean(indata**2))
            audio_buffer.append(indata.copy())
            if rms > SILENCE_THRESHOLD:
                recording = True
                if voice_start_time is None:
                    voice_start_time = time.time()
                silence_start = None
            elif recording:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_DURATION:
                    raise sd.CallbackStop()
            if recording and voice_start_time and (time.time() - voice_start_time) > MAX_RECORDING_AFTER_SPEECH:
                raise sd.CallbackStop()
            if (not recording) and (time.time() - start_time) > MAX_WAIT_FOR_SPEECH:
                raise sd.CallbackStop()

        try:
            with sd.InputStream(samplerate=self.native_sample_rate, channels=1,
                                callback=callback, blocksize=self.block_size,
                                device=AUDIO_INPUT_DEVICE):
                while time.time() - start_time < timeout:
                    sd.sleep(100)
        except sd.CallbackStop:
            pass

        if not recording:
            print("No se detectó voz.")
            return (None, None)

        audio = np.concatenate(audio_buffer, axis=0)

        # Remuestreo a 16 kHz para IA
        if self.native_sample_rate != self.target_sample_rate:
            try:
                from scipy.signal import resample_poly
                audio = resample_poly(audio.flatten(), self.target_sample_rate, self.native_sample_rate)
                print(f"[AUDIO] Remuestreado de {self.native_sample_rate}Hz a {self.target_sample_rate}Hz")
            except ImportError:
                print("[AUDIO] ⚠️ scipy no instalado, el audio podría no funcionar bien con la IA")

        # Guardar en WAV temporal
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_wav = f.name
        with wave.open(temp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.target_sample_rate)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())

        # Transcribir
        segments, _ = self.whisper.transcribe(temp_wav, beam_size=1, language="es")
        text = " ".join(seg.text for seg in segments).strip()
        print(f"Usuario dijo: {text}")

        # Copia opcional para Voice ID
        voice_wav = None
        if text:
            try:
                voice_wav = tempfile.NamedTemporaryFile(suffix="_voice_id.wav", delete=False).name
                shutil.copy2(temp_wav, voice_wav)
            except Exception:
                pass

        try:
            os.remove(temp_wav)
        except Exception:
            pass

        return (text if text else None, voice_wav)

    def list_audio_devices(self):
        print("\n--- Dispositivos de Audio Detectados ---")
        for i, dev in enumerate(sd.query_devices()):
            print(f"ID {i}: {dev['name']} "
                  f"(Entradas: {dev['max_input_channels']}, Salidas: {dev['max_output_channels']})")
        print("----------------------------------------\n")

    # ========== Wake word ==========
    def _wake_text_matches(self, text: str) -> bool:
        t = text.lower().strip().replace("á", "a").replace("é", "e")
        if self.wake_keyword in t:
            return True
        for alias in self.wake_aliases:
            if alias.lower().replace("á", "a") in t:
                return True
        return False

    def listen_for_wake_word(self):
        if not self.wake_model:
            return True

        wake_rms_floor = max(0.012, SILENCE_THRESHOLD * 0.35)
        print(f"Esperando palabra clave '{self.wake_keyword}'...")

        try:
            while True:
                audio_buffer = []
                start_time = time.time()
                chunk_seconds = 2.2
                with sd.InputStream(samplerate=self.target_sample_rate, channels=1,
                                    blocksize=self.block_size,
                                    device=AUDIO_INPUT_DEVICE) as stream:
                    while time.time() - start_time < chunk_seconds:
                        data, _ = stream.read(int(self.target_sample_rate * 0.1))
                        audio_buffer.append(data.copy())

                audio = np.concatenate(audio_buffer, axis=0)
                if audio.size == 0:
                    continue

                rms = np.sqrt(np.mean(audio**2))
                if rms < wake_rms_floor:
                    continue

                # Guardar a 16 kHz y transcribir
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_wav = f.name
                with wave.open(temp_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.target_sample_rate)
                    wf.writeframes((audio * 32767).astype(np.int16).tobytes())

                segments, _ = self.whisper.transcribe(temp_wav, beam_size=1, language="es")
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass
                text = " ".join(seg.text for seg in segments).lower().strip()
                print(f"DEBUG wake-word: '{text}' (rms={rms:.4f})")
                if self._wake_text_matches(text):
                    print(f"[OK] Palabra clave detectada: '{text}'")
                    return True
        except Exception as e:
            print(f"Error en detección de wake word: {e}")
            return False

    def ask_confirmation(self, timeout=5):
        if self.autotest_mode:
            return True
        print("Esperando confirmación ('sí', 'adelante', 'no', 'cancela')...")
        result = self.listen(timeout=timeout)
        if not result or not result[0]:
            return False
        text = result[0].lower()
        return any(w in text for w in ["sí", "si", "adelante", "continúa", "dale", "ok", "está bien"])
