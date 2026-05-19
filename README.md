# SMA Zero Export — Home Assistant Integration

Automatically controls the **Zero Export** setting on your SMA inverter via the Sunny Portal (EnnexOS) API, driven by real-time energy prices from a Home Assistant sensor.

When the energy price is negative you are effectively paid to export, so Zero Export is turned **OFF**.
When the price is positive you are paying to export, so Zero Export is turned **ON** to stop feeding back into the grid.

---

## Features

- Fully automatic ON/OFF control based on a configurable price sensor and deadband
- Manual override modes (`manual_on` / `manual_off`) that write the state once and then leave the portal alone
- Configurable minimum toggle interval to prevent rapid switching
- Configurable polling interval (default 5 min) to stay within SMA's rate limits
- Optional grid feed-in validation via an energy meter sensor (P1-meter, Sunny Home Manager, etc.)
- Optional fail-safe: forces Zero Export OFF if it has been ON too long at a positive price
- Optional push notifications to any Home Assistant notify service
- On-demand token refresh (no background timer; refresh only triggered by a real 401 response)
- All settings configurable via the HA UI — no YAML required
- HACS-compatible

---

## Requirements

- Home Assistant 2024.1 or newer
- An SMA inverter connected to [Sunny Portal / EnnexOS](https://ennexos.sunnyportal.com/)
- Your SMA Sunny Portal **username**, **password**, and **plant ID**
- A Home Assistant **sensor** that provides the current energy price as a numeric value (e.g. from the [Nordpool](https://github.com/custom-components/nordpool) or [ENTSO-E](https://github.com/JaccoR/hass-entso-e) integrations)

---

## Finding your Plant ID

1. Log in to [ennexos.sunnyportal.com](https://ennexos.sunnyportal.com/)
2. Open your plant
3. Look at the browser URL — it will contain something like `/plants/12345/...`
4. The number (`12345`) is your plant ID

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → Custom repositories**
3. Add `https://github.com/fesp/sma_zero_export` with category **Integration**
4. Search for **SMA Zero Export** and install it
5. Restart Home Assistant

### Manual

1. Download the latest release from [GitHub](https://github.com/fesp/sma_zero_export/releases)
2. Copy the `sma_zero_export` folder into your `<config>/custom_components/` directory
3. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SMA Zero Export**
3. Enter:
   - **SMA username** — your Sunny Portal e-mail address
   - **SMA password** — your Sunny Portal password
   - **Plant ID** — see above
   - **Energy price sensor** — the HA sensor entity that provides the current price
4. The integration performs a PKCE login and a test API call. If either fails, an error is shown and you can retry.
5. Once setup completes, the integration is active immediately.

---

## Options

Open **Settings → Devices & Services → SMA Zero Export → Configure** to adjust any setting without re-entering credentials.

### Automatic Control

| Setting | Default | Description |
|---|---|---|
| Enable automatic control | On | When off, the manual state below is applied once to the portal and held. |
| Manual state | Off | The Zero Export state to apply when automatic control is disabled. |

### Algorithm Settings

| Setting | Default | Description |
|---|---|---|
| Deadband | 0.1 | Prices between −deadband and +deadband are treated as zero (no toggle). |
| Minimum toggle interval | 30 min | Prevents rapid switching. No toggle is made sooner than this after the last one. |
| State polling interval | 5 min | How often the integration reads the actual state from the SMA portal. Only active in automatic mode. |

**Price logic:**
- Price `< −deadband` → Zero Export **ON** (negative price: being paid to export is still wasteful if you're limiting; turn off the limit)
- Price `> +deadband` → Zero Export **OFF** (positive price: stop exporting)
- Price between `−deadband` and `+deadband` → **no change** (HOLD)

### Monitoring / Validation

| Setting | Default | Description |
|---|---|---|
| Enable grid feed-in validation | Off | When on, reads the feed-in sensor and flags if export exceeds the threshold while Zero Export is active. |
| Grid feed-in sensor | — | A sensor measuring current grid feed-in power (W). Must be set if validation is enabled. |
| Discrepancy threshold | 200 W | If grid feed-in exceeds this value while Zero Export is active, validation is marked failed. |

### Notifications

| Setting | Default | Description |
|---|---|---|
| Enable notifications | Off | Send push notifications on errors, fail-safe triggers, and validation failures. |
| Notification service | — | Full service name, e.g. `notify.mobile_app_myphone`. |

### Fail-Safe

| Setting | Default | Description |
|---|---|---|
| Fail-safe timeout | 60 min | If Zero Export stays ON for longer than this while the price is positive, the integration forces it OFF. Only applies in automatic mode. |

### Debug

| Setting | Default | Description |
|---|---|---|
| Enable debug logging | Off | Logs API request/response metadata (no sensitive data). Check logs under **Settings → System → Logs**. |

#### Debug logging

You can enable more verbose output for troubleshooting in two ways:

- Via the integration options UI: go to **Settings → Devices & Services → SMA Zero Export → Configure** and enable **Enable debug logging**. This opt‑in exposes debug messages generated by the integration (including truncated response previews). Tokens are redacted from these previews.

- Temporarily via Home Assistant's logger (useful for ad‑hoc troubleshooting): add the following to your `configuration.yaml` and reload the logger or restart Home Assistant:

```yaml
logger:
  logs:
    custom_components.sma_zero_export: debug
```

Notes:
- Debug logging increases log volume; disable it when you're finished investigating.
- At non-debug levels (INFO/WARNING/ERROR) the integration does not include raw API response bodies or sensitive tokens in logs.
- If you prefer, you can download diagnostics from the integration's three‑dot menu and share that (tokens are redacted) when filing an issue.

---

## Entities

After setup, the integration creates a device called **SMA Zero Export Controller** with the following entities:

### Sensors

| Entity | Description |
|---|---|
| `sensor.sma_zero_export_state` | Current Zero Export state as read from the portal: `on`, `off`, or `unknown`. This is the canonical portal state indicator. |
| `sensor.sma_zero_export_last_toggle` | Timestamp of the last successful toggle (automatic mode only). |
| `sensor.sma_zero_export_status` | Last API operation status: `SUCCESS`, `ERROR_401`, `RATE_LIMITED`, `ERROR_5XX`, `NETWORK_ERROR`, `DATA_ERROR`, or `VALIDATION_MISMATCH`. |
| `sensor.sma_zero_export_validation` | Feed-in validation result: `disabled`, `success`, or `failed`. |
| `sensor.sma_zero_export_api_latency` | Last API round-trip time in milliseconds. |

### Binary Sensors

| Entity | Description |
|---|---|
| `binary_sensor.sma_zero_export_problem_detected` | `On` when the integration is degraded or failed; `Off` when healthy. |

### Select

| Entity | Description |
|---|---|
| `select.sma_zero_export_control_mode` | Current control mode. Change directly from the dashboard to switch modes. Options: `Automatic`, `Manual ON`, `Manual OFF`. |

---

## Services

### `sma_zero_export.set_mode`

Set the control mode from an automation or script.

```yaml
service: sma_zero_export.set_mode
data:
  mode: automatic   # or: manual_on, manual_off
```

Switching to `manual_on` or `manual_off` writes the corresponding state to the portal once and suspends all automatic activity until you switch back to `automatic`.

### `sma_zero_export.refresh`

Force an immediate portal state read. In automatic mode this also re-runs the control algorithm.

```yaml
service: sma_zero_export.refresh
```

---

## Example Dashboard Card

```yaml
type: entities
title: SMA Zero Export
entities:
  - entity: select.sma_zero_export_control_mode
    name: Control Mode
  - entity: sensor.sma_zero_export_state
    name: Portal State
  - entity: sensor.sma_zero_export_status
    name: API Status
  - entity: binary_sensor.sma_zero_export_problem_detected
    name: Problem
  - entity: sensor.sma_zero_export_validation
    name: Feed-In Validation
  - entity: sensor.sma_zero_export_last_toggle
    name: Last Toggle
  - entity: sensor.sma_zero_export_api_latency
    name: API Latency (ms)
```

---

## Example Automation

Disable automatic control every night at 23:00 and set Zero Export OFF, then re-enable automatic control at 06:00:

```yaml
automation:
  - alias: "Zero Export: disable at night"
    trigger:
      platform: time
      at: "23:00:00"
    action:
      service: sma_zero_export.set_mode
      data:
        mode: manual_off

  - alias: "Zero Export: re-enable at morning"
    trigger:
      platform: time
      at: "06:00:00"
    action:
      service: sma_zero_export.set_mode
      data:
        mode: automatic
```

---

## Troubleshooting

**Setup fails with "Invalid credentials"**
Verify your username and password by logging in at [ennexos.sunnyportal.com](https://ennexos.sunnyportal.com/). Make sure you are using the same account that has access to the plant.

**Setup fails with "Cannot connect"**
Check that the plant ID is correct and that your Home Assistant instance has outbound internet access.

**`sensor.sma_zero_export_state` shows `unknown`**
The integration could not parse the response from the SMA API. Enable debug logging in the options and check the Home Assistant logs for details.

**`binary_sensor.sma_zero_export_problem_detected` is `On`**
Check `sensor.sma_zero_export_status` for the error type. If it shows `ERROR_401`, your tokens have expired and re-authentication failed — try reloading the integration from **Settings → Devices & Services**. If it shows `RATE_LIMITED`, the integration will automatically back off and retry after 10 minutes.

**Zero Export is not toggling as expected**
- Confirm the price sensor is reporting a numeric value (check its state in Developer Tools)
- Check whether the minimum toggle interval is preventing a change
- Enable debug logging and watch the logs during a price change

**Diagnostics**
Go to **Settings → Devices & Services → SMA Zero Export → three-dot menu → Download diagnostics** for a full snapshot of the integration's runtime state, suitable for attaching to a bug report.

---

## Contributing

Issues and pull requests are welcome at [github.com/fesp/sma_zero_export](https://github.com/fesp/sma_zero_export).

---

## License

MIT
