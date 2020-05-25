import argparse
import contextlib
import datetime
import logging
import queue
import time
from time import sleep

# import Adafruit_DHT
# import Adafruit_MCP3008
# import picamera
# import RPi.GPIO as GPIO

import adc_thread_safe
import camera_manager
import clock
import db_store
import dht11
from miflora_sensor_fc import CachingMiFlora
import arduino_sensors
import humidity_sensor
import light_sensor
import pi_io
import poller
import pump
import pump_history
import record_processor
import sleep_windows
import soil_moisture_sensor
import temperature_sensor
import soil_temperature_sensor
import wiring_config_parser
import actuator_observer
import cv_cam

from btlewrap import available_backends, GatttoolBackend

from miflora.miflora_poller import MiFloraPoller
from pySerialTransfer import pySerialTransfer as txfer

logger = logging.getLogger(__name__)


def configure_logging(verbose):
    """Configure the root logger for log output."""
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s %(name)-15s %(levelname)-4s %(message)s',
        '%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    if verbose:
        root_logger.setLevel(logging.INFO)
    else:
        root_logger.setLevel(logging.WARNING)


def read_wiring_config(config_filename):
    """Parses wiring config from a file."""
    logger.info('reading wiring config at "%s"', config_filename)
    with open(config_filename) as config_file:
        return wiring_config_parser.parse(config_file.read())


def make_adc(wiring_config):
    """Creates ADC instance based on the given wiring_config.

    Args:
        wiring_config: Wiring configuration for the GreenPiThumb.

    Returns:
        An ADC instance for the specified wiring config.
    """
    # The MCP3008 spec and Adafruit library use different naming for the
    # Raspberry Pi GPIO pins, so we translate as follows:
    # * CLK -> CLK
    # * CS/SHDN -> CS
    # * DOUT -> MISO
    # * DIN -> MOSI
    return adc_thread_safe.Adc(
        Adafruit_MCP3008.MCP3008(
            clk=wiring_config.gpio_pins.mcp3008_clk,
            cs=wiring_config.gpio_pins.mcp3008_cs_shdn,
            miso=wiring_config.gpio_pins.mcp3008_dout,
            mosi=wiring_config.gpio_pins.mcp3008_din))


# def make_dht11_sensors(wiring_config):
#     """Creates sensors derived from the DHT11 sensor.
#
#     Args:
#         wiring_config: Wiring configuration for the GreenPiThumb.
#
#     Returns:
#         A two-tuple where the first element is a temperature sensor and the
#         second element is a humidity sensor.
#     """
#     local_dht11 = dht11.CachingDHT11(
#         lambda: Adafruit_DHT.read_retry(Adafruit_DHT.DHT11, wiring_config.gpio_pins.dht11),
#         clock.Clock())
#     return soil_temperature_sensor.TemperatureSensor(
#         local_dht11), humidity_sensor.HumiditySensor(local_dht11),

def make_arduino_sensors(arduino_uart):
    """Creates sensors derived from the arduino sensors.

    Args:
        arduino_uart: Arduino serial port. (pySerialTransfer object)

    Returns:
        A two-tuple where the first element is a temperature sensor and the
        second element is a humidity sensor.
    """
    local_arduino_sensors = arduino_sensors.CachingArduinoSensors(
        arduino_uart,
        clock.Clock())
    return temperature_sensor.TemperatureSensor(local_arduino_sensors), humidity_sensor.HumiditySensor(local_arduino_sensors), actuator_observer.ActuatorObserver(local_arduino_sensors)

def make_miflora_sensors(miflora_mac):
    """Creates sensors derived from the Mi Flora sensor.

    Args:
        miflora_mac: Miflora bluetooth mac address.

    Returns:
        A 3-tuple where the first element is a temperature sensor, the
        second element is a soil moisture sensor and the third element is a light sensor.
    """
    local_miflora = CachingMiFlora(
        lambda: MiFloraPoller(miflora_mac, GatttoolBackend),
        clock.Clock())
    return soil_temperature_sensor.SoilTemperatureSensor(local_miflora), soil_moisture_sensor.SoilMoistureSensor(local_miflora), light_sensor.LightSensor(local_miflora)


# def make_soil_moisture_sensor(adc, raspberry_pi_io, wiring_config):
#     return soil_moisture_sensor.SoilMoistureSensor(
#         adc, raspberry_pi_io, wiring_config.adc_channels.soil_moisture_sensor,
#         wiring_config.gpio_pins.soil_moisture)


def make_light_sensor(adc, wiring_config):
    return light_sensor.LightSensor(adc,
                                    wiring_config.adc_channels.light_sensor)


def make_camera_manager(rotation, image_path, light_sensor):
    """Creates a camera manager instance.

    Args:
        rotation: The amount (in whole degrees) to rotate the camera image.
        image_path: The directory in which to save images.
        light_sensor: A light sensor instance.

    Returns:
        A CameraManager instance with the given settings.
    """
    # camera = picamera.PiCamera(resolution=picamera.PiCamera.MAX_RESOLUTION)
    camera = cv_cam.CameraCV(0)
    # camera.rotation = rotation
    return camera_manager.CameraManager(image_path,
                                        clock.Clock(), camera, light_sensor)


def make_pump_manager(pump_id, moisture_threshold, sleep_windows, arduino_uart,
                      # wiring_config,
                      pump_amount, pump_rate, db_connection, pump_interval):
    """Creates a pump manager instance.

    Args:
        moisture_threshold: The minimum moisture level below which the pump
            turns on.
        sleep_windows: Sleep windows during which pump will not turn on.
        arduino_uart: serial communication instance for the GreenPiThumb.
        wiring_config: Wiring configuration for the GreenPiThumb.
        pump_amount: Amount (in mL) to pump on each run of the pump.
        db_connection: Database connection to use to retrieve pump history.
        pump_interval: Maximum amount of time between pump runs.

    Returns:
        A PumpManager instance with the given settings.
    """
    logger.info('Initializing pump %d', pump_id)
    water_pump = pump.Pump(pump_id,
                           arduino_uart,
                           clock.Clock(), 36,
                           pump_rate
                           # wiring_config.gpio_pins.pump
                           )
    pump_scheduler = pump.PumpScheduler(clock.LocalClock(), sleep_windows)
    pump_timer = clock.Timer(clock.Clock(), pump_interval)
    last_pump_time = pump_history.last_pump_time(
        db_store.WateringEventStore(db_connection), pump_id)
    if last_pump_time:
        logger.info('last watering was at %s', last_pump_time)
        time_remaining = max(
            datetime.timedelta(seconds=0),
            (last_pump_time + pump_interval) - clock.Clock().now())
    else:
        logger.info('no previous watering found')
        time_remaining = datetime.timedelta(seconds=0)
    logger.info('time until until next watering: %s', time_remaining)
    pump_timer.set_remaining(time_remaining)
    return pump.PumpManager(water_pump, pump_scheduler, moisture_threshold,
                            pump_amount, pump_timer)

def make_climate_manager(desired_ambient_temperature, arduino_uart,
                      db_connection):
    """Creates a climate manager instance.

    Args:
        desired_ambient_temperature:
        arduino_uart: serial communication instance for the GreenPiThumb.
        db_connection: Database connection to use to retrieve pump history.

    Returns:
        A ClimateManager instance with the given settings.
    """
    water_pump = pump.Pump(arduino_uart,
                           clock.Clock(), 36
                           # wiring_config.gpio_pins.pump
                           )
    pump_scheduler = pump.PumpScheduler(clock.LocalClock(), sleep_windows)
    pump_timer = clock.Timer(clock.Clock(), pump_interval)
    last_pump_time = pump_history.last_pump_time(
        db_store.WateringEventStore(db_connection))
    if last_pump_time:
        logger.info('last watering was at %s', last_pump_time)
        time_remaining = max(
            datetime.timedelta(seconds=0),
            (last_pump_time + pump_interval) - clock.Clock().now())
    else:
        logger.info('no previous watering found')
        time_remaining = datetime.timedelta(seconds=0)
    logger.info('time until until next watering: %s', time_remaining)
    pump_timer.set_remaining(time_remaining)
    return pump.PumpManager(water_pump, pump_scheduler, moisture_threshold,
                            pump_amount, pump_timer)


def make_sensor_pollers(poll_interval, photo_interval, record_queue,
                        soil_temperature_sensor,
                        soil_moisture_sensor, ambient_temperature_sensor,
                        ambient_humidity_sensor, light_sensor,
                        camera_manager,
                        pump_managers, n_pumps, actuator_observer):
    """Creates a poller for each GreenPiThumb sensor.

    Args:
        poll_interval: The frequency at which to poll non-camera sensors.
        photo_interval: The frequency at which to capture photos.
        record_queue: Queue on which to put sensor reading records.
        soil_temperature_sensor: Sensor for measuring temperature.
        soil_moisture_sensor: Sensor for measuring soil moisture.
        ambient_temperature_sensor: Sensor for measuring ambient temperature.
        ambient_humidity_sensor: Sensor for measuring ambient humidity.
        light_sensor: Sensor for measuring light levels.
        camera_manager: Interface for capturing photos.
        pump_manager: Interface for turning water pump on and off.

    Returns:
        A list of sensor pollers.
    """
    logger.info('creating sensor pollers (poll interval=%ds")',
                poll_interval.total_seconds())
    utc_clock = clock.Clock()

    make_scheduler_func = lambda: poller.Scheduler(utc_clock, poll_interval)
    photo_make_scheduler_func = lambda: poller.Scheduler(utc_clock, photo_interval)
    poller_factory = poller.SensorPollerFactory(make_scheduler_func,
                                                record_queue)
    camera_poller_factory = poller.SensorPollerFactory(
        photo_make_scheduler_func, record_queue=None)

    pollers = []
    # pollers.append(poller_factory.create_soil_temperature_poller(soil_temperature_sensor))
    for pump_number in range(n_pumps):
        pollers.append(poller_factory.create_soil_watering_poller(
            soil_moisture_sensor,
            pump_managers[pump_number]))
    # pollers.append(poller_factory.create_climate_control_poller(
    #     ambient_temperature_sensor, ambient_humidity_sensor,
    #     actuator_observer))
    # pollers.append(poller_factory.create_light_poller(light_sensor))
    # pollers.append(camera_poller_factory.create_camera_poller(camera_manager))

    return pollers


def create_record_processor(db_connection, record_queue):
    """Creates a record processor for storing records in a database.

    Args:
        db_connection: Database connection to use to store records.
        record_queue: Record queue from which to process records.
    """
    return record_processor.RecordProcessor(
        record_queue,
        db_store.SoilMoistureStore(db_connection),
        db_store.LightStore(db_connection),
        db_store.HumidityStore(db_connection),
        db_store.TemperatureStore(db_connection),
        db_store.WateringEventStore(db_connection),
        db_store.SoilTemperatureStore(db_connection),
        db_store.PumpStateStore(db_connection),
        db_store.WindowStateStore(db_connection),
        db_store.MifloraBatteryStore(db_connection))


def main(args):
    configure_logging(args.verbose)
    logger.info('starting greenpithumb')
    # wiring_config = read_wiring_config(args.config_file)
    record_queue = queue.Queue()
    try:
        arduino_uart = txfer.SerialTransfer('/dev/ttyUSB0')
        arduino_uart.open()
        sleep(2)
    except:
        print("ERROR: Couldn't connect to Arduino")
        return
    n_pumps = args.n_pumps;
    # arduino_uart.txBuff[0] = 'a'
    # arduino_uart.send(1)
    # adc = make_adc(wiring_config)
    local_soil_temperature_sensor, local_soil_moisture_sensor, local_light_sensor = make_miflora_sensors("C4:7C:8D:6A:6B:3A")
    local_ambient_temperature_sensor, local_ambient_humidity_sensor, local_actuator_observer = make_arduino_sensors(arduino_uart)
    # local_soil_moisture_sensor = make_soil_moisture_sensor(
    #     adc, arduino_uart, wiring_config)
    # local_soil_temperature_sensor, local_humidity_sensor = make_dht11_sensors(
    #     wiring_config)
    # local_light_sensor = make_light_sensor(adc, wiring_config)
    camera_manager = make_camera_manager(args.camera_rotation, args.image_path,
                                         local_light_sensor)

    with contextlib.closing(
            db_store.open_or_create_db(args.db_file)) as db_connection:
        record_processor = create_record_processor(db_connection, record_queue)
        pump_managers = []
        for pump_number in range(n_pumps):
            pump_managers.append(
                make_pump_manager(
                    pump_number,
                    int(args.moisture_threshold[pump_number]),
                    sleep_windows.parse(args.sleep_window),
                    arduino_uart,
                    # wiring_config,
                    args.pump_amounts[pump_number],
                    args.pump_rates[pump_number],
                    db_connection,
                    datetime.timedelta(hours=float(args.pump_interval[pump_number])))
                    )

        # climate_manager = make_climate_manager(
        #     args.desired_ambient_temperature,
        #     arduino_uart,
        #     db_connection)
        pollers = make_sensor_pollers(
            datetime.timedelta(minutes=args.poll_interval),
            datetime.timedelta(minutes=args.photo_interval),
            record_queue,
            local_soil_temperature_sensor,
            local_soil_moisture_sensor,
            local_ambient_temperature_sensor,
            local_ambient_humidity_sensor,
            local_light_sensor,
            camera_manager,
            pump_managers,
            n_pumps,
            local_actuator_observer)
        try:
            for current_poller in pollers:
                current_poller.start_polling_async()
            while True:
                if not record_processor.try_process_next_record():
                    time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info('Caught keyboard interrupt. Exiting.')
        finally:
            for current_poller in pollers:
                current_poller.close()
            arduino_uart.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='GreenPiThumb',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-n',
        '--n_pumps',
        type=int,
        choices=(1, 2, 3, 4, 5),
        help='Specifies the amount of pumps to control.',
        default=2)
    parser.add_argument(
        '-a',
        '--pump_amounts',
        type=int,
        nargs='+',
        help='Volume of water (in mL) to pump each time the water pump is run for every pump (divided by spaces)',
        required=True)
    parser.add_argument(
        '-r',
        '--pump_rates',
        type=int,
        nargs='+',
        help='Volume of water (in mL) per minute for every pump (divided by spaces)',
        required=True)
    parser.add_argument(
        '-w',
        '--pump_interval',
        type=float,
        nargs='+',
        help='Max number of hours between plant waterings',
        required=True)
    parser.add_argument(
        '-p',
        '--poll_interval',
        type=float,
        help='Number of minutes between each sensor poll',
        default=15)
    parser.add_argument(
        '-t',
        '--photo_interval',
        type=float,
        help='Number of minutes between each camera photo',
        default=(4 * 60))
    parser.add_argument(
        '-c',
        '--config_file',
        help='Wiring config file',
        default='greenpithumb/wiring_config.ini')
    parser.add_argument(
        '-s',
        '--sleep_window',
        action='append',
        type=str,
        default=[],
        help=('Time window during which GreenPiThumb will not activate its '
              'pump. Window should be in the form of a time range in 24-hour '
              'format, such as "03:15-03:45 (in the local time zone)"'))
    parser.add_argument(
        '-i',
        '--image_path',
        type=str,
        help='Path to folder where images will be stored',
        default='images/')
    parser.add_argument(
        '-d',
        '--db_file',
        help='Location to store GreenPiThumb database file',
        default='greenpithumb/greenpithumb.db')
    parser.add_argument(
        '-m',
        '--moisture_threshold',
        type=int,
        nargs='+',
        help=('Moisture threshold to start pump. The pump will turn on if the '
              'moisture level drops below this level'),
        default=[0, 0, 0, 0, 0])
    parser.add_argument(
        '--camera_rotation',
        type=int,
        choices=(0, 90, 180, 270),
        help='Specifies the amount to rotate the camera\'s image.')
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='Use verbose logging')
    main(parser.parse_args())
