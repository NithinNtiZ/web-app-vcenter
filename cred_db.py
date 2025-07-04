import json
with open('cred.json', 'r') as handle:
  info = json.load(handle)

vc          = info["vc"]
domain      = info["domain"]
donald      = info["donald"]
popepy      = info["popepy"]
jerry       = info["jerry"]
thanos      = info["thanos"]
mgmt        = info["mgmt"]
folder      = info["folder"]
username    = info["username"]
password    = info["password"]
res_pool_list    = info["res_pool_list"]
ds = info["ds"]
network = info["network"]
sql_database = info["sql_database"]