"""Sensors for SMA Zero Export integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SMAZeroExportCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SMAZeroExportCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SMAStateSensor(coordinator, entry),
            SMALastToggleSensor(coordinator, entry),
            SMAStatusSensor(coordinator, entry),
            SMAValidationSensor(coordinator, entry),
            SMALatencySensor(coordinator, entry),
        ]
    )


# ── Shared base ───────────────────────────────────────────────────────────────

class _SMABaseSensor(CoordinatorEntity[SMAZeroExportCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="SMA Zero Export Controller",
            manufacturer="SMA",
            model="Sunny Portal Grid Management",
            configuration_url="https://ennexos.sunnyportal.com/",
        )

    def _data(self) -> dict[str, Any]:
        return self.coordinator.data or {}


# ── Individual sensors ────────────────────────────────────────────────────────

class SMAStateSensor(_SMABaseSensor):
    """Read-only portal state: 'on' / 'off' / 'unknown'."""

    _attr_translation_key = "state"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_state"

    @property
    def native_value(self) -> str:
        active = self._data().get("zero_export_active")
        if active is None:
            return "unknown"
        return "on" if active else "off"


class SMALastToggleSensor(_SMABaseSensor):
    """Timestamp of last successful toggle (automatic mode only)."""

    _attr_translation_key = "last_toggle"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_toggle"

    @property
    def native_value(self):
        return self._data().get("last_toggle")


class SMAStatusSensor(_SMABaseSensor):
    """Last API status string."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:api"

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        return self._data().get("api_status", "UNKNOWN")


class SMAValidationSensor(_SMABaseSensor):
    """Feed-in validation: 'disabled' / 'success' / 'failed'."""

    _attr_translation_key = "validation"
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_validation"

    @property
    def native_value(self) -> str:
        return self._data().get("validation_status", "disabled")


class SMALatencySensor(_SMABaseSensor):
    """API round-trip latency in milliseconds."""

    _attr_translation_key = "api_latency"
    _attr_native_unit_of_measurement = "ms"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: SMAZeroExportCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_api_latency"

    @property
    def native_value(self) -> int | None:
        return self._data().get("api_latency_ms")
