# src/saygift_light_bridge/mqtt_client.py

import paho.mqtt.client as mqtt
import logging
import json
import time
import threading
from .config import config
from .light_controller import LightController

log = logging.getLogger(__name__)


class MqttClient:
    """
    Handles all MQTT communication, acting as a bridge between Home Assistant and the LightController.
    """

    def __init__(self, controller: LightController):
        """
        Initializes the MQTT client.

        Args:
            controller: An instance of the LightController to interact with the device.
        """
        self.controller = controller
        self.client = mqtt.Client(client_id=config.mqtt.client_id)

        # Set username and password if they are provided in the config
        if config.mqtt.username:
            self.client.username_pw_set(config.mqtt.username, config.mqtt.password)

        # Assign callback functions for MQTT events
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        # Construct the full topic strings from the base topic
        self.command_topic = f"{config.mqtt.base_topic}/set"
        self.state_topic = f"{config.mqtt.base_topic}/state"
        self.availability_topic = (
            f"{config.mqtt.base_topic}/{config.mqtt.availability_topic_suffix}"
        )

        # A threading lock is crucial for robustness. It prevents race conditions between
        # the background polling thread and the main thread when accessing the controller.
        self.state_lock = threading.Lock()

    def on_connect(self, client, userdata, flags, rc):
        """Callback executed when the client connects to the MQTT broker."""
        if rc == 0:
            log.info("Successfully connected to MQTT Broker!")
            # Subscribe to the command topic to receive instructions from Home Assistant
            client.subscribe(self.command_topic)
            log.info(f"Subscribed to command topic: {self.command_topic}")
            # Announce that the bridge is online. The 'retain=True' flag ensures that
            # Home Assistant sees the device as available even if HA restarts.
            client.publish(
                self.availability_topic,
                config.mqtt.payload_available,
                retain=config.mqtt.retain,
            )
            # Immediately publish the current state upon connection
            self.publish_state()
        else:
            log.error(f"Failed to connect to MQTT Broker, return code: {rc}")

    def on_disconnect(self, client, userdata, rc):
        """Callback executed when the client disconnects from the MQTT broker."""
        log.warning(
            f"Disconnected from MQTT Broker with result code: {rc}. Paho-MQTT will attempt to reconnect automatically."
        )

    def on_message(self, client, userdata, msg):
        """Callback executed when a message is received on a subscribed topic."""
        # This is where we receive commands from Home Assistant
        log.debug(f"Received message on topic '{msg.topic}': {msg.payload.decode()}")

        try:
            # Decode the payload from bytes and parse it as JSON
            payload = json.loads(msg.payload.decode())

            # Extract state and brightness from the HA command payload
            power = payload.get("state", "OFF").upper() == "ON"
            brightness = payload.get("brightness")

            # Call the controller to execute the command
            success = self.controller.set_state(power=power, brightness=brightness)

            if success:
                # To ensure we report the TRUE state, we wait a moment for the cloud
                # to process the command, then we poll for the new state.
                log.info("Command sent successfully. Scheduling state refresh.")
                time.sleep(1.5)  # Wait 1.5s for cloud state to update
                self.publish_state()
            else:
                log.warning(
                    "Controller failed to execute command. State will be re-synced on next poll."
                )

        except json.JSONDecodeError:
            log.error("Received invalid JSON on command topic. Message ignored.")
        except Exception as e:
            log.error(f"An unexpected error occurred while processing command: {e}")

    def publish_state(self):
        """
        Gets the current state from the light controller and publishes it to the state topic.
        This method is thread-safe.
        """
        with self.state_lock:
            log.debug("Acquired lock to poll and publish state.")
            current_state = self.controller.get_state()
            if current_state:
                # Convert the state dictionary to a JSON string and publish
                self.client.publish(
                    self.state_topic,
                    json.dumps(current_state),
                    retain=config.mqtt.retain,
                )
                log.debug(f"Published state: {current_state}")
            else:
                log.warning("Could not get state from controller; skipping publish.")

    def periodic_polling(self):
        """
        A background task that runs in a separate thread to periodically poll the device state.
        """
        log.info(
            f"Starting periodic polling every {config.mqtt.polling_interval} seconds."
        )
        while True:
            time.sleep(config.mqtt.polling_interval)
            log.debug("Periodic polling trigger...")
            self.publish_state()

    def start(self):
        """
        Connects to the MQTT broker and starts the main loop.
        """
        # Set the "Last Will and Testament". This is a crucial feature for robustness.
        # If the bridge disconnects ungracefully, the broker will automatically publish
        # the 'offline' message to the availability topic on our behalf.
        self.client.will_set(
            self.availability_topic,
            config.mqtt.payload_not_available,
            retain=config.mqtt.retain,
        )

        try:
            log.info(
                f"Connecting to MQTT broker at {config.mqtt.broker}:{config.mqtt.port}..."
            )
            self.client.connect(config.mqtt.broker, config.mqtt.port, 60)

            # Start the background polling thread. It's set as a 'daemon' so that it
            # automatically exits when the main application exits.
            poll_thread = threading.Thread(target=self.periodic_polling)
            poll_thread.daemon = True
            poll_thread.start()

            # The 'loop_forever' call is a blocking function that handles all MQTT network
            # traffic, processes messages, and manages reconnections automatically.
            self.client.loop_forever()
        except ConnectionRefusedError:
            log.fatal(
                "Connection refused by MQTT broker. Check broker address and port."
            )
        except OSError as e:
            log.fatal(f"Could not connect to MQTT broker due to a network error: {e}")
        except Exception as e:
            log.fatal(f"An unexpected error occurred while starting MQTT client: {e}")
