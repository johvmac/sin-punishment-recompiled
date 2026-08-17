#!/usr/bin/env python3
"""Read N64 memory out of a running ares instance over its GDB remote protocol.

WHY THIS EXISTS
---------------
The playbook's G6 (cross-compare against ares) is blocked on this machine:
system gdb has no MIPS target compiled in (`set architecture mips` ->
"Undefined item"), so it cannot decode the register set and the `target remote`
handshake fails with "Remote 'g' packet reply is too long".

But that limitation is specific to REGISTER decoding. The GDB remote serial
protocol's memory-read packet (`m<addr>,<len>`) is architecture-agnostic: it
returns raw hex bytes. So a ~100-line client can read ares's memory even though
gdb itself cannot attach. That unblocks the only G6 question that matters here
-- "does real-hardware-accurate emulation corrupt the same address we do?" --
without waiting on a gdb-multiarch install.

Start ares with its debug server first:

    flatpak run dev.ares.ares --setting DebugServer/Enabled=true \\
        --setting DebugServer/Port=9123 --setting DebugServer/UseIPv4=true \\
        --system "Nintendo 64" "rom/Tsumi to Batsu - Hoshi no Keishousha (Japan).z64"

Then:

    python3 scripts/ares_peek.py --addr 0x8007AF0C --seconds 60

Addresses may be given as KSEG0 virtual (0x8007AF0C); if the stub rejects those
the script retries with the physical equivalent (0x0007AF0C) and says so.
"""

import argparse
import socket
import sys
import time


class RSPError(Exception):
    pass


class RSP:
    """Minimal GDB remote serial protocol client: connect, interrupt, read, continue."""

    debug = False

    def __init__(self, host, port, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    @staticmethod
    def _checksum(payload):
        return sum(payload) & 0xFF

    def send(self, payload):
        data = payload.encode()
        pkt = b"$" + data + b"#" + b"%02x" % self._checksum(data)
        if self.debug:
            print("[ares_peek] --> %r" % pkt, file=sys.stderr)
        self.sock.sendall(pkt)
        self._read_ack()

    def _read_ack(self):
        # The stub replies '+' (ack) or '-' (retransmit). Some stubs run in
        # no-ack mode and send nothing; tolerate both rather than hanging.
        try:
            ch = self._recv_byte()
        except socket.timeout:
            return
        if ch == b"-":
            raise RSPError("stub requested retransmit")

    def _recv_byte(self):
        if self.buf:
            ch, self.buf = self.buf[:1], self.buf[1:]
            return ch
        data = self.sock.recv(1)
        if not data:
            raise RSPError("connection closed by ares")
        return data

    def read_packet(self):
        """Return the payload of the next $...#xx packet, skipping acks."""
        while True:
            ch = self._recv_byte()
            if ch != b"$":
                continue
            body = b""
            while True:
                c = self._recv_byte()
                if c == b"#":
                    break
                body += c
            self._recv_byte()  # checksum digits
            self._recv_byte()
            try:
                self.sock.sendall(b"+")
            except OSError:
                pass
            return body.decode(errors="replace")

    def interrupt(self):
        """Ctrl-C equivalent: raw 0x03, not a packet."""
        self.sock.sendall(b"\x03")
        try:
            return self.read_packet()
        except socket.timeout:
            return ""

    def cont(self):
        self.send("c")

    def read_mem(self, addr, length):
        self.send("m%x,%x" % (addr, length))
        reply = self.read_packet()
        if reply.startswith("E") or reply == "":
            raise RSPError("memory read rejected at 0x%08X (reply %r)" % (addr, reply))
        return bytes.fromhex(reply)


def to_physical(addr):
    # KSEG0/KSEG1 -> physical.
    if 0x80000000 <= addr < 0xA0000000:
        return addr - 0x80000000
    if 0xA0000000 <= addr < 0xC0000000:
        return addr - 0xA0000000
    return addr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=9123)
    ap.add_argument("--addr", action="append", required=True,
                    help="address to sample; repeatable")
    ap.add_argument("--words", type=int, default=1, help="words to read per address")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--debug", action="store_true", help="print raw protocol traffic")
    args = ap.parse_args()

    addrs = [int(a, 0) for a in args.addr]

    try:
        rsp = RSP(args.host, args.port)
    except OSError as e:
        sys.exit("[ares_peek] cannot connect to %s:%d (%s) -- is ares running "
                 "with DebugServer/Enabled=true?" % (args.host, args.port, e))

    rsp.debug = args.debug

    # Drain anything the stub volunteers on connect and ACK it before speaking.
    # ares closes the session if the client talks over an unacknowledged packet.
    rsp.sock.settimeout(1.5)
    try:
        greeting = rsp.read_packet()
        if args.debug:
            print("[ares_peek] greeting: %r" % greeting[:120], file=sys.stderr)
    except (RSPError, OSError, socket.timeout):
        if args.debug:
            print("[ares_peek] no greeting packet", file=sys.stderr)
    rsp.sock.settimeout(5.0)

    # Handshake FIRST. ares closes the connection outright if the very first
    # packet is an execution command -- the stub expects the normal gdb opening
    # exchange (feature negotiation, then a halt-reason query) before anything
    # else. Failures here are reported but not fatal, since different ares
    # versions support different subsets.
    for pkt in ("qSupported:multiprocess+;swbreak+;hwbreak+;xmlRegisters=mips", "?"):
        try:
            rsp.send(pkt)
            reply = rsp.read_packet()
            if args.debug:
                print("[ares_peek] %s -> %r" % (pkt.split(":")[0], reply[:120]),
                      file=sys.stderr)
        except (RSPError, OSError, socket.timeout) as e:
            print("[ares_peek] handshake %s failed: %s" % (pkt.split(":")[0], e),
                  file=sys.stderr)

    # The stub is usually halted on connect; let the game run.
    try:
        rsp.cont()
    except (RSPError, OSError) as e:
        print("[ares_peek] note: initial continue failed (%s)" % e, file=sys.stderr)

    use_phys = False
    start = time.monotonic()
    last = {}
    while time.monotonic() - start < args.seconds:
        time.sleep(args.interval)
        elapsed = time.monotonic() - start
        try:
            rsp.interrupt()
            for a in addrs:
                target = to_physical(a) if use_phys else a
                try:
                    raw = rsp.read_mem(target, 4 * args.words)
                except RSPError:
                    if use_phys:
                        raise
                    use_phys = True
                    print("[ares_peek] virtual addressing rejected; "
                          "retrying with physical", file=sys.stderr)
                    raw = rsp.read_mem(to_physical(a), 4 * args.words)
                for i in range(args.words):
                    word = int.from_bytes(raw[i * 4:i * 4 + 4], "big")
                    key = a + i * 4
                    changed = key in last and last[key] != word
                    print("[ares] t=%5.1fs 0x%08X = 0x%08X%s"
                          % (elapsed, key, word, "   <<< CHANGED" if changed else ""),
                          flush=True)
                    last[key] = word
            rsp.cont()
        except (RSPError, OSError, socket.timeout) as e:
            print("[ares_peek] lost connection at t=%.1fs: %s" % (elapsed, e),
                  file=sys.stderr)
            break

    rsp.close()


if __name__ == "__main__":
    main()
