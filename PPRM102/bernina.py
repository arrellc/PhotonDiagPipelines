from collections import OrderedDict
from cam_server.pipeline.data_processing import functions, processor


def process_image(image, pulse_id, timestamp, x_axis, y_axis, parameters, bsdata):
    r = processor.process_image(image, pulse_id, timestamp, x_axis, y_axis, parameters, bsdata)
    ret = OrderedDict()
    channels = ["intensity","x_center_of_mass","x_fwhm","x_rms","x_fit_amplitude", "x_fit_mean","x_fit_offset","x_fit_standard_deviation","x_profile"]
    prefix = parameters["camera_name"]
    for c in channels:
        ret[prefix+":"+c] = r[c]
    return ret
