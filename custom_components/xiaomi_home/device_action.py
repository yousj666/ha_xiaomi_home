"""Device actions for Xiaomi Home (Lite-Safety).

Writable MIoT properties become "set property" device actions and MIoT
actions become "call action" device actions, so Xiaomi devices can be
picked directly in the automation editor's action step.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv

from .lite_safety import resolve_miot_device
from .miot.const import DOMAIN

ACTION_TYPE_SET_PROPERTY = 'set_property'
ACTION_TYPE_CALL_ACTION = 'call_action'

_ACTION_BASE = {
    vol.Required(CONF_DOMAIN): DOMAIN,
    vol.Required(CONF_DEVICE_ID): cv.string,
}
ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend({
    **_ACTION_BASE,
    vol.Required(CONF_TYPE): vol.In(
        [ACTION_TYPE_SET_PROPERTY, ACTION_TYPE_CALL_ACTION]),
    vol.Optional('siid'): cv.positive_int,
    vol.Optional('piid'): cv.positive_int,
    vol.Optional('aiid'): cv.positive_int,
    vol.Optional('value'): vol.Any(bool, int, float, str),
    vol.Optional('in_list'): list,
})


async def async_validate_action_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """Validate config."""
    return ACTION_SCHEMA(config)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device actions for a device."""
    device = resolve_miot_device(hass, device_id)
    if device is None:
        return []
    actions: list[dict[str, Any]] = []
    for service in device.spec_instance.services:
        for prop in service.properties:
            if not prop.writable:
                continue
            actions.append({
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: ACTION_TYPE_SET_PROPERTY,
                'siid': service.iid,
                'piid': prop.iid,
                'subtype': f'{prop.name} ({service.iid}.{prop.iid})',
            })
        for act in service.actions:
            actions.append({
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: ACTION_TYPE_CALL_ACTION,
                'siid': service.iid,
                'aiid': act.iid,
                'subtype': f'{act.name} ({service.iid}.{act.iid})',
            })
    return actions


async def async_get_action_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """List action capabilities."""
    if config[CONF_TYPE] == ACTION_TYPE_SET_PROPERTY:
        return {
            'extra_fields': vol.Schema({
                vol.Required('value'): vol.Any(bool, int, float, str),
            })
        }
    return {
        'extra_fields': vol.Schema({
            vol.Optional('in_list', default=[]): list,
        })
    }


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: dict[str, Any],
    variables: dict[str, Any],
    context: Context | None,
) -> None:
    """Execute a device action."""
    device = resolve_miot_device(hass, config[CONF_DEVICE_ID])
    if device is None:
        return
    client = device.miot_client
    if config[CONF_TYPE] == ACTION_TYPE_SET_PROPERTY:
        await client.set_prop_async(
            did=device.did, siid=config['siid'], piid=config['piid'],
            value=config.get('value'))
    else:
        await client.action_async(
            did=device.did, siid=config['siid'], aiid=config['aiid'],
            in_list=config.get('in_list') or [])
