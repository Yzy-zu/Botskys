# Qwen probado y ejecución local · 07/11/2026

Modelo:Qwen3.8-27B. Cloudflare:@cf/qwen/qwen3.8-27b,razonamiento low.
Pesos originales:Qwen/Qwen3.8-27B enHuggingFace;referencia del equipo oficial:
https://github.com/QwenLM/Qwen3.8 . low es parámetro,nootrocheckpoint.

Otros proveedores:OpenRouter qwen/qwen3.8-27b listaDeepInfra,AlibabaCloudInt.,
Cerebras yotros. Tarifas por tokens,no se acredita cuota gratuita independiente.
https://openrouter.ai/qwen/qwen3.8-27b

Ollama permite descargar/ejecutar:ollama run qwen3.8:27b . Su ficha declara18GB
para el paquete actual,más memoria de ejecución/contexto,no RAMtotalgarantizada.
https://ollama.com/library/qwen3.8

VarianteGGUFcuantizada deUnsloth:unsloth/Qwen3.8-27B-GGUF,UD-Q4_K_M.
https://huggingface.co/unsloth/Qwen3.8-27B-GGUF . Instrucción publicada:
ollama run hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M

No se descargó/cargó ni conectó un modelo local durante esta consulta. Este host
reporta11GiB deRAM;no alcanza para alojar enRAMpor sísolo el paquete18GBmáscontexto.
No se comprobóGPU/VRAM;ausencia denvidia-smi no demuestra ausencia deotrasGPU.
Para valorar otraPC hace falta su RAM/GPU/VRAM. Local evita cuota deneuronas del
servicioCloudflare,pero depende dehardware/tiempo/energía. Cuantizar o cambiar de
proveedor exige contrastar de nuevo antes de usarlo para decisiones deBotsky.
