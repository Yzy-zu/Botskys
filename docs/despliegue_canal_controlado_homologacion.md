# Guía de Despliegue en Canal Controlado de Homologación

## 1. Propósito y Principio de No Afectación a Producción

Este documento especifica cómo desplegar una instancia de homologación de Botsky para ejecutar la validación visual en clientes reales (Fase 4), garantizando aislamiento total respecto al daemon de producción en vivo (`botsky.connected`, PID 3902023).

> [!IMPORTANT]
> Nunca reinicie, detenga ni altere el proceso de producción `botsky.connected` sin orden expresa del usuario. Toda prueba de canal controlado debe correr en un entorno aislado con base de datos, puerto y sesión independientes.

---

## 2. Aislamiento de Recursos

| Recurso | Producción en Vivo | Canal de Homologación (Staging) |
|---|---|---|
| **Base de Datos** | `/home/petrov/botsky/private/db.sqlite` | `/home/petrov/botsky/private/staging_db.sqlite` |
| **Directorio de Artefactos** | `/home/petrov/botsky/private/artifacts/` | `/home/petrov/botsky/private/staging_artifacts/` |
| **Instancia Baileys / Evolution** | Instancia de producción (número principal) | Instancia staging (número de prueba o subcuenta) |
| **Tokens / Webhook Port** | Puerto estándar configurado | Puerto dedicado (ej. `8085`) |

---

## 3. Procedimiento de Inicialización del Canal Controlado

### Paso 1: Creación del entorno de datos de prueba
```bash
cd /home/petrov/botsky
mkdir -p private/staging_artifacts
chmod 700 private/staging_artifacts
```

### Paso 2: Inicialización de la base de datos de staging
```bash
PYTHONPATH=src:tests .venv/bin/python -c '
from botsky.store import Store
from pathlib import Path
s = Store(Path("private/staging_db.sqlite"))
print("Base de datos de staging lista, versión:", s.version)
'
```

### Paso 3: Configuración de la sesión de mensajería
Para conectar WhatsApp a la instancia de prueba:
1. Configurar en Evolution API / Baileys una nueva instancia aislada (ej. `botsky-staging`).
2. Vincular mediante escaneo de código QR desde un número de teléfono de pruebas o SIM de homologación.
3. Configurar el webhook de entrada apuntando al puerto de la instancia de staging.

### Paso 4: Ejecución supervisada de la instancia de prueba
```bash
BOTSKY_DATABASE=private/staging_db.sqlite \
BOTSKY_ARTIFACTS=private/staging_artifacts \
BOTSKY_PORT=8085 \
PYTHONPATH=src .venv/bin/python -m botsky.app --env staging
```

---

## 4. Ejecución del Banco de Pruebas y Recolección de Evidencia

1. Desde el dispositivo de pruebas (Android / iPhone con WhatsApp), enviar los 6 mensajes del banco de pruebas definido en [docs/protocolo_validacion_visual_clientes_reales.md](file:///home/petrov/botsky/docs/protocolo_validacion_visual_clientes_reales.md).
2. Tomar captura de pantalla en:
   - Modo claro (*Light mode*)
   - Modo oscuro (*Dark mode*)
   - Dispositivo móvil (Android / iOS)
   - WhatsApp Web
3. Transferir las capturas al directorio `docs/evidencia/homologacion_visual/`.
4. Una vez verificadas las capturas, dar por concluida la sesión de staging y apagar el proceso del canal controlado.
