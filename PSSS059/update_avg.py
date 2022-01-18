import json

from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SARFE10-PSSS059_psss_avg"
# instance_name = pipeline_name + "1"
instance_name = pipeline_name

# update config
with open("PSSS_avg.json") as config_file:
    config = json.load(config_file)

pc.save_pipeline_config(pipeline_name, config)

# update process func
filename = "psss_avg.py"
try:
    pc.set_function_script(instance_name, filename)
except:
    pc.upload_user_script(filename)

pc.stop_instance(instance_name)
