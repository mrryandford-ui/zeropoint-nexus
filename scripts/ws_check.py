import importlib.util
print('websockets:', importlib.util.find_spec('websockets') is not None)
print('websocket_client:', importlib.util.find_spec('websocket') is not None)
