"""Diagnostics support for Xiaomi Home (Lite-Safety addition).

Exposes a redacted summary (device count, model histogram, hook status)
through Home Assistant's standard "Download diagnostics" flow. No device
ids, tokens or credentials are included.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .miot.const import DOMAIN

TO_REDACT = {
    'access_token', 'refresh_token', 'token', 'service_token',
    'ssecurity', 'cUserId', 'userId', 'uid', 'password',
    'mac', 'did', 'bssid', 'open_id', 'sliding_token',
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    client = hass.data[DOMAIN].get('miot_clients', {}).get(entry.entry_id)
    devices: dict = client.device_list if client else {}
    models = Counter(
        info.get('model', 'unknown') for info in devices.values())
    online = sum(1 for info in devices.values() if info.get('online'))
    return {
        'entry_data': async_redact_data(dict(entry.data), TO_REDACT),
        'device_count': len(devices),
        'device_online': online,
        'models': dict(models),
        'lite_safety': {
            'prop_event_hook': bool(
                client and getattr(client, 'on_prop_msg_hook', None)),
            'device_event_hook': bool(
                client and getattr(client, 'on_event_msg_hook', None)),
        },
    }
