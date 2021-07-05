from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SARFE10-PSSS059_psss"
print(pc.get_pipeline_config(pipeline_name))

