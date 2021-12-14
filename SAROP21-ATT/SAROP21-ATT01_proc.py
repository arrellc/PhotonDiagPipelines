from collections import deque
from logging import getLogger
from scipy.signal import savgol_filter
import numpy as np

_logger = getLogger(__name__)

initialized = False


def initialize(params):
    global initialized, buffer, device, step_length, edge_type, refinement, dark_event, fel_on_event, use_dark, calib, use_filter, filter_window, buffer_nosavgol

    device = params["device"]
    step_length = params["step_length"]
    edge_type = params["edge_type"]
    refinement = params["refinement"]
    dark_event = params["dark_event"]
    fel_on_event = params["fel_on_event"]
    buffer = deque(maxlen=params["buffer_length"])
    use_dark = params["use_dark"]
    calib = params["calib"]
    filter_window = params["filter_window"]
    # use_filter = params['filter']
    buffer_nosavgol = deque(maxlen=params["buffer_length"])
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
    #edge_position += np.floor(step_length / 2)

    return {"edge_pos": edge_position, "xcorr": xcorr, "xcorr_ampl": xcorr_amplitude, "signal":data}


def process(data, pulse_id, timestamp, params):
    if not initialized:
        initialize(params)
    output = {}

    # Read stream inputs
    prof_sig_nosavgol = data[params["prof_sig"]]
    prof_sig  = savgol_filter(prof_sig_nosavgol,filter_window,3)
    events = data[params["events"]]

    if events[dark_event] and use_dark:
        buffer_nosavgol.append(prof_sig_nosavgol)

    if prof_sig.ndim == 1:
        prof_sig = prof_sig[np.newaxis, :]

    if events[dark_event] and use_dark:
        buffer.append(prof_sig)
        edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}
    else:
        if events[fel_on_event] and buffer:
            prof_sig_norm = prof_sig / np.mean(buffer, axis=0)
            edge_results = find_edge(prof_sig_norm, step_length, edge_type, refinement)
        elif events[fel_on_event] and not use_dark:
            edge_results = find_edge(prof_sig, step_length, edge_type, refinement)
        else:
            edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}

    # calib edge
    edge_results["arrival_time"] = edge_results["edge_pos"] * calib

    # Set bs outputs
    for key, value in edge_results.items():
        output[f"{device}:{key}"] = value

    output[f"{device}:raw_wf_nosavgol"] = prof_sig_nosavgol
    output[f"{device}:raw_wf"] = prof_sig

    if events[dark_event]:
        output[f"{device}:dark_wf_nosavgol"] = prof_sig_nosavgol
        output[f"{device}:dark_wf"] = prof_sig
    else:
        output[f"{device}:dark_wf_nosavgol"] = np.nan
        output[f"{device}:dark_wf"] = np.nan

    if buffer_nosavgol:
        output[f"{device}:avg_dark_wf_nosavgol"] = np.mean(buffer_nosavgol, axis=0)
    else:
        output[f"{device}:avg_dark_wf_nosavgol"] = np.nan

    if buffer:
        output[f"{device}:avg_dark_wf"] = np.mean(buffer, axis=0)
    else:
        output[f"{device}:avg_dark_wf"] = np.nan

    return output
