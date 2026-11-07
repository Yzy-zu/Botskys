"""Una petición HTTP, sin reintentos ni acceso al ejecutor."""
import asyncio
import json
import os
import re
import stat
import time
from datetime import UTC, datetime, timedelta

MODEL = '@cf/zai-org/glm-4.7-flash'


class InterpreterError(ValueError):
    pass


def read_credentials(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_size > 16384:
            raise InterpreterError('credentials_permissions')
        data = json.load(stream)
    if set(data) != {'account_id', 'api_token'} or not all(type(v) is str and v for v in data.values()):
        raise InterpreterError('credentials_invalid')
    if not re.fullmatch(r'[a-fA-F0-9]{32}', data['account_id']):
        raise InterpreterError('account_invalid')
    return data


class CloudflareInterpreter:
    def __init__(self, http, credentials, *, deadline_seconds=40, max_concurrency=2):
        self.http, self.credentials = http, credentials
        self.deadline = deadline_seconds
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.paused_until = None
        self.last_metrics = None

    async def propose(self, messages, tools):
        started = time.monotonic()
        async with asyncio.timeout(self.deadline):
            async with self.semaphore:
                now = datetime.now(UTC)
                if self.paused_until and now < self.paused_until:
                    raise InterpreterError('daily_quota')
                # GLM/Cloudflare tool parser returned 3030 on valid single proposals.
                # Fixed JSON envelope keeps the same closed decision contract, one
                # request and full catalog; no fallback or repair inference.
                wire_messages = [dict(message) for message in messages] or [{'role': 'system', 'content': ''}]
                wire_messages[0]['content'] += (
                    '\nPROTOCOLO JSON: Devuelve un solo objeto JSON con exactamente name y arguments. '
                    'name es reply,clarify,select_action o no_action. arguments cumple el schema '
                    'de esa función. No produzcas XML, etiquetas ni llamadas de herramientas. Definiciones: '
                    + json.dumps([t['function'] for t in tools], ensure_ascii=False, separators=(',', ':')))
                try:
                    response = await self.http.post(
                        'https://api.cloudflare.com/client/v4/accounts/' + self.credentials['account_id'] + '/ai/v1/chat/completions',
                        headers={'Authorization': 'Bearer ' + self.credentials['api_token']},
                        json={'model': MODEL, 'messages': wire_messages,
                              'response_format': {'type': 'json_object'}, 'stream': False,
                              'temperature': 0, 'max_completion_tokens': 1024}, timeout=self.deadline)
                except Exception:
                    raise InterpreterError('transport_error') from None
                try:
                    data = response.json()
                except ValueError:
                    raise InterpreterError('invalid_response') from None
                errors = data.get('errors', []) if isinstance(data, dict) else []
                codes = {e.get('code') for e in errors if isinstance(e, dict)}
                if 3036 in codes:
                    self.paused_until = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    raise InterpreterError('daily_quota')
                if 3040 in codes:
                    raise InterpreterError('capacity')
                if response.status_code != 200:
                    raise InterpreterError('provider_http_' + str(response.status_code))
                self.last_metrics = {'model': MODEL, 'duration_seconds': time.monotonic() - started,
                                     'usage': data.get('usage')}
                try:
                    choices = data['choices']
                    if len(choices) != 1 or choices[0]['finish_reason'] != 'stop':
                        raise ValueError()
                    message = choices[0]['message']
                    if message.get('tool_calls'):
                        raise ValueError()
                    envelope = json.loads(message['content'])
                    if type(envelope) is not dict or set(envelope) != {'name', 'arguments'}:
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    raise InterpreterError('invalid_json_envelope') from None
                return {'choices': [{'finish_reason': 'stop', 'message': {
                    'tool_calls': [{'function': envelope}]}}]}
