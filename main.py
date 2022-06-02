import asyncio
import os
from functools import wraps

from ppadb.client import Client as AdbClient
from ppadb.device import Device
from quart import Quart, render_template, websocket
from tinydb import TinyDB

db = TinyDB('db.json')
app = Quart(__name__)

connected_websockets = set()

client = AdbClient(host="127.0.0.1", port=5037)

try:
    client.devices()
except RuntimeError as e:
    if e.__str__().find("Is adb running on your computer?"):
        print("ADB Server not running, starting it now!")
        command = os.system("adb start-server")
        print(command)


def collect_websocket(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global connected_websockets
        queue = asyncio.Queue()
        connected_websockets.add(queue)
        try:
            return await func(queue, *args, **kwargs)
        finally:
            connected_websockets.remove(queue)

    return wrapper


async def broadcast(message):
    for queue in connected_websockets:
        await queue.put(message)


@app.route('/')
async def index():
    return await render_template('index.html')


@app.route('/set')
async def pick():
    experiences = []
    devices = client.devices()
    if devices:
        device: Device = devices[0]
        payload = device.shell('cmd package list packages -3').strip()

        for package in payload.split('\n'):
            package = package.replace('package:', '')
            experiences.append({'package': package, 'name': package})

        experiences.sort(key=lambda el: el['name'])

    return await render_template('pick.html', experiences=experiences)


def get_exp_info(_d: Device, experience: str):
    my_info: str = _d.shell(f'dumpsys package | grep {experience} | grep Activity')
    my_info = my_info.strip().split('\n')[0]
    if not my_info:
        return ''
    return my_info.split(' ')[1]


@app.websocket('/ws')
async def ws():
    while True:
        outcome = 'nothing!'
        data = await websocket.receive()
        if data == 'devices':
            outcome = client.devices()
        elif data == 'stop':
            device: Device = client.devices()[0]
            current_app = device.shell("dumpsys activity activities | grep ResumedActivity")
            current_app = current_app.split(' ')[-2]
            current_app = current_app.split('/')[0]
            print(current_app,66)
            outcome = device.shell(f"am force-stop { current_app }")
        elif data == 'status':
            devices = client.devices()
            if not devices:
                outcome = 'no device!'
            else:
                device: Device = client.devices()[0]
                outcome = device.get_state()
        else:
            devices = client.devices()
            if not devices:
                outcome = 'no device!'
            else:
                device: Device = client.devices()[0]
                info = get_exp_info(device, data)
                print(info, 22)
                outcome = device.shell(f"am start -n {info}")
                print(111, outcome)
        await websocket.send(f"echo {outcome}")


@app.websocket('/api/v2/ws')
@collect_websocket
async def ws_v2(queue):
    while True:
        data = await queue.get()
        await websocket.send(data)


if __name__ == '__main__':
    app.run(port=8000, host="0.0.0.0")
