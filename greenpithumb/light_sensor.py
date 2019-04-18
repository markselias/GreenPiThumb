import logging

logger = logging.getLogger(__name__)

_LIGHT_SENSOR_MIN_VALUE = 0
_LIGHT_SENSOR_MAX_VALUE = 1023


class LightSensor(object):
    """Wrapper for light sensor."""

    def __init__(self, sensor):
        """Creates a new LightSensor wrapper.

        Args:
            sensor: sensor instance that returns brightness readings.
        """
        self._sensor = sensor

    def light(self):
        """Returns light level as percentage."""
        light = self._sensor.light()
        logger.info('light reading = %d', light)

        light_as_pct = 100 * (float(light - _LIGHT_SENSOR_MIN_VALUE) / (
            _LIGHT_SENSOR_MAX_VALUE - _LIGHT_SENSOR_MIN_VALUE))

        return light_as_pct
