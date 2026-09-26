import argparse
import logging
from pathlib import Path
import os
import shutil
import sys

from local_service.http_server import create_server
from local_service.service import MathGraderService
from local_service.worker import JobWorker
from local_service.runtime_paths import RuntimePaths, default_root


def default_data_dir():
    root = default_root()
    legacy = Path.home() / "Library" / "Application Support" / "Math Grader"
    if not os.environ.get("MATH_GRADER_DATA_DIR") and legacy.joinpath("math-grader.sqlite3").is_file():
        return legacy
    return root


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

    if sys.version_info[:2] < (3, 9):
        parser.error("Math Grader requires Python 3.9 or newer")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    data_dir = args.data_dir.expanduser().resolve()
    paths = RuntimePaths(data_dir).ensure()
    config_path = args.recognition_config
    if config_path is None:
        config_path = paths.config / "recognition.json"
        if not config_path.exists():
            shutil.copyfile(Path(__file__).parent / "config" / "recognition.json", config_path)
    service = MathGraderService(
        database_path=paths.database,
        data_dir=data_dir,
        recognition_config=config_path,
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
