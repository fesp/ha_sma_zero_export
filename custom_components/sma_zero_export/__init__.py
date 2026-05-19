"""SMA Zero Export integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .const import CONTROL_MODES, DOMAIN, PLATFORMS
from .coordinator import SMAZeroExportCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SMA Zero Export from a config entry."""

    coordinator = SMAZeroExportCoordinator(hass, entry)
    await coordinator.async_setup()

    # Initial coordinator refresh so entities have data before being added.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward to all platforms.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (once, guarded by checking if already registered).
    _register_services(hass)

    # Re-initialise if the user changes options.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SMAZeroExportCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

        # Remove services when the last entry is removed.
        if not hass.data[DOMAIN]:
            for service in ("set_mode", "refresh"):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services (idempotent)."""

    if hass.services.has_service(DOMAIN, "set_mode"):
        return   # already registered

    SET_MODE_SCHEMA = vol.Schema(
        {vol.Required("mode"): vol.In(CONTROL_MODES)}
    )

    async def handle_set_mode(call: ServiceCall) -> None:
        mode = call.data["mode"]
        # Apply to every loaded entry (normally just one).
        for coordinator in hass.data.get(DOMAIN, {}).values():
            await coordinator.async_set_control_mode(mode)

    async def handle_refresh(call: ServiceCall) -> None:
        for coordinator in hass.data.get(DOMAIN, {}).values():
            await coordinator.async_force_refresh()

    hass.services.async_register(
        DOMAIN, "set_mode", handle_set_mode, schema=SET_MODE_SCHEMA
    )
    hass.services.async_register(DOMAIN, "refresh", handle_refresh)
