import json
from collections import deque
from logging import getLogger
import numpy as np

_logger = getLogger(__name__)

background = deque(maxlen=4)

DEFAULT_ROI_SIGNAL = None
DEFAULT_ROI_BACKGROUND = None


def get_roi_x_profile(image, roi, pixel_bkg):
    offset_x, size_x, offset_y, size_y = roi
    roi_image = image[offset_y : offset_y + size_y, offset_x : offset_x + size_x].astype(np.float64)
    roi_image -= pixel_bkg

    return roi_image.sum(0)


def process_image(
    image, pulse_id, timestamp, x_axis, y_axis, parameters, image_background_array=None
):

    processed_data = dict()

    image_property_name = parameters["camera_name"]
    pixel_bkg = parameters["pixel_bkg"]
    roi_signal = parameters.get("roi_signal", DEFAULT_ROI_SIGNAL)
    roi_background = parameters.get("roi_background", DEFAULT_ROI_BACKGROUND)

    processed_data[image_property_name + ".processing_parameters"] = json.dumps(
        {"roi_signal": roi_signal, "roi_background": roi_background}
    )

    if roi_signal:
        signal_profile = get_roi_x_profile(image, roi_signal, pixel_bkg)
        processed_data[image_property_name + ".roi_signal_x_profile"] = signal_profile

    if roi_background:
        processed_data[image_property_name + ".roi_background_x_profile"] = get_roi_x_profile(
            image, roi_background, pixel_bkg
        )
    # sent = pid
    return processed_data
