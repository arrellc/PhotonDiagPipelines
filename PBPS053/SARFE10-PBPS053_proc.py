import time
from collections import defaultdict, deque
from functools import partial
from logging import getLogger
from threading import RLock, Thread

import epics
import numpy as np
from cam_server.utils import create_thread_pvs
from scipy.fftpack import fft

_logger = getLogger(__name__)

intensity_pv = None
initialized = False

# this is to avoid exceptions in the 'process' function upon appending to buffers if not all of
# them were created in the 'initialize' function
buffers = defaultdict(partial(deque, maxlen=1))


def initialize(params):
    global intensity_pv, device, initialized

    epics.ca.clear_cache()
    [intensity_pv] = create_thread_pvs([params["intensity_pvname"]])
    intensity_pv.wait_for_connection()
    # If raising this exception then the pipeline won't start
    if not intensity_pv.connected:
        raise ("Cannot connect to " + params["intensity_pvname"])

    for label in ("x_pos_all", "y_pos_all", "x_pos_odd", "y_pos_odd", "x_pos_even", "y_pos_even"):
        out_x_pvname = params[f"fft_{label}_X_pvname"]
        out_y_pvname = params[f"fft_{label}_Y_pvname"]

        if out_x_pvname and out_y_pvname:
            buffer = deque(maxlen=params["queue_length"])
            buffers[label] = buffer

            thread = Thread(target=calculate_fft, args=(buffer, out_x_pvname, out_y_pvname))
            thread.start()

    device, _ = params["up"].split(":", 1)

    initialized = True


# Processing the buffer every second and setting result to EPICS channel
def calculate_fft(buffer, out_x_pvname, out_y_pvname):
    _logger.info("Start buffer processing thread")
    try:
        out_x_pv, out_y_pv = create_thread_pvs([out_x_pvname, out_y_pvname])

        out_x_pv.wait_for_connection()
        out_y_pv.wait_for_connection()
        if not (out_x_pv.connected and out_y_pv.connected):
            raise ("Cannot connect to fft PVs.")

        out_x_pv.put(np.arange(buffer.maxlen))
        out_y_pv.put(np.zeros(buffer.maxlen))

        while True:
            _buffer = buffer.copy()
            if len(_buffer) == _buffer.maxlen:
                out_y_pv.put(np.abs(fft(np.array(_buffer))))

            time.sleep(10)

    except Exception as e:
        _logger.error("Error on buffer processing thread %s" % (str(e)))
    finally:
        _logger.info("Exit buffer processing thread")


def process(data, pulse_id, timestamp, params):
    # Initialize on first run
    if not initialized:
        initialize(params)

    # Read stream inputs
    up = data[params["up"]] * params["up_calib"]
    down = data[params["down"]] * params["down_calib"]
    right = data[params["right"]] * params["right_calib"]
    left = data[params["left"]] * params["left_calib"]

    # Calculations
    try:
        intensity = down + up + left + right
        intensity_uJ = intensity * params["uJ_calib"]
    except:
        intensity = float("nan")
        intensity_uJ = float("nan")

    if intensity > params["threshold"]:
        x_pos = ((right - left) / (right + left)) * params["horiz_calib"]
        y_pos = ((up - down) / (up + down)) * params["vert_calib"]
    else:
        x_pos = float("nan")
        y_pos = float("nan")

    # Update buffers
    buffers["x_pos_all"].append(x_pos)
    buffers["y_pos_all"].append(y_pos)
    if pulse_id % 2:
        buffers["x_pos_odd"].append(x_pos)
        buffers["y_pos_odd"].append(y_pos)
    else:
        buffers["x_pos_even"].append(x_pos)
        buffers["y_pos_even"].append(y_pos)

    # Update intensity EPICS channel
    intensity_pv.put(intensity)

    # Set bs outputs
    output = {}
    output[f"{device}:intensity"] = intensity
    output[f"{device}:intensity_uJ"] = intensity_uJ
    output[f"{device}:x_pos"] = x_pos
    output[f"{device}:y_pos"] = y_pos

    return output

