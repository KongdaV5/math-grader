import argparse
import logging
import os
from pathlib import Path
import platform

from local_service.http_server import create_server
from local_service.service import MathGraderService
from local_service.worker import JobWorker


def default_data_dir():
    if os.environ.get("MATH_GRADER_DATA_DIR"):
        return Path(os.environ["MATH_GRADER_DATA_DIR"])
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Math Grader"
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Math Grader"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "math-grader"


def main():
    parser = argparse.ArgumentParser(description="Run the local Math Grader service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--capture-port", type=int, default=8766)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    recognition_config = os.environ.get("MATH_GRADER_RECOGNITION_CONFIG")
    parser.add_argument(
        "--recognition-config",
        type=Path,
        default=Path(recognition_config) if recognition_config else None,
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    data_dir = args.data_dir.expanduser().resolve()
    service = MathGraderService(
        database_path=data_dir / "math-grader.sqlite3",
        data_dir=data_dir,
        recognition_config=args.recognition_config,
    )
    worker = JobWorker(service)
    from local_service.capture_bridge import CaptureBridge

    capture_bridge = CaptureBridge(service, port=args.capture_port)
    server = create_server(service, args.host, args.port, capture_bridge=capture_bridge)
    worker.start()
    logging.getLogger(__name__).info("Local service listening on http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        capture_bridge.close()
        worker.stop()


if __name__ == "__main__":
    main()
