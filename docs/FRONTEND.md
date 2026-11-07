# Frontend conversacional · F2

Adaptador y servicio aislados; no conectado a admisión hasta F3.
`Application.frontend` conserva la instancia optativa, sin ejecutarla automáticamente.
Una decisión es una propuesta validada, nunca evidencia de efecto.

Bloque optativo del perfil existente (no reemplaza los demás bloques):

```json
{"interpreter":{"enabled":false,"provider":"cloudflare","model":"@cf/zai-org/glm-4.7-flash","credentials_file":"private/cloudflare-toolcall.json","deadline_seconds":40,"max_concurrency":2}}
```

Credenciales propias relativas a settings.root, archivo privado con account_id y
api_token. Sin lectura si está desactivado. No hay pools ni cambio de modelo.
Una petición por decisión, ninguna después del resultado. El contexto lo prepara
el host; todavía no se implementa continuidad F4. Métricas de última inferencia
en el adaptador: modelo, duración y usage reportado; no conversaciones ni razonamiento.
La pausa diaria 3036 es local a la instancia; persistencia y estado operativo
se integran en F3. El proveedor real y calidad semántica se comprueban en F7.
