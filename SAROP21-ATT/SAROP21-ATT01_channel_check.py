from collections import deque
from logging import getLogger
from scipy.signal import savgol_filter
import numpy as np

_logger = getLogger(__name__)

initialized = False


def initialize(params):
    global initialized, buffer_savgol, device, step_length, edge_type, refinement, dark_event, fel_on_event, use_dark, calib, use_filter, filter_window, buffer

    device = params["device"]
    step_length = params["step_length"]
    edge_type = params["edge_type"]
    refinement = params["refinement"]
    dark_event = params["dark_event"]
    fel_on_event = params["fel_on_event"]
    buffer_savgol = deque(maxlen=params["buffer_length"])
    use_dark = params["use_dark"]
    calib = params["calib"]
    filter_window = params["filter_window"]
    # use_filter = params['filter']
    buffer = deque(maxlen=params["buffer_length"])
    initialized = True


def _interpolate_row(y_known, x_known, x_interp):
    y_interp = np.interp(x_interp, x_known, y_known)
    return y_interp


def find_edge(data, step_length=50, edge_type="falling", refinement=1):
    # refine data
    data_length = data.shape[1]
    refined_data = np.apply_along_axis(
        _interpolate_row,
        axis=1,
        arr=data,
        x_known=np.arange(data_length),
        x_interp=np.arange(0, data_length - 1, refinement),
    )

    # prepare a step function and refine it
    step_waveform = np.ones(shape=(step_length,))
    if edge_type == "rising":
        step_waveform[: int(step_length / 2)] = -1
    elif edge_type == "falling":
        step_waveform[int(step_length / 2) :] = -1

    step_waveform = np.interp(
        x=np.arange(0, step_length - 1, refinement), xp=np.arange(step_length), fp=step_waveform
    )

    # find edges
    xcorr = np.apply_along_axis(np.correlate, 1, refined_data, v=step_waveform, mode="valid")
    edge_position = np.argmax(xcorr, axis=1).astype(float) * refinement
    xcorr_amplitude = np.amax(xcorr, axis=1)

    # correct edge_position for step_length
    edge_position += np.floor(step_length / 2)

    return {"edge_pos": edge_position, "xcorr": xcorr, "xcorr_ampl": xcorr_amplitude, "signal":data}


def process(data, pulse_id, timestamp, params):
    return data
    #if not initialized:
    #    initialize(params)
    #output = {}

    # Read stream inputs
    #prof_sig = data[params["prof_sig"]]
    #events = data[params["events"]]
    #output[params["prof_sig"]] = prof_sig
    #output[params["events"]] = events
    #output["prof_sig_length"] = len(prof_sig)
    #output["events_length"] = len(events)
 

    #return output
