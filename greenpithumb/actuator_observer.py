import logging

logger = logging.getLogger(__name__)


class ActuatorObserver(object):
    """Wrapper for an actuator observer."""

    def __init__(self, state_reader):
        """Creates a new ActuatorObserver wrapper.

        Args:
            state_reader: state_reader instance that returns actuator states.
        """
        self._state_reader = state_reader

    def window_position(self):
        """Returns window position."""
        window_position = self._state_reader.window_position()
        logging.info('window_position = %d', window_position)
        return window_position

    # def pump1_state(self):
    #     """Returns pump1_state."""
    #     pump1_state = self._state_reader.pump1_state()
    #     logging.info('pump1_state = ', pump1_state)
    #     return pump1_state
