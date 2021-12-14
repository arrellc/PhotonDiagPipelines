import json

from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SARES11-SPEC125-M2_psen_db"
instance_name = pipeline_name + "1"

# update config
with open("SARES11-SPEC125-M2_psen.json") as config_file:
    config = json.load(config_file)

pc.save_pipeline_config(pipeline_name, config)

pc.stop_instance(instance_name)

