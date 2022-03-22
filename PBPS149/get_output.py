from bsread import source, SUB, PULL, PUSH, PUB
from cam_server.utils import get_host_port_from_stream_address

port=9004
host = "sf-daqsync-03.psi.ch"
mode = SUB
with source(host=host, port=port, mode=SUB) as stream:
    data = stream.receive()
    print(data.data.data.keys())
    #print(data.data.data.values())

