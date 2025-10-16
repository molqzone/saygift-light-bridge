# src/saygift_light_bridge/config.py

import sys
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import toml

# --- Configuration Constants ---

# The primary path for the configuration file, used in a production environment (e.g., on the R3S).
PRIMARY_CONFIG_PATH = Path("/etc/saygift-light-bridge/config.toml")
# A secondary, fallback path for easier local development. This is also where a new config will be generated.
SECONDARY_CONFIG_PATH = Path("config.toml")

log = logging.getLogger(__name__)

# --- Default Configuration Template ---
# This multi-line string holds the content for a newly generated config file.
DEFAULT_CONFIG_CONTENT = """# Saygift Light Bridge Configuration
# ==================================
# This file was auto-generated. Please fill in your device-specific values below.

[light]
# The unique identifiers for your light device.
# You can find these by inspecting the payload of the API calls in your browser's F12 tools.
serial_number = "PLEASE_FILL_IN_YOUR_SERIAL_NUMBER"
id = "PLEASE_FILL_IN_YOUR_DEVICE_ID"


[cloud]
# The API endpoints discovered through reverse engineering.
# It's unlikely you will need to change these unless the manufacturer updates their API.
control_url = "https://h5.saygift.cc/api/dvsn/saveDevice"
status_url = "https://h5.saygift.cc/api/dvsn/findBySerialNumber"

# Network request timeout in seconds.
request_timeout = 10


[mqtt]
# -- Core Connection Settings --
# IP address or hostname of your MQTT broker (e.g., Mosquitto on your R3S).
broker = "127.0.0.1"
# The standard MQTT port. 1883 for unencrypted, 8883 for encrypted (TLS).
port = 1883
# Optional: Fill these in if your MQTT broker requires authentication.
username = ""
password = ""
# A unique ID for this client. Helps in debugging on the broker side.
client_id = "saygift-light-bridge-r3s"

# -- Home Assistant Integration Settings --
# The base topic used for Home Assistant's MQTT discovery and control.
base_topic = "homeassistant/light/saygift_living_room"

# Suffix for the availability topic. This is highly recommended for robust HA integration.
availability_topic_suffix = "availability"
payload_available = "online"
payload_not_available = "offline"

# -- MQTT Quality of Service --
qos = 1
# Whether the state and availability messages should be retained by the broker.
retain = true

# -- Application Behavior --
# Interval in seconds for polling the light's actual status from the cloud.
polling_interval = 30
"""

# --- Dataclass Definitions ---
@dataclass
class LightConfig:
    """Configuration specific to the light device itself."""
    serial_number: str
    id: str

@dataclass
class CloudConfig:
    """Configuration for the Saygift cloud API."""
    control_url: str
    status_url: str
    request_timeout: int

@dataclass
class MqttConfig:
    """Configuration for the MQTT client and broker connection."""
    broker: str
    port: int
    client_id: str
    base_topic: str
    availability_topic_suffix: str
    payload_available: str
    payload_not_available: str
    qos: int
    retain: bool
    polling_interval: int
    username: Optional[str] = None
    password: Optional[str] = None

@dataclass
class Config:
    """The main configuration object holding all sections."""
    light: LightConfig
    cloud: CloudConfig
    mqtt: MqttConfig


def _generate_default_config(path: Path):
    """
    Writes the default configuration template to the specified path and exits.
    """
    log.info(f"Configuration file not found. Generating a new template at: {path}")
    try:
        # Ensure parent directory exists, though for the local path it's not strictly necessary.
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_CONFIG_CONTENT)
        log.info("✅ Successfully created 'config.toml' template.")
    except IOError as e:
        log.fatal(f"❌ Could not write default configuration file to {path}: {e}")
    
    # IMPORTANT: Exit after generation, forcing the user to edit the new file.
    log.fatal("👉 Please edit the newly created config.toml with your device details and run the application again.")
    sys.exit(1)


def load_config() -> Config:
    """
    Loads the application configuration from a TOML file.
    If the file is not found, it generates a default template and exits.
    """
    config_path = None
    if PRIMARY_CONFIG_PATH.exists():
        config_path = PRIMARY_CONFIG_PATH
    elif SECONDARY_CONFIG_PATH.exists():
        config_path = SECONDARY_CONFIG_PATH
    else:
        # If neither path exists, generate a new file in the local directory.
        _generate_default_config(SECONDARY_CONFIG_PATH)

    log.info(f"Loading configuration from: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = toml.load(f)

        required_sections = ["light", "cloud", "mqtt"]
        for section in required_sections:
            if section not in data:
                raise KeyError(f"Configuration file is missing required section: '[{section}]'")

        return Config(
            light=LightConfig(**data["light"]),
            cloud=CloudConfig(**data["cloud"]),
            mqtt=MqttConfig(**data["mqtt"]),
        )
    except toml.TomlDecodeError as e:
        log.fatal(f"Error parsing TOML file at '{config_path}': {e}")
        sys.exit(1)
    except (KeyError, TypeError) as e:
        log.fatal(f"Configuration file '{config_path}' is missing a required key or has a malformed value: {e}")
        sys.exit(1)
    except Exception as e:
        log.fatal(f"An unexpected error occurred while loading configuration: {e}")
        sys.exit(1)

# Create a single, globally accessible instance of the configuration.
config: Config = load_config()