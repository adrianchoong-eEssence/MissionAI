#!/usr/bin/env python3
"""Fail closed when the deployed Python/TLS runtime is unsupported."""

import json
import ssl
import sys


def runtime_report():
    python_ok = sys.version_info >= (3, 11)
    openssl_info = getattr(ssl, "OPENSSL_VERSION_INFO", (0, 0, 0))
    openssl_ok = openssl_info >= (1, 1, 1) and "LibreSSL" not in ssl.OPENSSL_VERSION
    return {
        "Python": sys.version.split()[0],
        "PythonMinimum": "3.11",
        "PythonSupported": python_ok,
        "TLSLibrary": ssl.OPENSSL_VERSION,
        "OpenSSLMinimum": "1.1.1",
        "TLSSupported": openssl_ok,
        "Passed": python_ok and openssl_ok,
    }


def main():
    report = runtime_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["Passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
