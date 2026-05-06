import ipaddress
import json
import socket
import struct
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, List, Optional, TypedDict


PORT = 35
CONNECT_TIMEOUT = 0.35
REQUEST_TIMEOUT = 1.0
MAX_WORKERS = 64


class Printer(TypedDict):
    ip: str
    serial: str
    machineTypeId: str
    printerId: str


class PrinterInfo(TypedDict):
    DeviceAlias: str
    FactoryMACAddress: str
    MachineTypeId: str
    Serial: str


class PrinterInformationParameters(TypedDict):
    capabilities: list
    connectionInterface: str
    ipAddresses: List[str]
    printer: PrinterInfo
    printerID: str
    version: dict


class PrinterInformationResponse(TypedDict):
    Id: str
    Parameters: PrinterInformationParameters
    ReplyToMethod: str
    Success: bool
    Version: int


def send_protocol_request(
    ip: str,
    method: str,
) -> Optional[dict]:
    request = {
        "Id": f"{{{uuid.uuid4()}}}",
        "Method": method,
        "Version": 1,
    }

    json_payload = json.dumps(request) + "\n"
    json_bytes = json_payload.encode("utf-8")

    payload = (
        struct.pack("<I", len(json_bytes))
        + json_bytes
        + b"\x00" * 8
    )

    response = b""

    try:
        with socket.create_connection(
            (ip, PORT),
            timeout=REQUEST_TIMEOUT,
        ) as sock:
            sock.settimeout(REQUEST_TIMEOUT)

            sock.sendall(payload)

            while True:
                try:
                    chunk = sock.recv(4096)

                    if not chunk:
                        break

                    response += chunk

                except socket.timeout:
                    break

    except Exception:
        return None

    if len(response) < 4:
        return None

    try:
        declared_length = struct.unpack("<I", response[:4])[0]

        body = response[4 : 4 + declared_length]

        decoded = body.decode("utf-8", errors="ignore")

        start = decoded.find("{")
        end = decoded.rfind("}")

        if start == -1 or end == -1:
            return None

        return json.loads(decoded[start : end + 1])

    except Exception:
        return None


def probe_printer(ip: str) -> Optional[Printer]:
    try:
        response = send_protocol_request(
            ip=ip,
            method="PROTOCOL_METHOD_GET_INFORMATION",
        )

        if not response:
            return None

        parameters = response["Parameters"]
        printer = parameters["printer"]

        return {
            "ip": ip,
            "serial": printer["Serial"],
            "machineTypeId": printer["MachineTypeId"],
            "printerId": parameters["printerID"],
        }

    except Exception:
        return None


def iter_ips(subnets: List[str]) -> Generator[str, None, None]:
    for subnet in subnets:
        network = ipaddress.ip_network(subnet, strict=False)

        for ip in network.hosts():
            yield str(ip)


def is_port_open(ip: str) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(CONNECT_TIMEOUT)

            return sock.connect_ex((ip, PORT)) == 0

    except Exception:
        return False


def worker(ip: str) -> Optional[Printer]:
    if not is_port_open(ip):
        return None

    return probe_printer(ip)


def discover_printers(
    subnets: List[str],
) -> List[Printer]:
    printers_by_id: dict[str, Printer] = {}

    ips = list(iter_ips(subnets))

    print(f"Scanning {len(ips)} hosts")

    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(worker, ip)
            for ip in ips
        ]

        for future in as_completed(futures):
            completed += 1

            if completed % 50 == 0:
                print(f"{completed}/{len(ips)}")

            try:
                result = future.result()

                if not result:
                    continue

                printers_by_id[result["printerId"]] = result

                print(
                    f'Found {result["serial"]} '
                    f'at {result["ip"]}'
                )

            except Exception:
                pass

    return list(printers_by_id.values())


if __name__ == "__main__":
    printers = discover_printers(
        [
            "10.120.8.0/24",
            "10.120.10.0/24",
        ]
    )

    print(json.dumps(printers, indent=2))