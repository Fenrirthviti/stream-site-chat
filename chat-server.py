import asyncio
import websockets
import json
import ssl
import pathlib
import bleach
from bleach.linkifier import Linker

# todo: Prevent users from joining the same channel more than X times
# todo: Add list of users somewhere on the page
# todo: Prevent sending messages that are empty
# todo: Allow chat to be popped out

# config params
channel_list = {}  # written automatically in the format of {channel: {user: websocket(s)}}
debug = True
session_limit = 3
log_file = '' # path to log files location


# bleach.linkify callback to add _blank target
def target_blank(attrs, new=False):
    attrs[(None, u'target')] = u'_blank'
    return attrs

def log(message):
    file = open(log_file + 'server.log', 'a')
    file.write(message)
    file.close()

@asyncio.coroutine
def client_handler(websocket, path):
    # user sends their identity on connect (rachni.js#L131)
    connect_data = yield from websocket.recv()
    connect_message = json.loads(connect_data)

    if debug:
        print('New client: ', websocket, ' (', connect_message["user"], ')')
    log('New client: ' + str(websocket) + '(' + connect_message["user"] + ')\n')

    if debug:
        print('connect_message: ', connect_message)

    welcome_message = {
        "message": "Welcome to " + connect_message["channel_name"] + ".",
        "timestamp": connect_message["timestamp"],
        "user": "System",
        "channel": connect_message["channel"],
        "channel_name": connect_message["channel_name"],
        "type": "SYSTEM"
    }

    if connect_message["channel"] in channel_list:
        if connect_message["user"] in channel_list[connect_message["channel"]]:
            channel_list[connect_message["channel"]][connect_message['user']].append(websocket)
        else:
            channel_list[connect_message["channel"]][connect_message['user']] = []
            channel_list[connect_message["channel"]][connect_message['user']].append(websocket)

    else:
        channel_list[connect_message["channel"]] = {}
        channel_list[connect_message["channel"]][connect_message['user']] = []
        channel_list[connect_message["channel"]][connect_message['user']].append(websocket)

    # check to see if maximum session limit has been reached
    if len(channel_list[connect_message["channel"]][connect_message["user"]]) > session_limit:
        if debug:
            print('Max connection limit reached!')
        maxlimit_message = {
            "message": "Maximum connection limit reached!",
            "timestamp": connect_message["timestamp"],
            "user": "System",
            "channel": connect_message["channel"],
            "channel_name": connect_message["channel_name"],
            "type": "SYSTEM"
        }
        yield from websocket.send(json.dumps(maxlimit_message))
        channel_list[connect_message["channel"]][connect_message["user"]].remove(websocket)
        websocket.close(code=1000, reason='Connection limit reached!')
        return

    else:
        user_count = len(channel_list[connect_message["channel"]]) - 1
        join_message = {
            "message": "There are " + str(user_count) + " other users connected.",
            "timestamp": connect_message["timestamp"],
            "user": "System",
            "channel": connect_message["channel"],
            "channel_name": connect_message["channel_name"],
            "type": "SYSTEM"
        }

        if debug:
            print('channel_list: ', channel_list)

        yield from websocket.send(json.dumps(welcome_message))
        yield from websocket.send(json.dumps(join_message))

        for user in channel_list[connect_message["channel"]]:
            if debug:
                print('user (connect_message): ', user)
            for socket in channel_list[connect_message["channel"]][user]:
                yield from socket.send(json.dumps(connect_message))

        # wait for messages
        try:
            while True:
                message_data = yield from websocket.recv()
                message_json = json.loads(message_data)

                # set up callback for _blank target
                linker = Linker(callbacks=[target_blank])

                # sanitize our input, then convert links to actual links
                message_json['message'] = bleach.clean(message_json['message'])
                message_json['message'] = linker.linkify(message_json['message'])

                if debug:
                    print('message: ', message_json)

                # send message only to users in the same channel
                for user in channel_list[connect_message["channel"]]:
                    if debug:
                        print('user (message): ', user)
                    for socket in channel_list[connect_message["channel"]][user]:
                        yield from socket.send(json.dumps(message_json))

        # probably a better way to handle disconnections, but this works
        except websockets.exceptions.ConnectionClosed:
            part_message = {
                "message": channel_list[connect_message["channel"]][websocket] + " has left.",
                "timestamp": connect_message["timestamp"],
                "user": "System",
                "channel": connect_message["channel"],
                "channel_name": connect_message["channel_name"],
                "type": "SYSTEM"
            }
            channel_list[connect_message["channel"]][connect_message["user"]].remove(websocket)
            if debug:
                print('Client closed connection', websocket)
            log('Client closed connection: ' + str(websocket) + '\n')
            for user in channel_list[connect_message["channel"]]:
                if debug:
                    print('user (disconnect): ', user)
                for socket in channel_list[connect_message["channel"]][user]:
                    yield from socket.send(json.dumps(part_message))


if __name__ == "__main__":
    LISTEN_ADDRESS = ('0.0.0.0', 9090,)

    # open cert file if using wss
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(pathlib.Path(__file__).with_name('certfile.pem'))

    # for ssl
    start_server = websockets.serve(client_handler, *LISTEN_ADDRESS, ssl=ssl_context)

    # non-ssl
    #start_server = websockets.serve(client_handler, *LISTEN_ADDRESS)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
