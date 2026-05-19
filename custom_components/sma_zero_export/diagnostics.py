"""Diagnostics support for SMA Zero Export."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_ID_TOKEN, DOMAIN
from .coordinator import SMAZeroExportCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry (shown in HA UI → Download diagnostics)."""
    coordinator: SMAZeroExportCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Sanitise sensitive fields before returning.
    safe_data = {
        k: "**REDACTED**" if k in (CONF_PASSWORD, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_ID_TOKEN) else v
        for k, v in entry.data.items()
    }

    return {
        "config_entry": {
            "entry_id": entry.entry_id,
            "data": safe_data,
            "options": dict(entry.options),
        },
        "runtime": {
            "control_mode": coordinator.control_mode,
            "zero_export_active": coordinator.zero_export_active,
            "last_toggle": coordinator.last_toggle.isoformat() if coordinator.last_toggle else None,
            "api_status": coordinator.api_status,
            "api_latency_ms": coordinator.api_latency_ms,
            "health": coordinator.health,
            "validation_status": coordinator.validation_status,
            "rate_limited_until": (
                coordinator._rate_limited_until.isoformat()
                if coordinator._rate_limited_until else None
            ),
        },
        "coordinator_data": coordinator.data,
    }
