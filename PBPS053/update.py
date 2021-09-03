import json

from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SARFE10-PBPS053_proc"
instance_name = pipeline_name + "1"

# update config
with open("SARFE10-PBPS053_proc.json") as config_file:
    config = json.load(config_file)

pc.save_pipeline_config(pipeline_name, config)

# update process func
filename = "../functions/pbps.py"
try:
    pc.set_function_script(instance_name, filename)
except:
    pc.upload_user_script(filename)

pc.stop_instance(instance_name)
