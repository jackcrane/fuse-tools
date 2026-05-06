def format_status_details(printer: dict, status_response: dict) -> str:
    parameters = status_response["Parameters"]
    cylinder_last_print = parameters["cylinderLastPrint"]
    cylinder_tracking = parameters["cylinderTracking"]
    running_jobs = parameters["currentlyRunningJobHeights"]

    lines = [
        f'Serial: {printer["serial"]}',
        f'IP Address: {printer["ip"]}',
        f'Machine Type: {printer["machineTypeId"]}',
        f'Status: {"Printing" if parameters["isPrinting"] else "Idle"}',
        f'Accepting Jobs: {parameters["isAcceptingJobs"]}',
        f'Primed: {parameters["isPrimed"]}',
        f'Bed Temperature (C): {parameters["bedTemperature_C"]:.2f}',
        f'Powder Level: {parameters["powderLevel"]}',
        f'Material: {parameters["printerMaterial"]}',
        f'Material Credit (g): {parameters["materialCredit_g"]}',
        f'Printing Layer: {parameters["printingLayer"]}',
        (
            "Estimated Time Remaining (min): "
            f'{parameters["estimatedPrintTimeRemaining_ms"] / 60000:.1f}'
        ),
        f'Printing Job GUID: {parameters["printingJobGuid"]}',
        f'Job Revision: {parameters["printingJobRevision"]}',
        f'Cylinder Serial: {parameters["cylinderSerial"]}',
        f'Cylinder Material: {parameters["cylinderMaterialCode"]}',
        f'Cylinder Z Range (mm): {parameters["cylinderZAxisRange_mm"]}',
        f'Cylinder Last Print: {cylinder_last_print["printGuid"]}',
        (
            "Last Print Progress: "
            f'{cylinder_last_print["layersPrinted"]}/'
            f'{cylinder_last_print["totalLayers"]} layers'
        ),
        f'Last Print Updated: {cylinder_last_print["metadataUpdateTimestamp"]}',
        f'Tracking Layers: {cylinder_tracking["numberOfLayers"]}',
        (
            "Tracking Travel (mm): "
            f'{cylinder_tracking["totalTravel_mm"]:.2f}'
        ),
        f"Running Jobs: {len(running_jobs)}",
        f'Issues: {len(parameters["printerIssues"])}',
    ]

    if running_jobs:
        first_job = running_jobs[0]
        lines.extend(
            [
                f'Current Job GUID: {first_job["jobGuid"]}',
                (
                    "Core Print Height (mm): "
                    f'{first_job["heightCorePrint_mm"]}'
                ),
                (
                    "Hot Precoats Height (mm): "
                    f'{first_job["heightHotPrecoats_mm"]}'
                ),
            ]
        )

    return "\n".join(lines)
