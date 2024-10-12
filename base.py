"""Base Class to manage Arlo's Base Stations."""

import logging
import json
from device import Device


class Base(Device):
    """
    Class representing an Arlo base station.

    Attributes:
        name (str): Internal name of the base (not necessarily identical to Arlo).
        status_interval (int): Interval of status messages from generator (seconds).
    """

    def __init__(self, arlo_base, status_interval: int):
        """
        Initialize the Base instance.

        Args:
            arlo_base (ArloBase): Arlo base station object.
            status_interval (int): Interval of status messages from generator (seconds).
        """
        super().__init__(arlo_base, status_interval)
        logging.info("Base added: %s", self.name)

    async def on_event(self, attr: str, value):
        """
        Distribute events to the correct handler.

        Args:
            attr (str): Attribute name.
            value: Attribute value.
        """
        match attr:
            case "activeMode":
                self.state_event.set()
                logging.info("%s mode: %s", self.name, value)
            case _:
                pass

    def get_status(self) -> dict:
        """
        Get the status of the base station.

        Returns:
            dict: Status information including mode and siren state.
        """
        return {"mode": self._arlo.mode, "siren": self._arlo.siren_state}

    async def mqtt_control(self, payload: str):
        """
        Handle incoming MQTT commands.

        Args:
            payload (str): MQTT payload.
        """
        handlers = {"mode": self.set_mode, "siren": self.set_siren}

        try:
            payload = json.loads(payload)
            for k, v in payload.items():
                if k in handlers:
                    self._event_loop.run_in_executor(None, handlers[k], v)
        except Exception:
            logging.warning("%s: Invalid data for MQTT control", self.name)

    def set_mode(self, mode: str):
        """
        Set the mode of the base station.

        Args:
            mode (str): Mode to set.
        """
        try:
            mode = mode.lower()
            if mode not in self._arlo.available_modes:
                raise ValueError
            self._arlo.mode = mode
        except (AttributeError, ValueError):
            logging.warning("%s: Invalid mode, ignored", self.name)

    def set_siren(self, state):
        """
        Set the siren state (on/off/on with specified duration and volume).

        Args:
            state (str or dict): Siren state ("on", "off", or a dict with duration and volume).
        """
        match state:
            case "on":
                self._arlo.siren_on()
            case "off":
                self._arlo.siren_off()
            case dict():
                try:
                    self._arlo.siren_on(**state)
                except AttributeError:
                    logging.warning("%s: Invalid siren arguments", self.name)
            case _:
                pass

    @property
    def state_event(self):
        """
        Get the state event object.

        Returns:
            asyncio.Event: The state event object.
        """
        return self._state_event
