"""Personal, read-only IBKR TWS/Gateway -> authenticated quote bridge.

Run ONLY on the machine that runs your TWS/IB Gateway. Defaults to the local
loopback interface. For remote Streamlit, use an operator-managed authenticated
HTTPS reverse proxy / private tunnel; never expose the TWS socket publicly.

Install IBKR's *official* Python `ibapi` distribution separately. This service
uses only contract lookup and market-data subscription; it has NO order route.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper
except ImportError as exc:
    raise SystemExit("Install the current official IBKR TWS Python API (ibapi) first") from exc


class _State:
    def __init__(self):
        self.done = threading.Event()
        self.details = []
        self.mode = None
        self.price = None
        self.timestamp = None
        self.error = None


class QuoteGateway(EWrapper, EClient):
    """Read-only native API session with request-scoped state."""

    def __init__(self, host, port, client_id):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._req_id = 60000
        self._requests = {}
        self._contracts = {}
        self.connect(host, int(port), int(client_id))
        thread = threading.Thread(target=self.run, daemon=True, name="IBKR-read-only-events")
        thread.start()
        if not self._ready.wait(timeout=10):
            self.disconnect()
            raise RuntimeError("TWS/Gateway did not complete API handshake")

    def nextValidId(self, orderId):  # Required for API handshake; no orders sent.
        self._ready.set()

    def connectionClosed(self):
        with self._lock:
            for request in self._requests.values():
                request.error = "IBKR CONNECTION LOST"
                request.done.set()

    def error(self, reqId, errorCode, errorString, *args):
        if int(errorCode) not in (200, 354, 10167, 10168, 10186, 162, 10090, 10091, 10092):
            return
        with self._lock:
            request = self._requests.get(reqId)
            if request is not None:
                request.error = "IBKR DATA SUBSCRIPTION / CONTRACT ERROR"
                request.done.set()

    def contractDetails(self, reqId, contractDetails):
        with self._lock:
            request = self._requests.get(reqId)
            if request is not None:
                request.details.append(contractDetails.contract)

    def contractDetailsEnd(self, reqId):
        with self._lock:
            request = self._requests.get(reqId)
            if request is not None:
                request.done.set()

    def marketDataType(self, reqId, marketDataType):
        with self._lock:
            request = self._requests.get(reqId)
            if request is not None:
                request.mode = int(marketDataType)
                if request.mode != 1:
                    request.error = "NOT REALTIME: DELAYED / FROZEN FEED"
                    request.done.set()
                elif request.price is not None and request.timestamp is not None:
                    request.done.set()

    def tickString(self, reqId, tickType, value):
        # Generic tick 233 / tick id 48: atomic price + *trade* timestamp.
        # Delayed Last (68/88), bid/ask, and arrival time are NEVER accepted.
        if int(tickType) != 48:
            return
        try:
            cells = str(value).split(";")
            price = float(cells[0])
            ts_ms = int(cells[2])
            if not (math.isfinite(price) and price > 0 and ts_ms > 0):
                return
        except (ValueError, TypeError, IndexError):
            return
        with self._lock:
            request = self._requests.get(reqId)
            if request is not None:
                request.price = price
                request.timestamp = ts_ms / 1000.0
                if request.mode == 1:
                    request.done.set()

    def _start_request(self):
        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            state = _State()
            self._requests[req_id] = state
        return req_id, state

    def _finish_request(self, req_id):
        with self._lock:
            self._requests.pop(req_id, None)

    def _contract(self, ticker):
        symbol = ticker[:-3]
        if ticker in self._contracts:
            return self._contracts[ticker]
        req_id, state = self._start_request()
        try:
            contract = Contract()
            contract.symbol = symbol
            contract.secType = "STK"
            contract.exchange = "TASE"
            contract.currency = "ILS"
            self.reqContractDetails(req_id, contract)
            if not state.done.wait(4) or state.error:
                return None
            valid = [c for c in state.details if c.secType == "STK" and
                     c.currency == "ILS" and c.symbol.upper() == symbol and
                     (c.exchange == "TASE" or c.primaryExchange == "TASE")]
            distinct = {int(c.conId): c for c in valid if int(c.conId) > 0}
            # Never select the first result when the IBKR contract is ambiguous.
            if len(distinct) != 1:
                return None
            chosen = next(iter(distinct.values()))
            self._contracts[ticker] = chosen
            return chosen
        finally:
            self._finish_request(req_id)

    def quote(self, ticker):
        result = {"status": "UNAVAILABLE", "symbol": ticker, "exchange": "TASE",
                  "currency": "ILS", "last_kind": "LAST_TRADE", "market_data_type": None}
        if not self.isConnected():
            result["status"] = "DISCONNECTED"
            return result
        contract = self._contract(ticker)
        if contract is None:
            result["status"] = "UNRESOLVED CONTRACT"
            return result
        req_id, state = self._start_request()
        try:
            self.reqMarketDataType(1)
            self.reqMktData(req_id, contract, "233", False, False, [])
            state.done.wait(5)
            result["market_data_type"] = state.mode
            if state.error:
                result["status"] = state.error
            elif state.mode == 1 and state.price is not None and state.timestamp is not None:
                result.update({"status": "OK", "price": state.price,
                               "timestamp": state.timestamp, "conid": int(contract.conId)})
            else:
                result["status"] = "NO TIMESTAMPED LIVE LAST TRADE"
            return result
        finally:
            try:
                self.cancelMktData(req_id)
            finally:
                self._finish_request(req_id)


def serve(gateway, token, listen, http_port):
    if len(token) < 24:
        raise ValueError("IBKR_BRIDGE_TOKEN must contain at least 24 characters")
    if listen not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("This sample bridge binds only to localhost; use an HTTPS reverse proxy")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            provided = self.headers.get("Authorization", "")
            if not secrets.compare_digest(provided, "Bearer " + token):
                self._send(401, {"status": "UNAUTHORIZED"})
                return
            parts = urlsplit(self.path)
            if parts.path != "/quote":
                self._send(404, {"status": "NOT FOUND"})
                return
            names = parse_qs(parts.query).get("symbol", [])
            ticker = names[0].upper().strip() if len(names) == 1 else ""
            if (not ticker.endswith(".TA") or not ticker[:-3] or
                    not all(c.isalnum() or c in "-_" for c in ticker[:-3])):
                self._send(400, {"status": "INVALID TASE SYMBOL"})
                return
            try:
                result = gateway.quote(ticker)
                self._send(200, result)
            except Exception:
                self._send(503, {"status": "IBKR QUOTE TEMPORARILY UNAVAILABLE"})

        def _send(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # No request URLs or bearer tokens in logs.
            pass

    server = ThreadingHTTPServer((listen, int(http_port)), Handler)
    try:
        server.serve_forever()
    finally:
        gateway.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Personal read-only IBKR TASE quote bridge")
    parser.add_argument("--tws-host", default="127.0.0.1")
    parser.add_argument("--tws-port", type=int, default=7497,
                        help="TWS paper=7497/live=7496; Gateway paper=4002/live=4001")
    parser.add_argument("--client-id", type=int, default=71)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8765)
    args = parser.parse_args()
    token = os.environ.get("IBKR_BRIDGE_TOKEN", "")
    if len(token) < 24:
        parser.error("Set a strong IBKR_BRIDGE_TOKEN environment variable first")
    print("Connecting to read-only TWS/Gateway. Keep API Read-Only enabled in TWS.")
    gateway = QuoteGateway(args.tws_host, args.tws_port, args.client_id)
    print(f"Local authenticated quote bridge listening on {args.listen}:{args.http_port}")
    serve(gateway, token, args.listen, args.http_port)


if __name__ == "__main__":
    main()
