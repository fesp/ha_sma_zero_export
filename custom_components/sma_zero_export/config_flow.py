"""Config flow for SMA Zero Export integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SMAApiClient, SMAAuthError, SMAApiError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ID_TOKEN,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PRICE_SENSOR,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
        vol.Required(CONF_PLANT_ID): str,
        vol.Required(CONF_PRICE_SENSOR): EntitySelector(
            EntitySelectorConfig(domain=["sensor"])
        ),
    }
)


class SMAZeroExportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow: credentials → PKCE login → API test → done."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict = {}

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Step 1: collect credentials and price sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Duplicate check: same plant_id already configured?
            await self.async_set_unique_id(user_input[CONF_PLANT_ID])
            self._abort_if_unique_id_configured()

            # Attempt PKCE login + test API call
            client = SMAApiClient(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                plant_id=user_input[CONF_PLANT_ID],
            )
            try:
                await client.async_login()
                await client.async_get_grid_management()
            except SMAAuthError:
                errors["base"] = "invalid_auth"
            except SMAApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            finally:
                await client.async_close()

            if not errors:
                tokens = client.get_tokens()
                entry_data = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_PLANT_ID: user_input[CONF_PLANT_ID],
                    CONF_PRICE_SENSOR: user_input[CONF_PRICE_SENSOR],
                    CONF_ACCESS_TOKEN: tokens["access_token"],
                    CONF_REFRESH_TOKEN: tokens["refresh_token"],
                    CONF_ID_TOKEN: tokens["id_token"],
                }
                return self.async_create_entry(
                    title=f"SMA Zero Export ({user_input[CONF_PLANT_ID]})",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        from .options_flow import SMAZeroExportOptionsFlow
        return SMAZeroExportOptionsFlow(entry)
