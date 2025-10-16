# src/saygift_light_bridge/light_controller.py

import requests
import logging
from .config import config

log = logging.getLogger(__name__)


class LightController:
    """
    A class to encapsulate all API communication with the Saygift cloud service.
    This acts as the "driver" for the smart light.
    """

    def __init__(self):
        """
        Initializes the LightController, loading all necessary information from the config.
        """
        # Load device identifiers from the config
        self.serial_number = config.light.serial_number
        self.device_id = config.light.id

        # Load cloud API settings from the config
        self.control_url = config.cloud.control_url
        self.status_url = config.cloud.status_url
        self.timeout = config.cloud.request_timeout

        # Prepare the request headers. Based on our research, these are the only
        # headers required for the server to accept the request.
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://h5.saygift.cc",
            "Referer": "https://h5.saygift.cc/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
        }

        log.info(f"LightController initialized for SN: {self.serial_number}")

    def get_state(self) -> dict | None:
        """
        Polls the cloud API to get the current state of the light.

        Returns:
            A dictionary representing the light's state (e.g., {"state": "ON", "brightness": 255})
            or None if the request fails.
        """
        log.debug("Attempting to get device state from cloud...")
        params = {'serialNumber': self.serial_number}
        try:
            response = requests.get(
                self.status_url,
                headers=self.headers,
                params=params,
                timeout=self.timeout
            )
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()
            response_json = response.json()

            if response_json.get('flag') and 'data' in response_json:
                device_data = response_json['data']
                luminance = int(device_data.get('luminance', 0))
                is_on = luminance > 0

                # Convert the device's 0-100 brightness scale to Home Assistant's 0-255 scale
                brightness_255 = round(luminance * 2.55) if is_on else 0

                state = {"state": "ON" if is_on else "OFF", "brightness": brightness_255}
                log.debug(f"Successfully polled state: {state}")
                return state
            else:
                log.warning(f"API returned failure flag: {response_json.get('errMessage')}")
                return None

        except requests.exceptions.RequestException as e:
            log.error(f"Network error while getting state: {e}")
            return None
        except (ValueError, KeyError) as e:
            log.error(f"Error parsing state response from API: {e}")
            return None

    def set_state(self, power: bool, brightness: int = None, light_type: int = 3) -> bool:
        """
        Sends a command to the cloud API to set the light's state.

        Args:
            power (bool): The desired power state (True for ON, False for OFF).
            brightness (int, optional): The desired brightness on a 0-255 scale (Home Assistant's scale).
                                       This is only used if power is True. Defaults to None.
            light_type (int, optional): The light mode. Defaults to 3.

        Returns:
            True if the command was sent and the API confirmed success, False otherwise.
        """
        log.debug(f"Attempting to set device state: power={power}, brightness={brightness}")
        payload = {
            'serialNumber': self.serial_number,
            'id': self.device_id,
            'lightType': light_type
        }

        if not power:
            payload['luminance'] = 0
        elif brightness is not None:
            # Convert Home Assistant's 0-255 scale to the device's 0-100 scale
            device_brightness = max(1, round(brightness / 2.55))
            payload['luminance'] = device_brightness
        # If power is ON but brightness is None, the light will likely turn on at its previous brightness.

        try:
            response = requests.post(
                self.control_url,
                headers=self.headers,
                data=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            response_json = response.json()

            if response_json.get('flag'):
                log.info(f"Successfully set state with payload: {payload}")
                return True
            else:
                log.warning(f"API returned failure flag while setting state: {response_json.get('errMessage')}")
                return False

        except requests.exceptions.RequestException as e:
            log.error(f"Network error while setting state: {e}")
            return False
