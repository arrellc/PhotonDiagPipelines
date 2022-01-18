import time
from collections import deque
from logging import getLogger
from threading import Thread

from cam_server.pipeline.data_processing import functions
from cam_server.utils import create_thread_pvs, epics_lock

import numpy as np

_logger = getLogger(__name__)

initialized = False
nrows = 1
axis = None
avg_spectrum = None
avg_center = None
avg_fwhm = None
spectra_buffer = None


def update_avg_spectrum(x_pvname, y_pvname, m_pvname, w_pvname):
    global avg_spectrum, avg_center, avg_fwhm
    x_pv, y_pv, m_pv, w_pv = create_thread_pvs([x_pvname, y_pvname, m_pvname, w_pvname])
    x_pv.wait_for_connection()
    y_pv.wait_for_connection()
    m_pv.wait_for_connection()
    w_pv.wait_for_connection()
    if not (x_pv.connected and y_pv.connected and m_pv.connected and w_pv.connected):
        raise (f"Cannot connect to PVs.")

    while True:
        time.sleep(1)
        if len(spectra_buffer) != spectra_buffer.maxlen:
            continue

        _buffer = np.array(spectra_buffer)
        avg_spectrum = np.mean(_buffer, axis=0)
        minimum, maximum = avg_spectrum.min(), avg_spectrum.max()
        amplitude = maximum - minimum
        skip = True
        if amplitude > nrows * 1.5:
            skip = False
        # gaussian fitting
        offset, amplitude, center, sigma = functions.gauss_fit_psss(
            avg_spectrum[::2], axis[::2], offset=minimum, amplitude=amplitude, skip=skip, maxfev=20
        )
        avg_center = np.float64(center)
        avg_fwhm = 2.355 * sigma

        if epics_lock.acquire(False):
            try:
                x_pv.put(axis)
                y_pv.put(avg_spectrum)
                m_pv.put(avg_center)
                w_pv.put(np.float64(avg_fwhm))
            finally:
                epics_lock.release()


def initialize(params):
    global spectra_buffer

    spectra_buffer = deque(maxlen=params["queue_length"])
    thread = Thread(
        target=update_avg_spectrum,
        args=(
            params["avg_spectrum_x_pvname"],
            params["avg_spectrum_y_pvname"],
            params["avg_spectrum_m_pvname"],
            params["avg_spectrum_w_pvname"],
        ),
    )
    thread.start()


def process(data, pulse_id, timestamp, params):
    global initialized, nrows, axis

    if not initialized:
        initialize(params)
        initialized = True

    processed_data = dict()
    epics_pv_name_prefix = "SARFE10-PSSS059"

    axis = data[params["spectrum_x"]]
    spectrum = data[params["spectrum_y"]]

    spectra_buffer.append(spectrum)

    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_Y"] = avg_spectrum
    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_CENTER"] = avg_center
    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_FWHM"] = avg_fwhm

    return processed_data
