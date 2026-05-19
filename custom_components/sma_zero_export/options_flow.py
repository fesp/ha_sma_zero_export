"""Options flow for SMA Zero Export integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DEFAULT_AUTOMATIC_CONTROL,
    DEFAULT_DEADBAND,
    DEFAULT_DISCREPANCY_THRESHOLD,
    DEFAULT_FAILSAFE_TIMEOUT,
    DEFAULT_MANUAL_STATE,
    DEFAULT_MIN_TOGGLE_INTERVAL,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_VALIDATION_ENABLED,
    OPT_AUTOMATIC_CONTROL,
    OPT_DEADBAND,
    OPT_DEBUG_LOGGING,
    OPT_DISCREPANCY_THRESHOLD,
    OPT_ENERGY_METER_SENSOR,
    OPT_FAILSAFE_TIMEOUT,
    OPT_MANUAL_STATE,
    OPT_MIN_TOGGLE_INTERVAL,
    OPT_NOTIFICATIONS_ENABLED,
    OPT_NOTIFY_SERVICE,
    OPT_POLLING_INTERVAL,
    OPT_VALIDATION_ENABLED,
)


class SMAZeroExportOptionsFlow(config_entries.OptionsFlow):
    """Options flow: all 12 settings from spec section 3."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        opts = self._entry.options

        if user_input is not None:
            # Write validated options and signal the coordinator to reload.
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                # 3.1 Automatic Control
                vol.Required(
                    OPT_AUTOMATIC_CONTROL,
                    default=opts.get(OPT_AUTOMATIC_CONTROL, DEFAULT_AUTOMATIC_CONTROL),
                ): BooleanSelector(),
                vol.Required(
                    OPT_MANUAL_STATE,
                    default=opts.get(OPT_MANUAL_STATE, DEFAULT_MANUAL_STATE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["on", "off"],
                        mode=SelectSelectorMode.LIST,
                        translation_key="manual_state",
                    )
                ),
                # 3.2 Algorithm Settings
                vol.Required(
                    OPT_DEADBAND,
                    default=opts.get(OPT_DEADBAND, DEFAULT_DEADBAND),
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=5.0, step=0.01, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    OPT_MIN_TOGGLE_INTERVAL,
                    default=opts.get(OPT_MIN_TOGGLE_INTERVAL, DEFAULT_MIN_TOGGLE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=1440, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
                ),
                vol.Required(
                    OPT_POLLING_INTERVAL,
                    default=opts.get(OPT_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=60, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
                ),
                # 3.3 Validation
                vol.Required(
                    OPT_VALIDATION_ENABLED,
                    default=opts.get(OPT_VALIDATION_ENABLED, DEFAULT_VALIDATION_ENABLED),
                ): BooleanSelector(),
                vol.Optional(
                    OPT_ENERGY_METER_SENSOR,
                    default=opts.get(OPT_ENERGY_METER_SENSOR, ""),
                ): EntitySelector(
                    EntitySelectorConfig(domain=["sensor"])
                ),
                vol.Required(
                    OPT_DISCREPANCY_THRESHOLD,
                    default=opts.get(OPT_DISCREPANCY_THRESHOLD, DEFAULT_DISCREPANCY_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10000, step=10, mode=NumberSelectorMode.BOX, unit_of_measurement="W")
                ),
                # 3.4 Notifications
                vol.Required(
                    OPT_NOTIFICATIONS_ENABLED,
                    default=opts.get(OPT_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED),
                ): BooleanSelector(),
                vol.Optional(
                    OPT_NOTIFY_SERVICE,
                    default=opts.get(OPT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE),
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                # 3.5 Fail-safe
                vol.Required(
                    OPT_FAILSAFE_TIMEOUT,
                    default=opts.get(OPT_FAILSAFE_TIMEOUT, DEFAULT_FAILSAFE_TIMEOUT),
                ): NumberSelector(
                    NumberSelectorConfig(min=5, max=1440, step=5, mode=NumberSelectorMode.BOX, unit_of_measurement="min")
                ),
                # 3.6 Debug
                vol.Required(
                    OPT_DEBUG_LOGGING,
                    default=opts.get(OPT_DEBUG_LOGGING, False),
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
