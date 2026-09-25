#!/usr/bin/python3 -I
"""Private host executor bootstrap. Processing endpoints remain closed until qualified.

The Unix socket is deliberately absent from every model sandbox. Peer identity
is checked before HTTP parsing. Only fixed infrastructure probes exist here;
no arbitrary command, path, environment or model prompt is accepted over RPC.
"""
import fcntl
import http.server
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import registration, command, PROBE
from jobs import Jobs, Conflict
from protocol import resolve

SOCKET = '/run/loginom-swarm/control.sock'
LOCK = '/opt/loginom-worker/state/heavy.lock'


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log arbitrary request paths, headers or provider output.

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith('/v1/jobs/'):
            try:
                return self.reply(200, self.server.jobs.get(self.path.removeprefix('/v1/jobs/')))
            except (FileNotFoundError, ValueError):
                return self.reply(404, {'error': 'unknown_operation'})
        if self.path != '/health':
            return self.reply(404, {'error': 'not_found'})
        self.reply(200, {'service': 'loginom-swarm-worker', 'schema': 1,
                         'processingEnabled': False, 'status': 'setup', 'executionProtocol': 1})

    def do_POST(self):
        if self.path in {'/v1/jobs', '/v1/jobs/cancel'}:
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 0 < size <= 4096:
                    raise ValueError('Invalid body size')
                body = json.loads(self.rfile.read(size))
                if self.path == '/v1/jobs':
                    # Resolve every request, including a retry, before inspecting receipts.
                    resolve(body)
                    record = self.server.jobs.submit(body)
                else:
                    if not isinstance(body, dict) or set(body) != {'requestKey', 'expectedVersion'}:
                        raise ValueError('Invalid cancellation fields')
                    record = self.server.jobs.cancel(body['requestKey'], body['expectedVersion'])
                return self.reply(200, record)
            except Conflict:
                return self.reply(409, {'error': 'execution_conflict'})
            except FileNotFoundError:
                return self.reply(404, {'error': 'unknown_operation'})
            except (ValueError, TypeError, KeyError, AttributeError):
                return self.reply(422, {'error': 'invalid_execution_request'})
        if self.path != '/v1/probe':
            return self.reply(409, {'error': 'processing_not_qualified'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < size <= 1024:
                raise ValueError('Invalid body size')
            body = json.loads(self.rfile.read(size))
            if set(body) != {'campaign', 'role'}:
                raise ValueError('Unsupported request fields')
            record = registration(body['campaign'], body['role'])
            with open(LOCK, 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                argv, env = command(record, ['/usr/bin/python3', '-I', '-c', PROBE])
                # Output from the fixed probe is JSON booleans only. Never forward stderr.
                result = subprocess.run(argv, env=env, capture_output=True, timeout=30)
                checks = json.loads(result.stdout)
                if not isinstance(checks, dict) or any(type(v) is not bool for v in checks.values()):
                    raise ValueError('Invalid probe result')
                return self.reply(200 if result.returncode == 0 else 422, {'checks': checks})
        except BlockingIOError:
            return self.reply(409, {'error': 'heavy_stage_busy'})
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired, TypeError):
            return self.reply(422, {'error': 'sandbox_probe_failed'})


class Server(socketserver.UnixStreamServer):
    allow_reuse_address = False
    def verify_request(self, request, _):
        request.settimeout(10)
        _, uid, _ = struct.unpack('3i', request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid in {0, os.getuid()}


def main():
    os.umask(0o077)
    # RuntimeDirectory is created and cleaned by systemd. Refuse stale sockets.
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.jobs = Jobs('/opt/loginom-worker/state/executions', LOCK, resolve)
        server.serve_forever()


if __name__ == '__main__':
    main()
