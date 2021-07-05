from cam_server import PipelineClient
from cam_server.utils import get_host_port_from_stream_address
from bsread import source, SUB

# Create a pipeline client.
client = PipelineClient()

# Define the camera name you want to read. This should be the same camera you are streaming in screen panel.
pipeline_name = "SAROP11-CVME-PBPS2_proc"
pipeline_instance_id = pipeline_name

# Get the stream for the pipelie instance.
stream_address = client.get_instance_stream(pipeline_instance_id)

# Extract the stream host and port from the stream_address.
stream_host, stream_port = get_host_port_from_stream_address(stream_address)

# Open connection to the stream. When exiting the 'with' section, the source disconnects by itself.
with source(host=stream_host, port=stream_port, mode=SUB) as input_stream:
    input_stream.connect()

    # Read one message.
    message = input_stream.receive()

    # Print out the received stream data - dictionary.
    print("Dictionary with data:\n", message.data.data)
