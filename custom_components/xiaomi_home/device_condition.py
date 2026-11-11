"""Device conditions for Xiaomi Home (Lite-Safety).

Readable MIoT properties become "property is" device conditions,
evaluated against the value the owning entity currently holds.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.condition import ConditionCheckerType

from .lite_safety import resolve_miot_device
from .miot.const import DOMAIN
from .miot.miot_spec import MIoTSpecProperty

CONDITION_TYPE = 'property_is'

CONDITION_SCHEMA = cv.DEVICE_CONDITION_BASE_SCHEMA.extend({
    vol.Required(CONF_DOMAIN): DOMAIN,
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Required(CONF_TYPE): CONDITION_TYPE,
    vol.Required('siid'): cv.positive_int,
    vol.Required('piid'): cv.positive_int,
    vol.Required('value'): vol.Any(bool, int, float, str),
})


async def async_validate_condition_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """Validate config."""
    return CONDITION_SCHEMA(config)


async def async_get_conditions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device conditions for a device."""
    device = resolve_miot_device(hass, device_id)
    if device is None:
        return []
    conditions: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for service in device.spec_instance.services:
        for prop in service.properties:
            if not prop.access:
                continue
            key = (service.iid, prop.iid)
            if key in seen:
                continue
            seen.add(key)
            conditions.append({
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: CONDITION_TYPE,
                'siid': service.iid,
                'piid': prop.iid,
                'subtype': f'{prop.name} ({service.iid}.{prop.iid})',
            })
    return conditions


async def async_get_condition_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, Any]:
    """List condition capabilities."""
    return {
        'extra_fields': vol.Schema({
            vol.Required('value'): vol.Any(bool, int, float, str),
        })
    }


async def async_condition_from_config(
    hass: HomeAssistant, config: dict[str, Any]
) -> ConditionCheckerType:
    """Create a condition checker from config."""
    device = resolve_miot_device(hass, config[CONF_DEVICE_ID])
    tag = device.did_tag if device else None
    siid = config['siid']
    piid = config['piid']
    expected = config['value']

    @callback
    def _check(hass_: HomeAssistant, variables: dict[str, Any] | None = None) -> bool:
        if tag is None:
            return False
        for entities in hass_.data.get(DOMAIN, {}).get('entities', {}).values():
            if not isinstance(entities, list):
                continue
            for entity in entities:
                spec = getattr(entity, 'spec', None)
                if not isinstance(spec, MIoTSpecProperty):
                    continue
                if spec.service.iid != siid or spec.iid != piid:
                    continue
                owner = getattr(entity, 'miot_device', None)
                if owner is None or owner.did_tag != tag:
                    continue
                return entity.get_prop_value(spec) == expected
        return False

    return _check
