import datetime
import logging
import threading
import struct

import pytz

logger = logging.getLogger(__name__)

# Maximum time a sensor reading can be used for, in seconds
_FRESHNESS_THRESHOLD = 50


class CachingArduinoSensors(object):
    """Wrapper around the sensor connected to the Arduino that caches sensor readings.

    Reads and returns temperature and humidity levels while also caching these
    values to ensure that the sensor is not polled at too high of a frequency.
    This class is thread-safe.
    """

    def __init__(self, arduino_read_write_obj, clock):
        """Creates a new CachingArduinoSensors object.

        Args:
            arduino_read_write_obj: An object that manages arduino UART.
            clock: A clock interface
        """
        self._arduino_read_write_obj = arduino_read_write_obj
        self._clock = clock
        self._last_reading_time = datetime.datetime.min.replace(tzinfo=pytz.utc)
        self._last_reading = None
        self._lock = threading.Lock()

    def _read_arduino(self):
        """Returns current or recent sensor values.

        Returns cached values if the sensor has been polled recently enough,
        otherwise polls the arduino and returns current values.
        """
        with self._lock:
            now = self._clock.now()
            if (now - self._last_reading_time).total_seconds() >= (
                    _FRESHNESS_THRESHOLD):
                self._last_reading_time = now
                self._last_reading = self._get_current_values()
                logger.info('Arduino raw reading = %s', self._last_reading)
            else:
                logger.info(
                    'read Arduino too recently, returning cached reading = %s',
                    self._last_reading)

        return self._last_reading

    def _get_current_values(self):
        """Returnes new sensor values from the Arduino
        """
        self._arduino_read_write_obj.txBuff[0] = 's'
        self._arduino_read_write_obj.send(1)
        while not self._arduino_read_write_obj.available():
            if self._arduino_read_write_obj.status < 0:
                print('ERROR: {}'.format(self._arduino_read_write_obj.status))
        sensor_values = {}
        sensor_values["humidity"] = struct.unpack('f', bytes(self._arduino_read_write_obj.rxBuff[0:4]))[0]
        sensor_values["temperature"] = struct.unpack('f', bytes(self._arduino_read_write_obj.rxBuff[4:8]))[0]
        return sensor_values

    def humidity(self):
        """Returns a recent relative humidity reading."""
        humidity = self._read_arduino()["humidity"]
        return humidity

    def temperature(self):
        """Returns a recent ambient temperature reading in Celsius."""
        temperature = self._read_arduino()["temperature"]
        return temperature
