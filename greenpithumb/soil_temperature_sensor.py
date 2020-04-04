import logging

logger = logging.getLogger(__name__)


class SoilTemperatureSensor(object):
    """Wrapper for a soil temperature sensor."""

    def __init__(self, sensor):
        """Creates a new SoilTemperatureSensor wrapper.

        Args:
            sensor: sensor instance that returns temperature readings.
        """
        self._sensor = sensor

    def temperature(self):
        """Returns soil temperature in Celcius."""
        temperature = self._sensor.temperature()
        logging.info('soil temperature reading = %.1f C', temperature)
        return temperature
