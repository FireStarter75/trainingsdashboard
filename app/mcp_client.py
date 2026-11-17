"""Minimale MCP-client (JSON-RPC over streamable HTTP) voor de twee garmin-servers."""
import json
import os
import threading

import requests

TIMEOUT = float(os.environ.get("MCP_TIMEOUT", "180"))


class MCPError(RuntimeError):
    pass


class MCPServer:
    def __init__(self, name, url, token):
        self.name = name
        self.url = url.rstrip("/")
        self.token = token
        self._id = 0
        self._lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.url and self.token)

    def _next_id(self):
        with self._lock:
            self._id += 1
            return self._id

    def _post(self, method, params):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        r = requests.post(self.url, headers=headers, json=payload, timeout=TIMEOUT)
        if r.status_code == 401:
            raise MCPError(f"{self.name}: bearer-token geweigerd (401)")
        if r.status_code == 403:
            raise MCPError(f"{self.name}: hostnaam niet toegestaan (403) - zie GARMIN_HTTP_ALLOWED_HOSTS")
        r.raise_for_status()
        return self._parse(r.text)

    @staticmethod
    def _parse(text):
        """Antwoord komt als SSE ('event: message' + 'data: {...}') of als pure JSON."""
        body = None
        for line in text.splitlines():
            if line.startswith("data: "):
                body = line[6:]
                break
        if body is None:
            body = text.strip()
        if not body:
            raise MCPError("leeg antwoord van MCP-server")
        doc = json.loads(body)
        if "error" in doc:
            raise MCPError(str(doc["error"]))
        return doc.get("result", {})

    def list_tools(self):
        return [t["name"] for t in self._post("tools/list", {}).get("tools", [])]

    def call(self, tool, arguments=None):
        """Roept een tool aan en geeft het resultaat terug: dict/list als de tool JSON
        teruggeeft, anders de ruwe tekst. Fouten van de tool worden MCPError."""
        result = self._post("tools/call", {"name": tool, "arguments": arguments or {}})
        blocks = result.get("content") or []
        text = ""
        for b in blocks:
            if b.get("type") == "text":
                text += b.get("text", "")
        if result.get("isError"):
            raise MCPError(f"{self.name}.{tool}: {text[:400]}")
        text = text.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


def from_env():
    """Bouwt de twee servers uit omgevingsvariabelen."""
    tax = MCPServer(
        "taxuspt",
        os.environ.get("MCP_TAXUSPT_URL", "http://192.168.0.20:8000/mcp"),
        os.environ.get("MCP_TAXUSPT_TOKEN", ""),
    )
    end = MCPServer(
        "endurance",
        os.environ.get("MCP_ENDURANCE_URL", "http://192.168.0.20:8001/mcp"),
        os.environ.get("MCP_ENDURANCE_TOKEN", ""),
    )
    return tax, end
