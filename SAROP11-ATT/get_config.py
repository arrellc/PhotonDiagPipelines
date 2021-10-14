from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SAROP21-ATT01_proc"
print(pc.get_pipeline_config(pipeline_name))

