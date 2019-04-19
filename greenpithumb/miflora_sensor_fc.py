import datetime
import logging
import threading

import pytz

from btlewrap import available_backends, GatttoolBackend
from miflora.miflora_poller import MiFloraPoller, \
    MI_CONDUCTIVITY, MI_MOISTURE, MI_LIGHT, MI_TEMPERATURE, MI_BATTERY

logger = logging.getLogger(__name__)

# Maximum time a sensor reading can be used for, in seconds
_FRESHNESS_THRESHOLD = 2
# Position of humidity value in the tuple returned from DHT11 read function.
_HUMIDITY_INDEX = 0
# Position of  temperature value in the tuple returned from DHT11 read function.
_TEMPERATURE_INDEX = 1


class CachingMiFlora(object):
    """Wrapper around a MiFlora that caches sensor readings.

    Reads and returns temperature, soil moisture and light levels while also caching these
    values to ensure that the sensor is not polled at too high of a frequency.
    This class is thread-safe.
    """

    def __init__(self,
                 # miflora_read_func,
                 clock):
        """Creates a new CachingMiFlora object.

        Args:
            miflora_read_func: A function that returns the temperature, soil moisture and light readings from a Mi Flora sensor.
            clock: A clock interface
        """
        self._miflora_read_func = MiFloraPoller("C4:7C:8D:6A:6B:3A", GatttoolBackend)
        self._clock = clock
        self._last_reading_time = datetime.datetime.min.replace(tzinfo=pytz.utc)
        self._last_reading = None
        self._lock = threading.Lock()

    def _read_miflora(self):
        """Returns current or recent temperature, soil moisture and light values.

        Returns cached values if the sensor has been polled recently enough,
        otherwise polls the sensor and returns current values.
        """
        with self._lock:
            now = self._clock.now()
            if (now - self._last_reading_time).total_seconds() >= (
                    _FRESHNESS_THRESHOLD):
                self._last_reading_time = now
                self._last_reading = self._miflora_read_func()
                logger.info('MiFlora raw reading = %s', self._last_reading)
            else:
                logger.info(
                    'read MiFlora too recently, returning cached reading = %s',
                    self._last_reading)

        return self._last_reading

    def soil_moisture(self):
        """Returns a recent relative humidity reading."""
        measurement = self._read_miflora()
        moisture = measurement.parameter_value(MI_MOISTURE)
        return moisture

    def temperature(self):
        """Returns a recent ambient temperature reading in Celsius."""
        measurement = self._read_miflora()
        temperature = measurement.parameter_value(MI_TEMPERATURE)
        return temperature

    def light(self):
        """Returns a recent ambient light reading."""
        measurement = self._read_miflora()
        light = measurement.parameter_value(MI_LIGHT)
        return light

    def battery(self):
        """Returns a recent battery reading."""
        measurement = self._read_miflora()
        battery = measurement.parameter_value(MI_BATTERY)
        return battery
