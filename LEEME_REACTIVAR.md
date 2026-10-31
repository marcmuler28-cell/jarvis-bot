# Reactivar JarvisBot (día de la RAM nueva 🐏)
1. Python:   python -m venv venv_linux && venv_linux/bin/pip install -r requirements.txt
2. UI:       cd ui-electron && npm install && npm run build && cd ..
3. Modelos (si no están en models/, re-descargar de HuggingFace):
   - Qwen2.5-7B-Instruct-1M-Q4_K_M.gguf
   - mistral-7b-instruct-v0.2.Q4_K_M.gguf
   - qwen2.5-3b-instruct-q4_k_m.gguf
   - phi-2.Q4_K_M.gguf
4. Arrancar con tu comando de siempre
