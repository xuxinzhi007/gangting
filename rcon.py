"""One-shot Source RCON client for Project Zomboid."""

import socket
import struct

TYPE_AUTH = 3
TYPE_AUTH_RESPONSE = 2
TYPE_EXECCOMMAND = 2
TYPE_RESPONSE_VALUE = 0
MAX_PACKET = 1024 * 1024


class RconError(Exception):
    pass


def _encode(req_id, req_type, body):
    payload = body.encode("utf-8") + b"\x00\x00"
    size = 8 + len(payload)
    return struct.pack("<iii", size, req_id, req_type) + payload


def _read_packets(sock):
    buf = b""
    packets = []
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        while len(buf) >= 4:
            size = struct.unpack_from("<i", buf, 0)[0]
            if size < 10 or size > MAX_PACKET:
                raise RconError("管理口返回了无法识别的数据")
            total = 4 + size
            if len(buf) < total:
                break
            req_id, req_type = struct.unpack_from("<ii", buf, 4)
            body = buf[12:total - 2].decode("utf-8", errors="replace")
            packets.append((req_id, req_type, body))
            buf = buf[total:]
        if packets:
            # Short responses arrive in one read. Stop once the socket is quiet.
            sock.settimeout(0.15)
    return packets


def execute(host, port, password, command, timeout=4):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, int(port)))
        sock.sendall(_encode(1, TYPE_AUTH, password))
        auth = _read_packets(sock)
        if not auth or auth[0][0] == -1:
            raise RconError("管理口密码不对")
        sock.settimeout(timeout)
        sock.sendall(_encode(2, TYPE_EXECCOMMAND, command))
        # Empty follow-up marks the end of a multi-packet reply.
        sock.sendall(_encode(3, TYPE_RESPONSE_VALUE, ""))
        parts = []
        for req_id, req_type, body in _read_packets(sock):
            if req_id == 2 and req_type == TYPE_RESPONSE_VALUE:
                parts.append(body)
        return "".join(parts).strip()
    except socket.timeout as exc:
        raise RconError("管理口没有回应") from exc
    except OSError as exc:
        raise RconError("管理口连不上") from exc
    finally:
        sock.close()
