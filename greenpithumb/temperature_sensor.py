import logging

logger = logging.getLogger(__name__)


class TemperatureSensor(object):
    """Wrapper for a temperature sensor."""

    def __init__(self, sensor):
        """Creates a new TemperatureSensor wrapper.

        Args:
            sensor: sensor instance that returns temperature readings.
        """
        self._sensor = sensor

    def temperature(self):
        """Returns ambient temperature in Celcius."""
        temperature = self._sensor.temperature()
        logging.info('temperature reading = %.1f C', temperature)
        return temperature
