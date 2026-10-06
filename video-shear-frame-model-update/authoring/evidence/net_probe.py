"""Authoring probe: prove the oracle container has no network (the only network call in the package)."""
import os
import socket

ifaces = sorted(os.listdir("/sys/class/net"))
print("interfaces present: " + " ".join(i + ":" for i in ifaces))
try:
    socket.getaddrinfo("pypi.org", 443)
    print("NETWORK: reachable (unexpected)")
except socket.gaierror as exc:
    print("NETWORK: unreachable -> gaierror (%s)" % exc)
