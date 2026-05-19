"""Binary sensors for SMA Zero Export integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HEALTH_HEALTHY
from .coordinator import SMAZeroExportCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SMAZeroExportCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SMAHealthBinarySensor(coordinator, entry)])


class SMAHealthBinarySensor(
    CoordinatorEntity[SMAZeroExportCoordinator], BinarySensorEntity
):
    """True when the integration is healthy; False when degraded or failed."""

    _attr_has_entity_name = True
    _attr_translation_key = "healthy"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:heart-pulse"

    def __init__(
        self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_healthy"

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
    def is_on(self) -> bool:
        """BinarySensorDeviceClass.PROBLEM: True = problem detected (not healthy)."""
        data = self.coordinator.data or {}
        return data.get("health", HEALTH_HEALTHY) != HEALTH_HEALTHY
