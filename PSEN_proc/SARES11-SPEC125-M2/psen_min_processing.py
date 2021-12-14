import json
from collections import deque
from logging import getLogger

_logger = getLogger(__name__)

background = deque(maxlen=4)

DEFAULT_ROI_SIGNAL = None
DEFAULT_ROI_BACKGROUND = None


def get_roi_x_profile(image, roi):
    offset_x, size_x, offset_y, size_y = roi
    roi_image = image[offset_y:offset_y + size_y, offset_x:offset_x + size_x]

    return roi_image.sum(0)

#_logger.warning("----- START ---- ")
#pid = None
#sent=None
def process_image(image, pulse_id, timestamp, x_axis, y_axis, parameters, image_background_array=None):
    #global pid, sent
    #if pid is not None:
    #      if pid != sent:
    #         _logger.warning("ERROR sending %s PID: %d" % (parameters["camera_name"], pid,))     
    #      if (pid+1) != pulse_id: 
    #         _logger.warning("ERROR %s PID: waiting %d - received %d" % (parameters["camera_name"], pid+1,pulse_id))
    #pid = pulse_id
 
    processed_data = dict()

    image_property_name = parameters["camera_name"]
    roi_signal = parameters.get("roi_signal", DEFAULT_ROI_SIGNAL)
    roi_background = parameters.get("roi_background", DEFAULT_ROI_BACKGROUND)

    processed_data[image_property_name + ".processing_parameters"] = json.dumps({"roi_signal": roi_signal,
                                                                                 "roi_background": roi_background})

    if roi_signal:
        signal_profile = get_roi_x_profile(image, roi_signal)
        processed_data[image_property_name + ".roi_signal_x_profile"] = signal_profile

    if roi_background:
        processed_data[image_property_name + ".roi_background_x_profile"] = get_roi_x_profile(image, roi_background)
    #sent = pid
    return processed_data
