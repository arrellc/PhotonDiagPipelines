import time
from collections import defaultdict, deque
from functools import partial
from logging import getLogger
from threading import Thread

import epics
import numpy as np
from cam_server.utils import create_thread_pvs

_logger = getLogger(__name__)

initialized = False

dif_vals = defaultdict(int)

# this is to avoid exceptions in the 'process' function upon appending to buffers if not all of
# them were created in the 'initialize' function
buffers = defaultdict(partial(deque, maxlen=1))


def initialize(params):
    global initialized

    epics.ca.clear_cache()

    for label in ("xpos_all", "ypos_all", "xpos_odd", "ypos_odd", "xpos_evn", "ypos_evn"):
        x_pvname = params[f"{label}_x_pvname"]
        y_pvname = params[f"{label}_y_pvname"]
        m_pvname = params[f"{label}_m_pvname"]
        w_pvname = params[f"{label}_w_pvname"]

        if x_pvname and y_pvname and m_pvname and w_pvname:
            buffer = deque(maxlen=params["queue_length"])
            buffers[label] = buffer

            thread = Thread(target=update_PVs, args=(label, buffer, x_pvname, y_pvname, m_pvname, w_pvname))
            thread.start()

    # diff PVs
    xpos_dif_m_pvname = params["xpos_dif_m_pvname"]
    xpos_dif_w_pvname = params["xpos_dif_w_pvname"]
    ypos_dif_m_pvname = params["ypos_dif_m_pvname"]
    ypos_dif_w_pvname = params["ypos_dif_w_pvname"]

    thread = Thread(target=update_dif_PVs, args=(xpos_dif_m_pvname, xpos_dif_w_pvname, ypos_dif_m_pvname, ypos_dif_w_pvname))
    thread.start()

    initialized = True


def update_PVs(label, buffer, x_pvname, y_pvname, m_pvname, w_pvname):
    x_pv, y_pv, m_pv, w_pv = create_thread_pvs([x_pvname, y_pvname, m_pvname, w_pvname])

    x_pv.wait_for_connection()
    y_pv.wait_for_connection()
    m_pv.wait_for_connection()
    w_pv.wait_for_connection()
    if not (x_pv.connected and y_pv.connected and m_pv.connected and w_pv.connected):
        raise (f"Cannot connect to {label} PVs.")

    x_pv.put(np.arange(buffer.maxlen))
    y_pv.put(np.zeros(buffer.maxlen))
    m_pv.put(0)
    w_pv.put(0)

    while True:
        time.sleep(3)
        if len(buffer) != buffer.maxlen:
            continue

        _buffer = np.array(buffer)
        _buffer = _buffer[~np.isnan(_buffer)]

        # histogram
        y_hist, x_hist = np.histogram(_buffer, bins=101)
        x_hist = (x_hist[1:] + x_hist[:-1]) / 2

        x_pv.put(x_hist)
        y_pv.put(y_hist)

        # stats
        mean_val = np.mean(_buffer)
        std_val = np.std(_buffer)

        m_pv.put(mean_val)
        w_pv.put(std_val)

        dif_vals[f"{label}_m"] = mean_val
        dif_vals[f"{label}_w"] = std_val


def update_dif_PVs(xpos_dif_m_pvname, xpos_dif_w_pvname, ypos_dif_m_pvname, ypos_dif_w_pvname):
    xpos_dif_m_pv, xpos_dif_w_pv, ypos_dif_m_pv, ypos_dif_w_pv = create_thread_pvs(
        [xpos_dif_m_pvname, xpos_dif_w_pvname, ypos_dif_m_pvname, ypos_dif_w_pvname]
    )

    xpos_dif_m_pv.wait_for_connection()
    xpos_dif_w_pv.wait_for_connection()
    ypos_dif_m_pv.wait_for_connection()
    ypos_dif_w_pv.wait_for_connection()
    if not (xpos_dif_m_pv.connected and xpos_dif_w_pv.connected and ypos_dif_m_pv.connected and ypos_dif_w_pv.connected):
        raise (f"Cannot connect to dif PVs.")

    while True:
        time.sleep(3)
        xpos_dif_m_pv.put(dif_vals["xpos_odd_m"] - dif_vals["xpos_evn_m"])
        xpos_dif_w_pv.put(dif_vals["xpos_odd_w"] - dif_vals["xpos_evn_w"])
        ypos_dif_m_pv.put(dif_vals["ypos_odd_m"] - dif_vals["ypos_evn_m"])
        ypos_dif_w_pv.put(dif_vals["ypos_odd_w"] - dif_vals["ypos_evn_w"])


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
        intensity = np.nan
        intensity_uJ = np.nan

    if intensity > params["threshold"]:
        xpos = ((right - left) / (right + left)) * params["horiz_calib"]
        ypos = ((up - down) / (up + down)) * params["vert_calib"]
    else:
        xpos = np.nan
        ypos = np.nan

    # Update buffers
    buffers["xpos_all"].append(xpos)
    buffers["ypos_all"].append(ypos)
    if pulse_id % 2:
        buffers["xpos_odd"].append(xpos)
        buffers["ypos_odd"].append(ypos)
    else:
        buffers["xpos_evn"].append(xpos)
        buffers["ypos_evn"].append(ypos)

    # Set bs outputs
    output = {}
    device, _ = params["up"].split(":", 1)
    output[f"{device}:INTENSITY"] = intensity
    output[f"{device}:INTENSITY_UJ"] = intensity_uJ
    output[f"{device}:XPOS"] = xpos
    output[f"{device}:YPOS"] = ypos

    return output
