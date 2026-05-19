"""Select entity for SMA Zero Export control mode."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONTROL_MODES, DOMAIN
from .coordinator import SMAZeroExportCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SMAZeroExportCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SMAControlModeSelect(coordinator, entry)])


class SMAControlModeSelect(
    CoordinatorEntity[SMAZeroExportCoordinator], SelectEntity
):
    """Writable select: automatic / manual_on / manual_off.

    Selecting a mode immediately changes the operating mode and — when
    switching to a manual mode — writes the corresponding state to the
    SMA portal once.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "control_mode"
    _attr_icon = "mdi:tune"
    _attr_options = CONTROL_MODES

    def __init__(
        self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_control_mode"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="SMA Zero Export Controller",
            manufacturer="SMA",
            model="Sunny Portal Grid Management",
            configuration_url="https://ennexos.sunnyportal.com/",
        )

    @property
    def current_option(self) -> str:
        data = self.coordinator.data or {}
        return data.get("control_mode", self.coordinator.control_mode)

    async def async_select_option(self, option: str) -> None:
        """Called by HA when the user picks a new mode from the UI."""
        if option not in CONTROL_MODES:
            _LOGGER.error("Invalid control mode selected: %s", option)
            return
        _LOGGER.info("Control mode changing to: %s", option)
        await self.coordinator.async_set_control_mode(option)
        self.async_write_ha_state()
