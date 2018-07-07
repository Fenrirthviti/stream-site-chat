import asyncio
import websockets
import json
import ssl
import pathlib

channel_list = {}  # in the format of {channel: {websocket: user}}
debug = True


@asyncio.coroutine
def client_handler(websocket):
    if debug:
        print('New client', websocket)

    # user sends their identity on connect (rachni.js#L61)
    connect_data = yield from websocket.recv()
    connect_data_json = json.loads(connect_data)
    if debug:
        print('connect_data_json: ', connect_data_json)
    welcome_message = {
        "message": "Welcome to " + connect_data_json["channel"] + ", " + connect_data_json["user"],
        "timestamp": connect_data_json["timestamp"],
        "user": "System",
        "channel": connect_data_json["channel"],
        "type": "SYSTEM"
    }
    join_message = {
        "message": "There are 'fix this shit later' other users connected.",
        "timestamp": connect_data_json["timestamp"],
        "user": "System",
        "channel": connect_data_json["channel"],
        "type": "SYSTEM"
    }

    if connect_data_json["channel"] in channel_list:
        channel_list[connect_data_json["channel"]][websocket] = connect_data_json['user']

    else:
        channel_list[connect_data_json["channel"]] = {}
        channel_list[connect_data_json["channel"]][websocket] = connect_data_json['user']

    if debug:
        print('channel_list: ', channel_list)

    yield from websocket.send(json.dumps(welcome_message))
    yield from websocket.send(json.dumps(join_message))

    for user in channel_list[connect_data_json["channel"]]:
        if debug:
            print('user: ', user)
        yield from user.send(json.dumps(connect_data_json))

    # wait for messages
    try:
        while True:
            message_data = yield from websocket.recv()
            message_json = json.loads(message_data)
            if debug:
                print('message: ', message_json)

            # send message only to users in the same channel
            for user in channel_list[connect_data_json["channel"]]:
                if debug:
                    print('user (message): ', user)
                yield from user.send(json.dumps(message_json))

    # probably a better way to handle disconnections, but this works
    except websockets.exceptions.ConnectionClosed:
        part_message = {
            "message": channel_list[connect_data_json["channel"]][websocket] + " has left.",
            "timestamp": connect_data_json["timestamp"],
            "user": "System",
            "channel": connect_data_json["channel"],
            "type": "SYSTEM"
        }
        del channel_list[connect_data_json["channel"]][websocket]
        if debug:
            print('Client closed connection', websocket)
        for user in channel_list[connect_data_json["channel"]]:
            if debug:
                print('user (disconnect): ', user)
            yield from user.send(json.dumps(part_message))


if __name__ == "__main__":
    LISTEN_ADDRESS = ('0.0.0.0', 8080,)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(pathlib.Path(__file__).with_name('/etc/letsencrypt/live/rachni.com/fullchain.pem'))

    start_server = websockets.serve(client_handler, *LISTEN_ADDRESS, ssl=ssl_context)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
