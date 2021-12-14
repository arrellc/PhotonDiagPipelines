from collections import deque
from logging import getLogger
from scipy.signal import savgol_filter
import numpy as np

_logger = getLogger(__name__)

initialized = False

def initialize(params):
    global initialized, buffer, device, step_length, edge_type, refinement, dark_event, fel_on_event, use_dark, calib, use_filter, filter_window

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
    use_filter = params['filter']
    initialized = True
    
def initialize_jp(params, namespace):
    #global initialized, buffer, device, step_length, edge_type, refinement, dark_event, fel_on_event, use_dark, calib, use_filter, filter_window

    namespace['device'] = params["device"]
    namespace['step_length'] = params["step_length"]
    namespace['edge_type'] = params["edge_type"]
    namespace['refinement'] = params["refinement"]
    namespace['dark_event'] = params["dark_event"]
    namespace['fel_on_event'] = params["fel_on_event"]
    namespace['buffer'] = deque(maxlen=params["buffer_length"])
    namespace['use_dark'] = params["use_dark"]
    namespace['calib'] = params["calib"]
    namespace['filter_window'] = params["filter_window"]
    namespace['use_filter'] = params['filter']
    namespace['initialized'] = True

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
    if not initialized:
        initialize(params)

    # Read stream inputs
    prof_sig = data[params["prof_sig"]]
    if use_filter:
        prof_sig  = savgol_filter(prof_sig,filter_window,3)
    events = data[params["events"]]

    if prof_sig.ndim == 1:
        prof_sig = prof_sig[np.newaxis, :]

    if events[dark_event] and use_dark:
        buffer.append(prof_sig)
        edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}
    else:
        if events[fel_on_event] and buffer:
            prof_sig = prof_sig / np.mean(buffer, axis=0)
            edge_results = find_edge(prof_sig, step_length, edge_type, refinement)
            edge_results['buffer'] = buffer
        elif events[fel_on_event] and not use_dark:
            edge_results = find_edge(prof_sig, step_length, edge_type, refinement)
            edge_results['buffer'] = "no buffer"

        else:
            edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}

    # calib edge
    edge_results["arrival_time"] = edge_results["edge_pos"] * calib

    # Set bs outputs
    output = {}
    for key, value in edge_results.items():
        output[f"{device}:{key}"] = value

    return output

def process_jp(data, pulse_id, timestamp, params, namespace):
    if not initialized:
        initialize(params)
    buffer = namespace['buffer']
    # Read stream inputs
    prof_sig = data[params["prof_sig"]]
    ## calibration of spectrometer, this can be moved to json/int function
    lambda_nm = np.linspace(446.1, 702, 2048)
    c = 3
    freq = c / lambda_nm
    interp_freq = np.linspace(c/702, c/446.1,  2048)
    ##
    
    try:
        if use_filter:
            #prof_sig = np.apply_along_axis(interpolate_row, 1, prof_sig[::-1], freq[::-1], interp_freq)[::-1]
            prof_sig  = savgol_filter(prof_sig,filter_window,3)

    except:
        edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}
        output = {}
        for key, value in edge_results.items():
            output[f"{device}:{key}"] = value
        return output

    if len(prof_sig)< filter_window:
        print('Length of signal less thank filter window')
    #if use_filter:
    #    prof_sig  = savgol_filter(prof_sig,filter_window,3)
    events = data[params["events"]]

    if prof_sig.ndim == 1:
        prof_sig = prof_sig[np.newaxis, :]
    if events[dark_event] and use_dark:
        if events[fel_on_event] and buffer:
            prof_sig = prof_sig / np.mean(buffer, axis=0)
            edge_results = find_edge(prof_sig, step_length, edge_type, refinement)
            edge_results["buffer"] = buffer
        elif events[fel_on_event] and not use_dark:
            edge_results = find_edge(prof_sig, step_length, edge_type, refinement)
            edge_results["buffer"] = "no buffer"

        else:
            edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}

    else:
        buffer.append(prof_sig)
        edge_results = {"edge_pos": np.nan, "xcorr": np.nan, "xcorr_ampl": np.nan, "signal":np.nan}
        
    # calib edge
    edge_results["arrival_time"] = edge_results["edge_pos"] * calib

    # Set bs outputs
    output = {}
    for key, value in edge_results.items():
        output[f"{device}:{key}"] = value
    namespace['buffer'] = buffer
    return output