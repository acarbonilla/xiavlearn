import json
import logging
import os
from urllib import error, request

from django.conf import settings


logger = logging.getLogger(__name__)

OPENAI_CHAT_COMPLETIONS_URL = 'https://api.openai.com/v1/chat/completions'
DEFAULT_OPENAI_MODEL = 'gpt-5.4-mini'
TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_VALUES


def _setting_or_env(name, default=''):
    value = getattr(settings, name, None)
    if value is None:
        value = os.getenv(name, default)
    if isinstance(value, str):
        return value.strip()
    return value


def _setting_or_env_flag(name, default=False):
    value = getattr(settings, name, None)
    if value is None:
        return _env_flag(name, default=default)
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_VALUES
    return bool(value)


def get_llm_runtime_diagnostic():
    provider = _setting_or_env('LLM_PROVIDER', 'openai')
    model = _setting_or_env('LLM_MODEL', DEFAULT_OPENAI_MODEL)
    api_key = _setting_or_env('LLM_API_KEY', '')
    return {
        'enabled': _setting_or_env_flag('USE_LLM_AGENTS', default=False),
        'provider_configured': bool(provider),
        'model_configured': bool(model),
        'api_key_present': bool(api_key),
        'provider': provider or '',
        'model': model or '',
    }


def _missing_llm_config(diagnostic):
    missing = []
    if not diagnostic['provider_configured']:
        missing.append('LLM_PROVIDER')
    if not diagnostic['model_configured']:
        missing.append('LLM_MODEL')
    if not diagnostic['api_key_present']:
        missing.append('LLM_API_KEY')
    return missing


def _log_llm_skipped(reason, missing=None):
    missing_text = ','.join(missing or [])
    log = logger.info if reason == 'disabled' else logger.warning
    log(
        'VOICE_LLM_SKIPPED reason=%s missing=%s',
        reason,
        missing_text or 'none',
    )


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
    diagnostic = get_llm_runtime_diagnostic()
    if not diagnostic['enabled']:
        _log_llm_skipped('disabled')
        return None

    provider = diagnostic['provider'].strip().lower()
    api_key = _setting_or_env('LLM_API_KEY', '')
    model = diagnostic['model'].strip()

    missing = _missing_llm_config(diagnostic)
    if missing:
        _log_llm_skipped('missing_config', missing=missing)
        return None
    if provider != 'openai':
        _log_llm_skipped('unsupported_provider')
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
