import json
import socket
import struct
import uuid
from typing import List, TypedDict


class RunningJobHeight(TypedDict):
    heightColdFills_mm: float
    heightCorePrint_mm: float
    heightHotPrecoats_mm: float
    heightPostPrint_mm: float
    jobBundleIndex: int
    jobGuid: str


class CylinderLastPrint(TypedDict):
    jobGuid: str
    layersPrinted: int
    metadataUpdateTimestamp: str
    printGuid: str
    printerSerial: str
    totalLayers: int


class CylinderTracking(TypedDict):
    numberOfLayers: int
    numberOfLayersSinceSealReplacement: int
    numberOfPrints: int
    totalTravelSinceSealReplacement_mm: float
    totalTravel_mm: float


class PrinterStatusParameters(TypedDict):
    bedTemperature_C: float
    currentlyRunningJobHeights: List[RunningJobHeight]
    cylinderLastPrint: CylinderLastPrint
    cylinderMaterialCode: str
    cylinderMechanicalVersion: int
    cylinderSerial: str
    cylinderTracking: CylinderTracking
    cylinderZAxisRange_mm: float
    estimatedPrintTimeRemaining_ms: float
    estimatedTotalPrintTime_ms: float
    highLevelState: int
    isAcceptingJobs: bool
    isDashboardRegistrationAllowed: bool
    isPrimed: bool
    isPrinting: bool
    materialCredit_g: float
    powderLevel: int
    primedTimeout_UnixStamp: int
    printerIssues: List[dict]
    printerMaterial: str
    printingJobGuid: str
    printingJobRevision: int
    printingLayer: int
    voltageCode: int


class PrinterStatusResponse(TypedDict):
    Id: str
    Parameters: PrinterStatusParameters
    ReplyToMethod: str
    Success: bool
    Version: int


def get_printer_status(
    printer_ip: str,
    port: int = 35,
) -> PrinterStatusResponse:
    request = {
        "Id": f"{{{uuid.uuid4()}}}",
        "Method": "PROTOCOL_METHOD_GET_STATUS",
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
    sock.settimeout(3)

    try:
        sock.connect((printer_ip, port))
        sock.sendall(payload)

        response = b""

        while True:
            try:
                chunk = sock.recv(4096)

                if not chunk:
                    break

                response += chunk

            except socket.timeout:
                break

    finally:
        sock.close()

    if len(response) < 4:
        raise ValueError("Invalid response from printer")

    declared_length = struct.unpack("<I", response[:4])[0]

    body = response[4 : 4 + declared_length]

    decoded = body.decode("utf-8", errors="ignore")

    start = decoded.find("{")
    end = decoded.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")

    return json.loads(decoded[start : end + 1])


if __name__ == "__main__":
    status = get_printer_status("10.120.8.38")

    print(status)