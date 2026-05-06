import json
import socket
import struct
import uuid
import sys

PRINTER_IP = "10.120.8.38"
PRINTER_PORT = 35

request = {
    "Id": f"{{{uuid.uuid4()}}}",
    "Method": "PROTOCOL_METHOD_GET_INFORMATION",
    "Version": 1,
}

json_payload = json.dumps(request, indent=4) + "\n"
json_bytes = json_payload.encode("utf-8")

payload = (
    struct.pack("<I", len(json_bytes))
    + json_bytes
    + b"\x00" * 8
)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)

sock.connect((PRINTER_IP, PRINTER_PORT))
sock.sendall(payload)

response = b""

try:
    while True:
        chunk = sock.recv(4096)

        if not chunk:
            break

        response += chunk

except socket.timeout:
    pass

sock.close()

if len(response) < 4:
    sys.exit(1)

length = struct.unpack("<I", response[:4])[0]
body = response[4 : 4 + length]

decoded = body.decode("utf-8", errors="ignore")

start = decoded.find("{")
end = decoded.rfind("}")

if start == -1 or end == -1:
    sys.exit(1)

print(decoded[start : end + 1])