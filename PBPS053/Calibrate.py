from bsread import source
import json
import os

PBPS = "SARFE10-PBPS053:INTENSITY"
PBPG = "SARFE10-PBPG050:PHOTON-ENERGY-PER-PULSE-AVG"
configFile = "SARFE10-PBPS053_proc.json"

PBPS_data = []
PBPG_data = []
num_shots = 100


with source(channels=[PBPS, PBPG]) as stream:
    for i in range(num_shots):
        message = stream.receive()
        PBPS_data.append(message.data.data[PBPS].value)
        PBPG_data.append(message.data.data[PBPG].value)

calib = (sum(PBPG_data)/len(PBPG_data))/(sum(PBPS_data)/len(PBPS_data))
print(calib)


with open(configFile, 'r+') as f:
    data = json.load(f)
    data["uJ_calib"] = calib
    f.seek(0)
    f.truncate()

    json.dump(data, f, indent=4)


os.system('python update.py')
