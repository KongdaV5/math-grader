import ipaddress
import re
import socket
import subprocess
import threading
import time

from local_service.service import ValidationError

LAN_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
VIRTUAL_INTERFACES = ("utun", "bridge", "awdl", "llw", "lo", "tap", "tun", "vmnet", "docker")


def discover_lan_ipv4_addresses():
    """Return reachable-looking IPv4 interface addresses, preferring the default route."""
    addresses = []
    try:
        result = subprocess.run(
            ["ifconfig", "-a"], capture_output=True, text=True, timeout=2, check=False
        )
        current_interface = None
        interface_is_up = False
        for line in result.stdout.splitlines():
            if line and not line[0].isspace() and ": flags=" in line:
                current_interface = line.split(":", 1)[0]
                interface_is_up = "UP" in line.split("<", 1)[-1].split(">", 1)[0].split(",")
                continue
            if not interface_is_up or current_interface in {None, "lo0"}:
                continue
            match = re.search(r"\binet\s+([0-9.]+)\b", line)
            if match:
                _append_private_address(addresses, match.group(1), current_interface)
    except (OSError, subprocess.SubprocessError):
        pass

    if not addresses:
        try:
            for record in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                _append_private_address(addresses, record[4][0], "network")
        except OSError:
            pass
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("192.0.2.1", 9))
                _append_private_address(addresses, probe.getsockname()[0], "default route")
            finally:
                probe.close()
        except OSError:
            pass

    preferred_interface = None
    try:
        route = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        match = re.search(r"\binterface:\s*(\S+)", route.stdout)
        if match:
            preferred_interface = match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    addresses.sort(
        key=lambda item: (
            item["interface"].startswith(VIRTUAL_INTERFACES),
            item["interface"] != preferred_interface,
            item["interface"] not in {"en0", "en1"},
            item["ip"],
        )
    )
    return addresses


def _append_private_address(addresses, value, interface):
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return
    if (parsed.version != 4 or parsed.is_loopback or parsed.is_link_local or
            not any(parsed in network for network in LAN_NETWORKS)):
        return
    if any(item["ip"] == str(parsed) for item in addresses):
        return
    addresses.append({"ip": str(parsed), "interface": interface})


class CaptureBridge:
    def __init__(self, service, port=8766, address_provider=discover_lan_ipv4_addresses):
        self.service = service
        self.port = port
        self.address_provider = address_provider
        self._lock = threading.RLock()
        self._server = None
        self._server_thread = None
        self._monitor_thread = None
        self._monitor_stop = None
        self._session_id = None
        self._token = None
        self._host = None
        self._port = None
        self._address_cache = []
        self._addresses_checked_at = None

    def addresses(self, refresh=False):
        with self._lock:
            if (refresh or self._addresses_checked_at is None or
                    time.monotonic() - self._addresses_checked_at >= 30):
                self._address_cache = list(self.address_provider())
                self._addresses_checked_at = time.monotonic()
            return [dict(item) for item in self._address_cache]

    def start(self, assignment_id, host):
        with self._lock:
            if self._server is not None:
                raise ValidationError("A Capture Session is already active")
            choices = self.addresses(refresh=True)
            if host not in {item["ip"] for item in choices}:
                raise ValidationError("Choose one of the available Mac network addresses")

            session = self.service.start_capture_session(assignment_id)
            server = None
            try:
                from local_service.http_server import create_capture_server

                server = create_capture_server(self.service, host, self.port)
                self._server = server
                self._server_thread = threading.Thread(
                    target=server.serve_forever,
                    name="math-grader-capture-http",
                    daemon=True,
                )
                self._session_id = session["session_id"]
                self._token = session["token"]
                self._host = host
                self._port = server.server_address[1]
                self._monitor_stop = threading.Event()
                self._server_thread.start()
                self._monitor_thread = threading.Thread(
                    target=self._watch_expiration,
                    name="math-grader-capture-session-watch",
                    daemon=True,
                )
                self._monitor_thread.start()
            except Exception:
                if server is not None:
                    server.server_close()
                self.service.end_capture_session(session["session_id"])
                self._clear_runtime_state_locked()
                raise
            return self.snapshot()

    def end(self):
        with self._lock:
            session_id = self._session_id
            if session_id is not None:
                self.service.end_capture_session(session_id)
            self._stop_listener_locked()
        return self.snapshot()

    def close(self):
        self.end()

    def snapshot(self):
        state = self.service.capture_admin_state()
        state["addresses"] = self.addresses()
        with self._lock:
            if (state.get("status") == "ACTIVE" and self._server is not None and
                    self._session_id == state.get("session", {}).get("id") and self._token):
                state["capture_url"] = "http://{}:{}/capture?t={}".format(
                    self._host, self._port, self._token
                )
                state["host"] = self._host
                state["port"] = self._port
            else:
                state["capture_url"] = None
                state["host"] = None
                state["port"] = None
        return state

    def _watch_expiration(self):
        with self._lock:
            stop_event = self._monitor_stop
            session_id = self._session_id
        if stop_event is None or session_id is None:
            return
        while not stop_event.wait(1.0):
            if not self.service.capture_session_is_active(session_id):
                with self._lock:
                    if self._session_id == session_id:
                        self._stop_listener_locked()
                return

    def _stop_listener_locked(self):
        stop_event = self._monitor_stop
        server = self._server
        server_thread = self._server_thread
        self._clear_runtime_state_locked()
        if stop_event is not None:
            stop_event.set()
        if server is not None:
            server.shutdown()
            server.server_close()
        if server_thread is not None and server_thread is not threading.current_thread():
            server_thread.join(timeout=2)

    def _clear_runtime_state_locked(self):
        self._server = None
        self._server_thread = None
        self._monitor_thread = None
        self._monitor_stop = None
        self._session_id = None
        self._token = None
        self._host = None
        self._port = None
