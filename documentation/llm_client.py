import json
import logging
import os
from urllib import error, request


logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_URL = 'https://api.openai.com/v1/chat/completions'
DEFAULT_OPENAI_MODEL = 'gpt-5.4-mini'
TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_VALUES


def _extract_json_content(payload):
    choices = payload.get('choices') or []
    if not choices:
        return None
    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text_parts.append(item.get('text', ''))
        return ''.join(text_parts) or None
    return None


def _strip_code_fences(raw_content):
    content = raw_content.strip()
    if content.startswith('```'):
        lines = content.splitlines()
        if len(lines) >= 3:
            content = '\n'.join(lines[1:-1]).strip()
    return content


def call_llm_json(system_prompt, user_prompt):
    if not _env_flag('USE_LLM_AGENTS', default=False):
        return None

    provider = os.getenv('LLM_PROVIDER', 'openai').strip().lower()
    api_key = os.getenv('LLM_API_KEY', '').strip()
    model = os.getenv('LLM_MODEL', DEFAULT_OPENAI_MODEL).strip()

    if provider != 'openai' or not api_key or not model:
        return None

    payload = {
        'model': model,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
    }
    body = json.dumps(payload).encode('utf-8')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    http_request = request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=body,
        headers=headers,
        method='POST',
    )

    try:
        with request.urlopen(http_request, timeout=30) as response:
            response_payload = json.loads(response.read().decode('utf-8'))
    except (error.URLError, error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        logger.exception('Optional LLM request failed.')
        return None

    raw_content = _extract_json_content(response_payload)
    if not raw_content:
        return None

    try:
        return json.loads(_strip_code_fences(raw_content))
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.exception('Optional LLM response was not valid JSON.')
        return None
