# Modelos de IA

Esta carpeta contiene los modelos GGUF utilizados por JarvisBot.
**No se incluyen en el repositorio por tamaño (>100MB cada uno).**

## Descarga manual

Coloca los siguientes archivos en esta carpeta (`models/`):

| Modelo | Tamaño | URL de descarga |
|--------|--------|-----------------|
| Qwen2.5-7B-Instruct-1M-Q4_K_M.gguf | ~4.5 GB | https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-1M-GGUF |
| mistral-7b-instruct-v0.2.Q4_K_M.gguf | ~4.2 GB | https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF |
| qwen2.5-3b-instruct-q4_k_m.gguf | ~2.0 GB | https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF |
| phi-2.Q4_K_M.gguf | ~1.7 GB | https://huggingface.co/TheBloke/phi-2-GGUF |

## Descarga automática (opcional)

```bash
# Instalar huggingface-cli
pip install huggingface-hub

# Descargar un modelo
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-1M-GGUF \
  qwen2.5-7b-instruct-1m-q4_k_m.gguf \
  --local-dir ./models

