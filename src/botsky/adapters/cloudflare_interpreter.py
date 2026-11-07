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
                try:
                    response = await self.http.post(
                        'https://api.cloudflare.com/client/v4/accounts/' + self.credentials['account_id'] + '/ai/v1/chat/completions',
                        headers={'Authorization': 'Bearer ' + self.credentials['api_token']},
                        json={'model': MODEL, 'messages': messages, 'tools': tools,
                              'tool_choice': 'required', 'stream': False, 'parallel_tool_calls': False,
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
                return data
