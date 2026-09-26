import logging
import threading


logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(self, service, poll_interval=0.2):
        self.service = service
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="math-grader-worker", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self, timeout=5):
        self._stop.set()
        self._thread.join(timeout=timeout)

    def _run(self):
        while not self._stop.is_set():
            try:
                worked = self.service.process_next_job()
            except Exception:
                logger.exception("Job worker could not claim or complete a job")
                worked = False
            if not worked:
                self._stop.wait(self.poll_interval)
