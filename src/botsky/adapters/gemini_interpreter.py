"""Intérprete conversacional basado en la API de Google Gemini."""

import asyncio
import json
import time

from .cloudflare_interpreter import InterpreterError

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
SUPPORTED_GEMINI_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
)


class GeminiInterpreter:
    def __init__(
        self,
        http,
        api_key: str,
        model: str = DEFAULT_GEMINI_MODEL,
        *,
        deadline_seconds: int = 30,
        max_concurrency: int = 4,
    ):
        if not isinstance(api_key, str) or not api_key.strip():
            raise InterpreterError("credentials_invalid")
        if model not in SUPPORTED_GEMINI_MODELS:
            raise InterpreterError("model_configuration_invalid")
        self.http = http
        self.api_key = api_key.strip()
        self.model = model
        self.deadline = deadline_seconds
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.last_metrics = None

    async def propose(self, messages, tools):
        started = time.monotonic()
        async with asyncio.timeout(self.deadline):
            async with self.semaphore:
                protocol_instruction = (
                    "\nPROTOCOLO JSON PLANO: Devuelve un único objeto JSON. name identifica "
                    "reply,clarify,select_action o no_action; los demás campos son directamente "
                    "las propiedades del schema de esa función, SIN otra envoltura. Ejemplos de forma: "
                    '{"name":"select_action","action_key":"nota.guardar","arguments":{"text":"ejemplo"}} '
                    'o {"name":"reply","text":"Hola"}. Para select_action los argumentos de dominio '
                    "van obligatoriamente dentro de arguments; nunca al lado de action_key. "
                    "No produzcas XML, etiquetas ni llamadas de herramientas. Definiciones: "
                    + json.dumps(
                        [t["function"] for t in tools], ensure_ascii=False, separators=(",", ":")
                    )
                )

                system_text = ""
                contents = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "system":
                        system_text = (
                            (system_text + "\n" + content).strip() if system_text else content
                        )
                    elif role in ("user", "assistant"):
                        gemini_role = "user" if role == "user" else "model"
                        contents.append({"role": gemini_role, "parts": [{"text": content}]})

                full_system = (system_text + "\n" + protocol_instruction).strip()
                if not contents:
                    contents.append({"role": "user", "parts": [{"text": ""}]})

                payload = {
                    "system_instruction": {"parts": [{"text": full_system}]},
                    "contents": contents,
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.0,
                        "maxOutputTokens": 1024,
                    },
                }

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
                try:
                    response = await self.http.post(url, json=payload, timeout=self.deadline)
                except Exception:
                    raise InterpreterError("transport_error") from None

                if response.status_code == 429:
                    raise InterpreterError("rate_limited")
                if response.status_code == 503:
                    raise InterpreterError("service_unavailable")
                if response.status_code in (401, 403):
                    raise InterpreterError("auth_error")
                if response.status_code != 200:
                    raise InterpreterError("provider_http_" + str(response.status_code))

                try:
                    data = response.json()
                except ValueError:
                    raise InterpreterError("invalid_response") from None

                self.last_metrics = {
                    "model": self.model,
                    "duration_seconds": time.monotonic() - started,
                    "usage": data.get("usageMetadata"),
                }

                try:
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise ValueError("no_candidates")
                    candidate = candidates[0]
                    content_obj = candidate.get("content", {})
                    parts = content_obj.get("parts", [])
                    if not parts or not isinstance(parts[0].get("text"), str):
                        raise ValueError("no_content_text")
                    raw_text = parts[0]["text"]
                    envelope = json.loads(raw_text)
                    if not isinstance(envelope, dict) or not isinstance(envelope.get("name"), str):
                        raise ValueError("invalid_envelope_structure")
                    name = envelope.pop("name")

                    selection = next(
                        (
                            t["function"]["parameters"]
                            for t in tools
                            if t["function"]["name"] == "select_action"
                        ),
                        None,
                    )
                    action_keys = (
                        selection["properties"]["action_key"]["enum"] if selection else ()
                    )
                    if name in action_keys and set(envelope) == {"arguments"}:
                        envelope = {"action_key": name, "arguments": envelope["arguments"]}
                        name = "select_action"

                    definition = next(
                        (t["function"]["parameters"] for t in tools if t["function"]["name"] == name),
                        None,
                    )
                    if (
                        definition is None
                        or set(envelope) - set(definition["properties"])
                        or set(definition["required"]) - set(envelope)
                    ):
                        raise ValueError("schema_validation_failed")

                    formatted_envelope = {"name": name, "arguments": envelope}
                except (KeyError, TypeError, ValueError):
                    raise InterpreterError("invalid_json_envelope") from None

                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"tool_calls": [{"function": formatted_envelope}]},
                        }
                    ]
                }
