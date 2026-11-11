"""Device triggers for Xiaomi Home (Lite-Safety).

Every readable/notifiable MIoT property of a device becomes a device
trigger ("property changed"), implemented on top of the
``xiaomi_home_property_changed`` bus event the Lite-Safety hooks emit.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .lite_safety import resolve_miot_device
from .miot.const import DOMAIN

EVENT_PROPERTY_CHANGED = f'{DOMAIN}_property_changed'
TRIGGER_TYPE = 'property_changed'

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({
    vol.Required(CONF_TYPE): TRIGGER_TYPE,
    vol.Required('siid'): cv.positive_int,
    vol.Required('piid'): cv.positive_int,
    vol.Optional('value'): vol.Any(bool, int, float, str),
})


async def async_validate_trigger_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """Validate config."""
    return TRIGGER_SCHEMA(config)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for a device."""
    device = resolve_miot_device(hass, device_id)
    if device is None:
        return []
    triggers: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for service in device.spec_instance.services:
        for prop in service.properties:
            if not prop.access:
                continue
            key = (service.iid, prop.iid)
            if key in seen:
                continue
            seen.add(key)
            triggers.append({
                CONF_PLATFORM: 'device',
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: TRIGGER_TYPE,
                'siid': service.iid,
                'piid': prop.iid,
                'subtype': f'{prop.name} ({service.iid}.{prop.iid})',
            })
    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """List trigger capabilities (an optional target value)."""
    return {
        'extra_fields': vol.Schema({
            vol.Optional('value'): vol.Any(bool, int, float, str),
        })
    }


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    device_id = config[CONF_DEVICE_ID]
    siid = config['siid']
    piid = config['piid']
    has_value = 'value' in config

    @callback
    def _handle_event(event) -> None:
        data = event.data
        if data.get('device_id') != device_id:
            return
        if data.get('siid') != siid or data.get('piid') != piid:
            return
        if has_value and data.get('value') != config['value']:
            return
        trigger_variables = {
            'trigger': {
                **trigger_info.get('trigger_variables', {}),
                'platform': 'device',
                'domain': DOMAIN,
                'type': TRIGGER_TYPE,
                'device_id': device_id,
                'siid': siid,
                'piid': piid,
                'value': data.get('value'),
                'description': f'{DOMAIN} property {siid}.{piid} changed',
            }
        }
        hass.async_create_task(action(trigger_variables, event.context))

    return hass.bus.async_listen(EVENT_PROPERTY_CHANGED, _handle_event)
