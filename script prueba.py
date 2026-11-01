# [PATCH_VOICE_GLOBAL]
try:
    import sounddevice as sd
except Exception:
    pass
import numpy as np

def callback(indata, frames, time, status):
    volume = np.linalg.norm(indata) * 10
    print(f"Volumen: {volume:.2f}")

print("Habla durante 5 segundos...")
with sd.InputStream(device=14, callback=callback):
    sd.sleep(5000)