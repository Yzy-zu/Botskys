"""Interpreta una vez y valida; no conoce Application ni ejecuta herramientas."""
import json

from botsky.adapters.cloudflare_interpreter import InterpreterError
from .catalog import Catalog
from .contracts import ActionRequest, ClarifyDecision, NoActionDecision, ReplyDecision
from .prompts import SYSTEM, FINAL_RULES, tools


class FrontendService:
    def __init__(self, provider, catalog=None):
        self.provider = provider
        self.catalog = catalog or Catalog()

    async def decide(self, text, context=None):
        if type(text) is not str or not text.strip() or len(text) > 64000:
            raise InterpreterError('invalid_input')
        messages = [{'role': 'system', 'content': SYSTEM + '\nCATALOGO:\n' + json.dumps(self.catalog.describe(), ensure_ascii=False, separators=(',', ':')) + '\n' + FINAL_RULES},
                    {'role': 'user', 'content': json.dumps({'message': text, 'context': context or {}}, ensure_ascii=False)}]
        data = await self.provider.propose(messages, tools(self.catalog))
        try:
            choices = data['choices']
            if len(choices) != 1 or choices[0]['finish_reason'] not in ('stop', 'tool_calls'):
                raise ValueError()
            message = choices[0]['message']
            calls = message['tool_calls']
            if len(calls) != 1 or message.get('content'):
                raise ValueError()
            function = calls[0]['function']
            name = function['name']
            args = function['arguments']
            if isinstance(args, str):
                args = json.loads(args)
            definition = next(t['function']['parameters'] for t in tools(self.catalog) if t['function']['name'] == name)
            if type(args) is not dict or set(args) - set(definition['properties']) or set(definition['required']) - set(args):
                raise ValueError()
            if name == 'select_action':
                decision = ActionRequest(**args)
                self.catalog.build(decision)
                return decision
            for key in ('text', 'question', 'reason'):
                if key in args and (type(args[key]) is not str or not 1 <= len(args[key].strip()) <= 2000):
                    raise ValueError()
            if name == 'clarify':
                if args.get('action_key') is not None and args['action_key'] not in self.catalog.specs:
                    raise ValueError()
                if type(args.get('partial_arguments', {})) is not dict:
                    raise ValueError()
                for key in ('missing_fields', 'choices'):
                    if key in args:
                        if type(args[key]) is not list or any(type(v) is not str for v in args[key]):
                            raise ValueError()
                        args[key] = tuple(args[key])
                return ClarifyDecision(**args)
            return ReplyDecision(**args) if name == 'reply' else NoActionDecision(**args)
        except (KeyError, TypeError, ValueError, StopIteration):
            raise InterpreterError('invalid_decision') from None
