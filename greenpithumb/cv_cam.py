import logging
import cv2

logger = logging.getLogger(__name__)


class CameraCV(object):
    """Wrapper for camera through opencv."""

    def __init__(self, camera):
        """Creates a new CameraCV wrapper.

        Args:
            camera: number of camera (usually 0).
        """
        self._cam_num = camera
        self._camera = cv2.VideoCapture(camera)

    def capture(self, path):
        """Saves an image to path."""
        self._camera.open(self._cam_num);
        check, frame = self._camera.read()
        cv2.imwrite(filename=path, img=frame)
        if (check):
            logger.info('Captured a picture.')
        else:
            logger.warning('Failed to open camera.')
        self._camera.release();
