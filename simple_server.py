"""Simple HTTP2 server."""
# TODO: Refactor into modules
import asyncio
from collections import namedtuple

from h2.connection import H2Connection
from h2.events import RequestReceived
import uvloop

ADDR_INFO = {'host': '127.0.0.1',
             'port': 8080}

HTTP1_UPGRADE_MESSAGE = (b'HTTP/1.1 101 Switching Protocols\r\n'
                         b'Connection: Upgrade\r\n'
                         b'Upgrade: h2c\r\n'
                         b'\r\n')

# TODO: Execute callback from parsing headers
Route = namedtuple('Route', ['path', 'method', 'callback'])


def parse_http1_headers(body):
    """Parse a given HTTP/1.1 request into a header dictionary.
        Achieves near-parity with HTTP/2 headers.

    Args:
        body (bytes): Client request to parse.

    Returns:
        dict, request headers.
    """
    body = body.decode('utf-8')
    request_headers = {}

    lines = body.split('\r\n')

    request_line = lines[0].split()

    split_headers = [[':method', request_line[0]],
                     [':path', request_line[1]]]

    for header in lines[1:-2]:
        removed_delimeter = header.split(':')

        key, value = removed_delimeter[0], ':'.join(removed_delimeter[1:])

        if key.lower() == 'host':
            split_headers.append([':authority', value.strip()])
        else:
            split_headers.append([key.lower(), value.strip()])

    for key, value in split_headers:
        request_headers[key] = value

    return request_headers


class H2Protocol(asyncio.Protocol):
    """Simple Protocol wrapper around H2Connection.

    Almost completely copied from hyper-h2 example.

    NOT THREAD SAFE."""
    def __init__(self):
        self.conn = H2Connection(client_side=False)
        self.transport = None
        self.req_headers = {}
        self.routes = []

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport

    def _upgrade_dance(self):
        if self.req_headers.get('upgrade') == 'h2c':
            self.transport.write(HTTP1_UPGRADE_MESSAGE)
            self.conn.initiate_upgrade_connection(self.req_headers['http2-settings'])
            self.transport.write(self.conn.data_to_send())
        else:
            self.conn.close_connection()

    def _initialise_connection(self, data):
        self.conn.initiate_connection()
        self.transport.write(self.conn.data_to_send())

        # Get request headers
        events = self.conn.receive_data(data)

        for event in events:
            if isinstance(event, RequestReceived):
                for key, value in event.headers:
                    self.req_headers[key] = value

    def data_received(self, data: bytes):
        if b' HTTP/1.1\r\n' in data:
            self.req_headers = parse_http1_headers(data)
            self._upgrade_dance()

        elif data.startswith(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'):
            self._initialise_connection(data)

        self.transport.write(self.conn.data_to_send())

    def connection_lost(self, exc):
        self.conn.close_connection()

        if exc:
            raise exc

        print('Connection has been closed.')

def set_up_loop():
    """Set loop and loop policy."""

    # Use uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()

    return loop


def set_up_server():
    """Set up transport with h2."""
    loop = set_up_loop()

    loop.run_until_complete(loop.create_server(H2Protocol, **ADDR_INFO))

    return loop

if __name__ == '__main__':
    LOOP = set_up_server()
    LOOP.run_forever()
