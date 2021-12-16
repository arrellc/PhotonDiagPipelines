import time
from collections import deque
from logging import getLogger
from threading import Thread

from cam_server.pipeline.data_processing import functions
from cam_server.utils import create_thread_pvs, epics_lock


import json

import numpy as np
import scipy.signal
import scipy.optimize
import numba
from lmfit.models import GaussianModel

model = GaussianModel(prefix="p1_") + GaussianModel(prefix="p2_") + GaussianModel(prefix="p3_")

model.set_param_hint("p1_center", value=0, vary=False)
model.set_param_hint("p2_center", value=0, vary=False)
model.set_param_hint("p3_center", value=0, vary=False)
params = model.make_params()

numba.set_num_threads(4)

_logger = getLogger(__name__)

channel_names = None
output_pv, center_pv, fwhm_pv, ymin_pv, ymax_pv, axis_pv = None, None, None, None, None, None
roi = [0, 0]
initialized = False
sent_pid = -1
nrows = 1
axis = None
avg_spectrum, avg_center, avg_fwhm = None, None, None
peak_width, spectral_width, bkg_width = None, None, None

@numba.njit(parallel=False)
def get_spectrum(image, background):
    y = image.shape[0]
    x = image.shape[1]

    profile = np.zeros(x, dtype=np.float64)

    for i in numba.prange(y):
        for j in range(x):
            profile[j] += image[i, j] - background[i, j]
    return profile


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
        x_pv.put(axis)
        y_pv.put(avg_spectrum)
        minimum, maximum = avg_spectrum.min(), avg_spectrum.max()
        amplitude = maximum - minimum
        skip = True
        if amplitude > nrows * 1.5:
            skip = False
        # gaussian fitting
        offset, amplitude, center, sigma = functions.gauss_fit_psss(avg_spectrum[::2], axis[::2],
            offset=minimum, amplitude=amplitude, skip=skip, maxfev=20)
        avg_center = np.float64(center)
        avg_fwhm = 2.355 * sigma
        m_pv.put(avg_center)
        w_pv.put(np.float64(avg_fwhm))


def update_autocorr(x_pvname, y_pvname):
    global peak_width, spectral_width, bkg_width
    x_pv, y_pv = create_thread_pvs([x_pvname, y_pvname])
    x_pv.wait_for_connection()
    y_pv.wait_for_connection()
    if not (x_pv.connected and y_pv.connected):
        raise (f"Cannot connect to PVs.")

    while True:
        time.sleep(1)
        if len(autocorr_buffer) != autocorr_buffer.maxlen:
            continue

        _buffer = np.array(autocorr_buffer)
        avg_autocorr = np.mean(_buffer, axis=0)
        avg_autocorr /= np.max(avg_autocorr)
        lags = axis - axis[int(axis.size / 2)]
        x_pv.put(lags)
        y_pv.put(avg_autocorr)

        result = model.fit(avg_autocorr, params, x=lags)
        peak_width = result.values['p1_sigma']
        spectral_width = result.values['p2_sigma']
        bkg_width = result.values['p3_sigma']


def initialize(params):
    global ymin_pv, ymax_pv, axis_pv, output_pv, center_pv, fwhm_pv
    global channel_names, spectra_buffer, autocorr_buffer
    epics_pv_name_prefix = params["camera_name"]
    output_pv_name = epics_pv_name_prefix + ":SPECTRUM_Y"
    center_pv_name = epics_pv_name_prefix + ":SPECTRUM_CENTER"
    fwhm_pv_name = epics_pv_name_prefix + ":SPECTRUM_FWHM"
    ymin_pv_name = epics_pv_name_prefix + ":SPC_ROI_YMIN"
    ymax_pv_name = epics_pv_name_prefix + ":SPC_ROI_YMAX"
    axis_pv_name = epics_pv_name_prefix + ":SPECTRUM_X"
    channel_names = [output_pv_name, center_pv_name, fwhm_pv_name, ymin_pv_name, ymax_pv_name, axis_pv_name]

    spectra_buffer = deque(maxlen=params["queue_length"])
    thread = Thread(target=update_avg_spectrum, args=(params["avg_spectrum_x_pvname"], params["avg_spectrum_y_pvname"], params["avg_spectrum_m_pvname"], params["avg_spectrum_w_pvname"]))
    thread.start()

    autocorr_buffer = deque(maxlen=params["queue_length"])
    thread = Thread(target=update_autocorr, args=(params["avg_autocorr_x_pvname"], params["avg_autocorr_y_pvname"]))
    thread.start()


def process_image(image, pulse_id, timestamp, x_axis, y_axis, parameters, bsdata=None, background=None):
    global roi, initialized, sent_pid, nrows, axis
    global channel_names

    if not initialized:
        initialize(parameters)
        initialized = True
    [output_pv, center_pv, fwhm_pv, ymin_pv, ymax_pv, axis_pv] = create_thread_pvs(channel_names)
    processed_data = dict()
    epics_pv_name_prefix = parameters["camera_name"]

    if ymin_pv and ymin_pv.connected:
        roi[0] = ymin_pv.value
    if ymax_pv and ymax_pv.connected:
        roi[1] = ymax_pv.value
    if axis_pv and axis_pv.connected:
        axis = axis_pv.value
    else:
        axis = None

    if axis is None:
        _logger.warning("Energy axis not connected");
        return None

    if len(axis) < image.shape[1]:
        _logger.warning("Energy axis length %d < image width %d", len(axis), image.shape[1])
        return None

    # match the energy axis to image width
    axis = axis[:image.shape[1]]

    processing_image = image.astype(np.float32) - np.float32(parameters["pixel_bkg"])
    nrows, ncols = processing_image.shape

    # validate background data if passive mode (background subtraction handled here)
    background_image = parameters.pop('background_data', None)
    if isinstance(background_image, np.ndarray):
        background_image = background_image.astype(np.float32)
        if background_image.shape != processing_image.shape:
            _logger.info("Invalid background shape: %s instead of %s" % (
            str(background_image.shape), str(processing_image.shape)))
            background_image = None
    else:
        background_image = None

    processed_data[epics_pv_name_prefix + ":processing_parameters"] = json.dumps(
        {"roi": roi, "background": None if (background_image is None) else parameters.get('image_background')})

    # crop the image in y direction
    ymin, ymax = int(roi[0]), int(roi[1])
    if nrows >= ymax > ymin >= 0:
        if (nrows != ymax) or (ymin != 0):
            processing_image = processing_image[ymin: ymax, :]
            if background_image is not None:
                background_image = background_image[ymin:ymax, :]

    # remove the background and collapse in y direction to get the spectrum
    if background_image is not None:
        spectrum = get_spectrum(processing_image, background_image)
    else:
        spectrum = np.sum(processing_image, axis=0)

    spectra_buffer.append(spectrum)

    # smooth the spectrum with savgol filter with 51 window size and 3rd order polynomial
    smoothed_spectrum = scipy.signal.savgol_filter(spectrum, 51, 3)

    # check wether spectrum has only noise. the average counts per pixel at the peak
    # should be larger than 1.5 to be considered as having real signals.
    minimum, maximum = smoothed_spectrum.min(), smoothed_spectrum.max()
    amplitude = maximum - minimum
    skip = True
    if amplitude > nrows * 1.5:
        skip = False
    # gaussian fitting
    offset, amplitude, center, sigma = functions.gauss_fit_psss(smoothed_spectrum[::2], axis[::2],
        offset=minimum, amplitude=amplitude, skip=skip, maxfev=20)

    smoothed_spectrum_normed = smoothed_spectrum / np.sum(smoothed_spectrum)
    spectrum_com = np.sum(axis * smoothed_spectrum_normed)
    spectrum_std = np.sqrt(np.sum((axis - spectrum_com) ** 2 * smoothed_spectrum_normed))

    auto_corr = np.correlate(spectrum, spectrum, mode='same')
    autocorr_buffer.append(auto_corr)

    # outputs
    processed_data[epics_pv_name_prefix + ":SPECTRUM_Y"] = spectrum
    processed_data[epics_pv_name_prefix + ":SPECTRUM_X"] = axis
    processed_data[epics_pv_name_prefix + ":SPECTRUM_CENTER"] = np.float64(center)
    processed_data[epics_pv_name_prefix + ":SPECTRUM_FWHM"] = np.float64(2.355 * sigma)
    processed_data[epics_pv_name_prefix + ":SPECTRUM_COM"] = spectrum_com
    processed_data[epics_pv_name_prefix + ":SPECTRUM_STD"] = spectrum_std

    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_Y"] = avg_spectrum
    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_CENTER"] = avg_center
    processed_data[epics_pv_name_prefix + ":SPECTRUM_AVG_FWHM"] = avg_fwhm

    processed_data[epics_pv_name_prefix + ":PEAK_WIDTH"] = peak_width
    processed_data[epics_pv_name_prefix + ":SPECTRAL_WIDTH"] = spectral_width
    processed_data[epics_pv_name_prefix + ":BKG_WIDTH"] = bkg_width

    if epics_lock.acquire(False):
        try:
            if pulse_id > sent_pid:
                sent_pid = pulse_id
                if output_pv and output_pv.connected:
                    output_pv.put(processed_data[epics_pv_name_prefix + ":SPECTRUM_Y"])
                    #_logger.debug("caput on %s for pulse_id %s", output_pv, pulse_id)

                if center_pv and center_pv.connected:
                    center_pv.put(processed_data[epics_pv_name_prefix + ":SPECTRUM_CENTER"])

                if fwhm_pv and fwhm_pv.connected:
                    fwhm_pv.put(processed_data[epics_pv_name_prefix + ":SPECTRUM_FWHM"])
        finally:
            epics_lock.release()

    return processed_data
