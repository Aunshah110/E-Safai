import urllib.request
import json


class LocationManager:
    def __init__(self, ip, port):
        self.gps_url = f"http://{ip}:{port}/gps.json"
        self._last = None

    def get_location(self):
        """Return dict {lat, lon} or None. Prefer GPS, fallback to network."""
        try:
            with urllib.request.urlopen(self.gps_url, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return self._last

        # Try GPS first
        gps = data.get("gps") or {}
        lat = gps.get("latitude")
        lon = gps.get("longitude")

        # If GPS empty, try network positioning
        if lat is None or lon is None or lat == 0 or lon == 0:
            net = data.get("network") or {}
            lat = net.get("latitude")
            lon = net.get("longitude")

        if lat is not None and lon is not None and lat != 0 and lon != 0:
            self._last = {"lat": float(lat), "lon": float(lon)}
            return self._last

        return self._last   # return last known if current fetch fails