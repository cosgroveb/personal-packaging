#!/usr/bin/env python3
import base64
import hashlib
import http.client
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

def receive(sock, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('WebSocket deadline exceeded')
    sock.settimeout(remaining)
    data = sock.recv(4096)
    if not data:
        raise EOFError('WebSocket closed before reload')
    return data


with tempfile.TemporaryDirectory() as root:
    path = Path(root) / 'index.html'
    initial = b'<html><body>' + b'x' * 3_200_000 + b'</body></html>'
    updated = initial.replace(b'xxx', b'yyy', 1)
    path.write_bytes(initial)
    server = subprocess.Popen(['live-serve', root, '--port', '5500', '--strict-port', '--poll'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                conn = http.client.HTTPConnection('127.0.0.1', 5500, timeout=2)
                conn.request('GET', '/index.html')
                response = conn.getresponse()
                data = response.read()
                assert response.status == 200 and data.startswith(initial[:-14]) and data.endswith(initial[-14:]) and b'/__live/ws' in data
                break
            except (OSError, http.client.HTTPException):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.2)
        ws = socket.create_connection(('127.0.0.1', 5500), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        ws.sendall((f'GET /__live/ws HTTP/1.1\r\nHost: localhost:5500\r\nOrigin: http://localhost:5500\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        deadline = time.monotonic() + 15
        buf = b''
        while b'\r\n\r\n' not in buf:
            buf += receive(ws, deadline)
        headers, buf = buf.split(b'\r\n\r\n', 1)
        assert b' 101 ' in headers.split(b'\r\n')[0], headers
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        assert expected.lower() in headers.lower()
        def frame():
            global buf
            while len(buf) < 2:
                buf += receive(ws, deadline)
            length = buf[1] & 127
            assert length < 126 and not buf[1] & 128
            while len(buf) < 2 + length:
                buf += receive(ws, deadline)
            payload, buf = buf[2:2+length], buf[2+length:]
            return payload
        assert frame().startswith(b'id:')
        path.write_bytes(updated)
        assert frame() == b'reload'
        conn = http.client.HTTPConnection('127.0.0.1', 5500, timeout=5)
        conn.request('GET', '/index.html')
        response = conn.getresponse()
        data = response.read()
        assert response.status == 200 and data.startswith(updated[:-14]) and data.endswith(updated[-14:]) and b'/__live/ws' in data
        ws.close()
        print('large HTML, WebSocket reload, and updated response passed')
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
