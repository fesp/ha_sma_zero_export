"""Coordinator for SMA Zero Export integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SMAApiClient, SMAAuthError, SMAApiError, SMARateLimitError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ID_TOKEN,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PRICE_SENSOR,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    CONTROL_MODE_AUTOMATIC,
    CONTROL_MODE_MANUAL_OFF,
    CONTROL_MODE_MANUAL_ON,
    DEFAULT_DEADBAND,
    DEFAULT_DISCREPANCY_THRESHOLD,
    DEFAULT_FAILSAFE_TIMEOUT,
    DEFAULT_MIN_TOGGLE_INTERVAL,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_VALIDATION_ENABLED,
    DOMAIN,
    FAILSAFE_INTERVAL_SECONDS,
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_HEALTHY,
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
    RATE_LIMIT_BACKOFF_SECONDS,
    STATUS_DATA_ERROR,
    STATUS_ERROR_401,
    STATUS_ERROR_429,
    STATUS_ERROR_5XX,
    STATUS_NETWORK_ERROR,
    STATUS_SUCCESS,
    STATUS_VALIDATION_MISMATCH,
    VALIDATION_DISABLED,
    VALIDATION_FAILED,
    VALIDATION_INTERVAL_SECONDS,
    VALIDATION_SUCCESS,
)

_LOGGER = logging.getLogger(__name__)


class SMAZeroExportCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central coordinator.

    Owns the API client. Drives state polling, the control algorithm,
    feed-in validation, and the fail-safe — each gated on automatic mode.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry

        polling_minutes = entry.options.get(OPT_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=polling_minutes),
        )

        data = entry.data
        opts = entry.options

        self.api = SMAApiClient(
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            plant_id=data[CONF_PLANT_ID],
            access_token=data.get(CONF_ACCESS_TOKEN, ""),
            refresh_token=data.get(CONF_REFRESH_TOKEN, ""),
            id_token=data.get(CONF_ID_TOKEN, ""),
            debug=opts.get(OPT_DEBUG_LOGGING, False),
        )

        # If the integration option for debug logging is enabled, elevate
        # the package logger to DEBUG so debug statements throughout the
        # integration become visible. Avoid changing levels when not
        # explicitly requested to prevent noisy logs in normal operation.
        try:
            pkg_logger = logging.getLogger(__name__.rsplit(".", 1)[0])
            if opts.get(OPT_DEBUG_LOGGING, False):
                pkg_logger.setLevel(logging.DEBUG)
        except Exception:
            # Be conservative: if logger manipulation fails, do nothing.
            pass

        # ── Runtime state ──────────────────────────────────────────────────
        self.zero_export_active: bool | None = None
        self.last_toggle: datetime | None = None
        self.api_status: str = STATUS_SUCCESS
        self.api_latency_ms: int = 0
        self.health: str = HEALTH_HEALTHY
        self.validation_status: str = VALIDATION_DISABLED

        # Derive initial control_mode from options
        automatic = opts.get(OPT_AUTOMATIC_CONTROL, True)
        if automatic:
            self.control_mode: str = CONTROL_MODE_AUTOMATIC
        else:
            manual_on = opts.get(OPT_MANUAL_STATE, "off") == "on"
            self.control_mode = CONTROL_MODE_MANUAL_ON if manual_on else CONTROL_MODE_MANUAL_OFF

        # Rate-limit back-off
        self._rate_limited_until: datetime | None = None

        # Periodic task cancel-callbacks
        self._validation_cancel: Any = None
        self._failsafe_cancel: Any = None
        self._price_listener_cancel: Any = None

    # ── Convenience ───────────────────────────────────────────────────────────

    @property
    def _automatic(self) -> bool:
        return self.control_mode == CONTROL_MODE_AUTOMATIC

    def _opt(self, key: str, default: Any) -> Any:
        return self._entry.options.get(key, default)

    # ── Token persistence ─────────────────────────────────────────────────────

    async def _persist_tokens(self) -> None:
        """Write current tokens back to config entry data so they survive restarts."""
        new_data = {**self._entry.data, **self.api.get_tokens()}
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)

    # ── Startup ───────────────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Called once from async_setup_entry after coordinator is created."""
        # Always do an initial state fetch so sensors have values immediately.
        await self._fetch_portal_state()

        if self._automatic:
            self._start_periodic_tasks()
            self._subscribe_price_sensor()
            # Run the algorithm immediately if we already know the price.
            await self._run_control_algorithm()
        else:
            # Manual mode: write desired state once, then stay idle.
            desired_on = self.control_mode == CONTROL_MODE_MANUAL_ON
            await self._apply_manual_state(desired_on)

    # ── DataUpdateCoordinator hook ────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Called periodically by the coordinator timer (automatic mode only)."""
        if not self._automatic:
            # Guard: timer may fire briefly after a mode switch.
            return self._snapshot()

        if self._is_rate_limited():
            _LOGGER.debug("Rate-limited; skipping poll")
            return self._snapshot()

        await self._fetch_portal_state()
        if self._automatic:   # re-check: state fetch may have set health=failed
            await self._run_control_algorithm()
        return self._snapshot()

    def _snapshot(self) -> dict[str, Any]:
        """Current runtime state as a plain dict for entity consumption."""
        return {
            "zero_export_active": self.zero_export_active,
            "last_toggle": self.last_toggle,
            "api_status": self.api_status,
            "api_latency_ms": self.api_latency_ms,
            "health": self.health,
            "validation_status": self.validation_status,
            "control_mode": self.control_mode,
        }

    # ── Portal state fetch ────────────────────────────────────────────────────

    async def _fetch_portal_state(self) -> None:
        """Read Zero Export state from SMA and update internal state."""
        try:
            result = await self.api.async_get_grid_management()
            self.api_latency_ms = result.get("latency_ms", 0)
            active = SMAApiClient.parse_zero_export_active(result["data"])
            if active is None:
                _LOGGER.warning("Could not parse feedInLimitation.active from SMA response")
                self.api_status = STATUS_DATA_ERROR
                self._set_health(HEALTH_DEGRADED)
            else:
                prev = self.zero_export_active
                self.zero_export_active = active
                self.api_status = STATUS_SUCCESS
                self._set_health(HEALTH_HEALTHY)
                await self._persist_tokens()
                if prev is not None and prev != active:
                    _LOGGER.warning(
                        "SMA portal state changed unexpectedly: %s → %s",
                        "ON" if prev else "OFF",
                        "ON" if active else "OFF",
                    )
        except SMAAuthError as exc:
            _LOGGER.error("Authentication failed permanently: %s", exc)
            self.api_status = STATUS_ERROR_401
            self._set_health(HEALTH_FAILED)
            await self._notify(
                "SMA Zero Export: authentication failed. "
                "Please reload the integration or update your credentials."
            )
        except SMARateLimitError:
            _LOGGER.warning(
                "Rate limited by SMA API; backing off for %ds", RATE_LIMIT_BACKOFF_SECONDS
            )
            self.api_status = STATUS_ERROR_429
            self._set_health(HEALTH_DEGRADED)
            self._rate_limited_until = dt_util.utcnow() + timedelta(
                seconds=RATE_LIMIT_BACKOFF_SECONDS
            )
        except SMAApiError as exc:
            _LOGGER.error("API error fetching portal state: %s", exc)
            self.api_status = (
                STATUS_ERROR_5XX if (exc.status_code or 0) >= 500 else STATUS_NETWORK_ERROR
            )
            self._set_health(HEALTH_DEGRADED)

    def _is_rate_limited(self) -> bool:
        if self._rate_limited_until is None:
            return False
        if dt_util.utcnow() >= self._rate_limited_until:
            self._rate_limited_until = None
            return False
        return True

    # ── Control algorithm ─────────────────────────────────────────────────────

    async def _run_control_algorithm(self) -> None:
        """Steps 2–7.  Only runs in automatic mode."""
        if not self._automatic:
            return
        if self.health == HEALTH_FAILED:
            _LOGGER.debug("Skipping algorithm: health is FAILED")
            return

        # Step 2: read price sensor
        price = self._read_price_sensor()
        if price is None:
            _LOGGER.debug("Price sensor unavailable; skipping algorithm")
            return

        deadband = self._opt(OPT_DEADBAND, DEFAULT_DEADBAND)

        # Step 3: desired state
        if price < -deadband:
            desired: bool | None = True    # ON
        elif price > deadband:
            desired = False                # OFF
        else:
            desired = None                 # HOLD

        if desired is None:
            return

        # Step 4: minimum toggle interval
        min_interval = self._opt(OPT_MIN_TOGGLE_INTERVAL, DEFAULT_MIN_TOGGLE_INTERVAL)
        if self.last_toggle is not None:
            elapsed_min = (dt_util.utcnow() - self.last_toggle).total_seconds() / 60
            if elapsed_min < min_interval:
                _LOGGER.debug(
                    "Min interval not reached (%.1f/%.0f min); skipping toggle",
                    elapsed_min, min_interval,
                )
                return

        # Step 5: compare with actual portal state
        if self.zero_export_active is None:
            _LOGGER.debug("Portal state unknown; skipping toggle")
            return
        if desired == self.zero_export_active:
            return  # already correct

        # Apply and record toggle
        await self._set_zero_export(desired, update_last_toggle=True)

    async def _apply_manual_state(self, desired_on: bool) -> None:
        """Write a state to the portal once (manual mode — no min-interval, no toggle update)."""
        if self.zero_export_active is not None and self.zero_export_active == desired_on:
            _LOGGER.debug(
                "Manual state already matches portal (%s); skipping write",
                "ON" if desired_on else "OFF",
            )
            return
        await self._set_zero_export(desired_on, update_last_toggle=False)

    async def _set_zero_export(self, enable: bool, *, update_last_toggle: bool) -> None:
        """Call PUT, update internal state, do follow-up GET (Step 6)."""
        label = "ON" if enable else "OFF"
        try:
            result = await self.api.async_set_zero_export(enable)
            self.api_latency_ms = result.get("latency_ms", 0)
            self.api_status = STATUS_SUCCESS
            if update_last_toggle:
                self.last_toggle = dt_util.utcnow()
            await self._persist_tokens()
            _LOGGER.info("Zero Export set to %s", label)
        except SMAAuthError as exc:
            _LOGGER.error("Auth error while setting Zero Export: %s", exc)
            self.api_status = STATUS_ERROR_401
            self._set_health(HEALTH_FAILED)
            return
        except SMARateLimitError:
            _LOGGER.warning("Rate limited while setting Zero Export to %s", label)
            self.api_status = STATUS_ERROR_429
            self._set_health(HEALTH_DEGRADED)
            return
        except SMAApiError as exc:
            _LOGGER.error("API error setting Zero Export to %s: %s", label, exc)
            self.api_status = (
                STATUS_ERROR_5XX if (exc.status_code or 0) >= 500 else STATUS_NETWORK_ERROR
            )
            self._set_health(HEALTH_DEGRADED)
            return

        # Step 6: follow-up GET to confirm
        await asyncio.sleep(2)
        await self._fetch_portal_state()
        if self.zero_export_active != enable:
            _LOGGER.error(
                "Post-toggle validation failed: expected %s, portal reports %s",
                label,
                "ON" if self.zero_export_active else "OFF",
            )
            self.api_status = STATUS_VALIDATION_MISMATCH
            self._set_health(HEALTH_DEGRADED)
            await self._notify(
                f"SMA Zero Export: tried to set {label} but portal still reports "
                f"{'ON' if self.zero_export_active else 'OFF'}"
            )

    # ── Price sensor ──────────────────────────────────────────────────────────

    def _read_price_sensor(self) -> float | None:
        entity_id = self._entry.data.get(CONF_PRICE_SENSOR)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", ""):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _subscribe_price_sensor(self) -> None:
        entity_id = self._entry.data.get(CONF_PRICE_SENSOR)
        if not entity_id:
            return

        @callback
        def _on_price_change(_event: Any) -> None:
            if self._automatic:
                self.hass.async_create_task(self._run_control_algorithm())

        self._price_listener_cancel = async_track_state_change_event(
            self.hass, [entity_id], _on_price_change
        )

    # ── Periodic tasks ────────────────────────────────────────────────────────

    def _start_periodic_tasks(self) -> None:
        self._start_validation_task()
        self._start_failsafe_task()

    def _stop_periodic_tasks(self) -> None:
        for attr in ("_validation_cancel", "_failsafe_cancel", "_price_listener_cancel"):
            cancel_fn = getattr(self, attr)
            if cancel_fn is not None:
                cancel_fn()
                setattr(self, attr, None)

    def _start_validation_task(self) -> None:
        @callback
        def _tick(_now: Any) -> None:
            if self._automatic:
                self.hass.async_create_task(self._run_validation())

        self._validation_cancel = async_track_time_interval(
            self.hass, _tick, timedelta(seconds=VALIDATION_INTERVAL_SECONDS)
        )

    def _start_failsafe_task(self) -> None:
        @callback
        def _tick(_now: Any) -> None:
            if self._automatic:
                self.hass.async_create_task(self._run_failsafe())

        self._failsafe_cancel = async_track_time_interval(
            self.hass, _tick, timedelta(seconds=FAILSAFE_INTERVAL_SECONDS)
        )

    # ── Feed-in validation ────────────────────────────────────────────────────

    async def _run_validation(self) -> None:
        """Check grid feed-in against the discrepancy threshold."""
        if not self._opt(OPT_VALIDATION_ENABLED, DEFAULT_VALIDATION_ENABLED):
            self.validation_status = VALIDATION_DISABLED
            return

        if not self.zero_export_active:
            # Nothing to validate when Zero Export is OFF.
            self.validation_status = VALIDATION_DISABLED
            return

        meter_entity = self._opt(OPT_ENERGY_METER_SENSOR, "")
        if not meter_entity:
            self.validation_status = VALIDATION_DISABLED
            return

        state = self.hass.states.get(meter_entity)
        if state is None or state.state in ("unavailable", "unknown", ""):
            _LOGGER.debug("Feed-in sensor %s unavailable", meter_entity)
            return

        try:
            feed_in_w = float(state.state)
        except ValueError:
            _LOGGER.warning("Cannot parse feed-in sensor value: %s", state.state)
            return

        threshold = self._opt(OPT_DISCREPANCY_THRESHOLD, DEFAULT_DISCREPANCY_THRESHOLD)
        if feed_in_w > threshold:
            if self.validation_status != VALIDATION_FAILED:
                _LOGGER.warning(
                    "Feed-in validation FAILED: %.1f W > threshold %.0f W",
                    feed_in_w, threshold,
                )
                await self._notify(
                    f"SMA Zero Export: feed-in validation failed — "
                    f"grid export is {feed_in_w:.0f} W (threshold: {threshold:.0f} W)"
                )
            self.validation_status = VALIDATION_FAILED
        else:
            self.validation_status = VALIDATION_SUCCESS

        self.async_set_updated_data(self._snapshot())

    # ── Fail-safe ─────────────────────────────────────────────────────────────

    async def _run_failsafe(self) -> None:
        """Step 7: force OFF if Zero Export has been ON too long at positive price."""
        if not self._automatic:
            return
        if self.health == HEALTH_FAILED:
            return

        price = self._read_price_sensor()
        if price is None or price <= 0:
            return
        if not self.zero_export_active:
            return
        if self.last_toggle is None:
            return

        timeout_min = self._opt(OPT_FAILSAFE_TIMEOUT, DEFAULT_FAILSAFE_TIMEOUT)
        elapsed_min = (dt_util.utcnow() - self.last_toggle).total_seconds() / 60

        if elapsed_min < timeout_min:
            return

        _LOGGER.warning(
            "Fail-safe triggered: Zero Export ON for %.0f min at price %.4f; forcing OFF",
            elapsed_min, price,
        )
        await self._notify(
            f"SMA Zero Export fail-safe: Zero Export has been ON for "
            f"{elapsed_min:.0f} min at positive price ({price:.4f}). Forcing OFF."
        )
        await self._set_zero_export(False, update_last_toggle=True)
        self.async_set_updated_data(self._snapshot())

    # ── Mode switching (called from select entity and set_mode service) ────────

    async def async_set_control_mode(self, mode: str) -> None:
        """Switch control mode.  Starts/stops periodic tasks as needed."""
        if mode == self.control_mode:
            return

        self.control_mode = mode

        # Persist mode into options so it survives restarts.
        new_options = {
            **self._entry.options,
            OPT_AUTOMATIC_CONTROL: (mode == CONTROL_MODE_AUTOMATIC),
            OPT_MANUAL_STATE: "on" if mode == CONTROL_MODE_MANUAL_ON else "off",
        }
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)

        if mode == CONTROL_MODE_AUTOMATIC:
            self._start_periodic_tasks()
            self._subscribe_price_sensor()
            # Re-fetch state and immediately run the algorithm.
            await self._fetch_portal_state()
            await self._run_control_algorithm()
        else:
            self._stop_periodic_tasks()
            desired_on = (mode == CONTROL_MODE_MANUAL_ON)
            await self._apply_manual_state(desired_on)
            # Validation resets to disabled in manual mode.
            self.validation_status = VALIDATION_DISABLED

        self.async_set_updated_data(self._snapshot())

    # ── Force refresh (service call) ──────────────────────────────────────────

    async def async_force_refresh(self) -> None:
        """Refresh portal state.  Only re-runs algorithm in automatic mode."""
        await self._fetch_portal_state()
        if self._automatic:
            await self._run_control_algorithm()
        self.async_set_updated_data(self._snapshot())

    # ── Health helper ─────────────────────────────────────────────────────────

    def _set_health(self, new_state: str) -> None:
        if self.health != new_state:
            _LOGGER.info("Health: %s → %s", self.health, new_state)
        self.health = new_state

    # ── Notifications ─────────────────────────────────────────────────────────

    async def _notify(self, message: str) -> None:
        if not self._opt(OPT_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED):
            return
        service = self._opt(OPT_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        if not service:
            return
        parts = service.split(".", 1)
        if len(parts) != 2:
            _LOGGER.warning("Invalid notify service string: %s", service)
            return
        try:
            await self.hass.services.async_call(
                parts[0],
                parts[1],
                {"title": "SMA Zero Export", "message": message},
                blocking=False,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Notification failed: %s", exc)

    # ── Teardown ──────────────────────────────────────────────────────────────

    async def async_shutdown(self) -> None:
        self._stop_periodic_tasks()
        await self.api.async_close()
