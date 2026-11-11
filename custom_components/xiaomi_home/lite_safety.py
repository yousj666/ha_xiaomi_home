"""Lite-Safety shared helpers: device resolution and BYOK AI assistant.

The AI assistant is bring-your-own-key: the user stores an OpenAI
compatible base URL, API key and model name (via the
``xiaomi_home.configure_ai`` service) in Home Assistant's own storage.
Nothing is sent anywhere except the endpoint the user configured.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .miot.common import slugify_did
from .miot.const import DOMAIN
from .miot.miot_client import MIoTClient
from .miot.miot_device import MIoTDevice

_LOGGER = logging.getLogger(__name__)

AI_STORE_KEY = 'xiaomi_home_lite_safety'
AI_DEFAULT_MODEL = ''

# Services the AI assistant is allowed to call when it decides a user
# request needs a device action. Anything else is refused.
AI_ALLOWED_SERVICE_DOMAINS = {
    'xiaomi_home', 'light', 'switch', 'climate', 'fan', 'cover',
    'vacuum', 'media_player', 'humidifier', 'water_heater', 'button',
    'number', 'select', 'text', 'scene', 'script',
}


def resolve_miot_device(
    hass: HomeAssistant, device_id: str
) -> Optional[MIoTDevice]:
    """Resolve a HA device registry id to a MIoTDevice of this domain."""
    registry = dr.async_get(hass)
    device_entry = registry.async_get(device_id)
    if device_entry is None:
        return None
    tag: Optional[str] = None
    for domain, identifier in device_entry.identifiers:
        if domain == DOMAIN:
            tag = identifier
            break
    if tag is None:
        return None
    for devices in hass.data.get(DOMAIN, {}).get('devices', {}).values():
        for device in devices:
            if device.did_tag == tag:
                return device
    return None


def ha_device_id_for_did(
    hass: HomeAssistant, client: MIoTClient, did: str
) -> Optional[str]:
    """Resolve a MIoT did to the HA device registry id (cached by caller)."""
    registry = dr.async_get(hass)
    device_entry = registry.async_get_device(
        identifiers={(DOMAIN, slugify_did(
            cloud_server=client.cloud_server, did=did))},
        connections=None)
    return device_entry.id if device_entry else None


def _ai_store(hass: HomeAssistant) -> Store:
    return Store(hass, 1, AI_STORE_KEY)


async def async_load_ai_config(hass: HomeAssistant) -> dict:
    """Load the BYOK AI configuration (cached in hass.data)."""
    cache = hass.data[DOMAIN].setdefault('lite_ai', None)
    if cache is not None:
        return cache
    data = await _ai_store(hass).async_load() or {}
    config = {
        'base_url': data.get('base_url', ''),
        'api_key': data.get('api_key', ''),
        'model': data.get('model', AI_DEFAULT_MODEL),
    }
    hass.data[DOMAIN]['lite_ai'] = config
    return config


async def async_save_ai_config(
    hass: HomeAssistant, base_url: str, api_key: str, model: str
) -> dict:
    """Persist the BYOK AI configuration to HA storage."""
    config = {
        'base_url': (base_url or '').rstrip('/'),
        'api_key': api_key or '',
        'model': model or AI_DEFAULT_MODEL,
    }
    await _ai_store(hass).async_save(config)
    hass.data[DOMAIN]['lite_ai'] = config
    return config


def build_device_context(hass: HomeAssistant, max_lines: int = 300) -> str:
    """Compact text snapshot of devices and entity states for the LLM."""
    lines: list[str] = []
    for devices in hass.data.get(DOMAIN, {}).get('devices', {}).values():
        for device in devices:
            lines.append(
                f"device: {device.name} | model: "
                f"{getattr(device, 'model', '')} | did: {device.did}")
    for state in hass.states.async_all():
        lines.append(
            f"entity: {state.entity_id} = {state.state} "
            f"({state.attributes.get('friendly_name', '')})")
        if len(lines) >= max_lines:
            break
    return '\n'.join(lines)


AI_SYSTEM_PROMPT = (
    'You are the built-in AI assistant of a Xiaomi smart home running in '
    'Home Assistant. Answer questions about the home using the device '
    'and entity snapshot provided. If (and only if) the user clearly asks '
    'you to control a device, reply with a short sentence plus exactly one '
    'JSON code block like '
    '{"service": "light.turn_on", "data": {"entity_id": "light.xxx"}} '
    'or {"service": "xiaomi_home.set_properties", "data": {"did": "...", '
    '"siid": 2, "piid": 1, "value": true}}. '
    'Never invent entity ids or device ids that are not in the snapshot.'
)


async def async_ask_ai(
    hass: HomeAssistant, prompt: str, allow_control: bool = False
) -> str:
    """Ask the user-configured LLM. Optionally execute one control call.

    Returns the assistant's text (any executed service call is appended
    as a short confirmation line). Raises ValueError when the AI is not
    configured or the endpoint fails.
    """
    config = await async_load_ai_config(hass)
    if not config['base_url'] or not config['api_key'] or not config['model']:
        raise ValueError(
            'AI assistant is not configured: call the '
            'xiaomi_home.configure_ai service with base_url, api_key '
            'and model first')
    session = async_get_clientsession(hass)
    payload = {
        'model': config['model'],
        'messages': [
            {'role': 'system', 'content': AI_SYSTEM_PROMPT},
            {'role': 'system', 'content': build_device_context(hass)},
            {'role': 'user', 'content': prompt},
        ],
    }
    try:
        async with session.post(
                f"{config['base_url']}/chat/completions",
                json=payload,
                headers={
                    'Authorization': f"Bearer {config['api_key']}",
                    'Content-Type': 'application/json',
                }, timeout=60) as resp:
            body = await resp.json()
            if resp.status != 200:
                raise ValueError(
                    f'AI endpoint error {resp.status}: {str(body)[:200]}')
    except ValueError:
        raise
    except Exception as err:  # pylint: disable=broad-exception-caught
        raise ValueError(f'AI endpoint unreachable: {err}') from err
    try:
        text: str = body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as err:
        raise ValueError(f'unexpected AI response: {str(body)[:200]}') from err

    call = _extract_service_call(text)
    if call is not None:
        text = text.replace(call['raw'], '').strip()
        if allow_control:
            domain = call['service'].split('.')[0]
            if domain in AI_ALLOWED_SERVICE_DOMAINS:
                try:
                    await hass.services.async_call(
                        domain, call['service'].split('.', 1)[1],
                        call.get('data') or {}, blocking=True)
                    text += f"\n[Lite-Safety] 已执行: {call['service']}"
                except Exception as err:  # pylint: disable=broad-exception-caught
                    text += f"\n[Lite-Safety] 执行失败: {err}"
            else:
                text += f"\n[Lite-Safety] 已拦截不在白名单的服务: {call['service']}"
        else:
            text += '\n[Lite-Safety] 检测到控制指令，但本次调用未开启 allow_control，未执行。'
    return text


def _extract_service_call(text: str) -> Optional[dict]:
    """Extract a {"service": ...} JSON block from an LLM reply."""
    start = text.find('{')
    while start != -1:
        end = text.rfind('}')
        if end <= start:
            return None
        snippet = text[start:end + 1]
        try:
            parsed = json.loads(snippet)
        except (ValueError, TypeError):
            start = text.find('{', start + 1)
            continue
        if isinstance(parsed, dict) and 'service' in parsed:
            parsed['raw'] = snippet
            return parsed
        return None
    return None


def ai_configured(config: dict) -> bool:
    """Whether the BYOK AI configuration is complete."""
    return bool(
        config.get('base_url') and config.get('api_key')
        and config.get('model'))
