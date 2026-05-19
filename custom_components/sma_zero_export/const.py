"""Constants for the SMA Zero Export integration."""

DOMAIN = "sma_zero_export"
PLATFORMS = ["sensor", "binary_sensor", "select"]

# ── SMA / Keycloak endpoints ──────────────────────────────────────────────────
REALM_URL = "https://login.sma.energy/auth/realms/SMA"
CLIENT_ID = "SPpbeOS"
REDIRECT_URI = "https://ennexos.sunnyportal.com/"
UIAPI_BASE = "https://uiapi.sunnyportal.com/api/v1"

# ── Config entry data keys (credentials + tokens) ────────────────────────────
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PLANT_ID = "plant_id"
CONF_PRICE_SENSOR = "price_sensor"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ID_TOKEN = "id_token"

# ── Options keys ──────────────────────────────────────────────────────────────
OPT_AUTOMATIC_CONTROL = "automatic_control"
OPT_MANUAL_STATE = "manual_state"          # "on" | "off"
OPT_DEADBAND = "deadband"
OPT_MIN_TOGGLE_INTERVAL = "min_toggle_interval"   # minutes
OPT_POLLING_INTERVAL = "polling_interval"          # minutes
OPT_VALIDATION_ENABLED = "validation_enabled"
OPT_ENERGY_METER_SENSOR = "energy_meter_sensor"
OPT_DISCREPANCY_THRESHOLD = "discrepancy_threshold"  # watts
OPT_NOTIFICATIONS_ENABLED = "notifications_enabled"
OPT_NOTIFY_SERVICE = "notify_service"
OPT_FAILSAFE_TIMEOUT = "failsafe_timeout"   # minutes
OPT_DEBUG_LOGGING = "debug_logging"

# ── Option defaults ───────────────────────────────────────────────────────────
DEFAULT_AUTOMATIC_CONTROL = True
DEFAULT_MANUAL_STATE = "off"
DEFAULT_DEADBAND = 0.1
DEFAULT_MIN_TOGGLE_INTERVAL = 30
DEFAULT_POLLING_INTERVAL = 5
DEFAULT_VALIDATION_ENABLED = False
DEFAULT_DISCREPANCY_THRESHOLD = 200
DEFAULT_NOTIFICATIONS_ENABLED = False
DEFAULT_NOTIFY_SERVICE = ""
DEFAULT_FAILSAFE_TIMEOUT = 60
DEFAULT_DEBUG_LOGGING = False

# ── Control mode values ───────────────────────────────────────────────────────
CONTROL_MODE_AUTOMATIC = "automatic"
CONTROL_MODE_MANUAL_ON = "manual_on"
CONTROL_MODE_MANUAL_OFF = "manual_off"
CONTROL_MODES = [CONTROL_MODE_AUTOMATIC, CONTROL_MODE_MANUAL_ON, CONTROL_MODE_MANUAL_OFF]

# ── API status values ─────────────────────────────────────────────────────────
STATUS_SUCCESS = "SUCCESS"
STATUS_ERROR_401 = "ERROR_401"
STATUS_ERROR_429 = "RATE_LIMITED"
STATUS_ERROR_5XX = "ERROR_5XX"
STATUS_NETWORK_ERROR = "NETWORK_ERROR"
STATUS_DATA_ERROR = "DATA_ERROR"
STATUS_VALIDATION_MISMATCH = "VALIDATION_MISMATCH"

# ── Validation sensor values ──────────────────────────────────────────────────
VALIDATION_DISABLED = "disabled"
VALIDATION_SUCCESS = "success"
VALIDATION_FAILED = "failed"

# ── Health states ─────────────────────────────────────────────────────────────
HEALTH_HEALTHY = "healthy"
HEALTH_DEGRADED = "degraded"
HEALTH_FAILED = "failed"

# ── Scheduler intervals ───────────────────────────────────────────────────────
VALIDATION_INTERVAL_SECONDS = 30
FAILSAFE_INTERVAL_SECONDS = 60

# ── HTTP / retry settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT_SECONDS = 20
MAX_AUTH_RETRIES = 1          # how many times to retry after a 401
RETRY_BACKOFF_BASE = 2.0      # seconds; doubled each attempt for 5xx/network
MAX_5XX_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 600   # 10 minutes
