from cam_server import PipelineClient
pc = PipelineClient("http://sf-daqsync-01:8889")

pipeline_name = "SATOP31-PMOS132-2D_pmos"
print(pc.get_pipeline_config(pipeline_name))

