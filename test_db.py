import socket
import sys

def check_host(host, port=3306):
    try:
        ip = socket.gethostbyname(host)
        print(f"Host '{host}' resolves to IP: {ip}")
    except socket.gaierror:
        print(f"Host '{host}' could NOT be resolved.")
        return

    try:
        print(f"Attempting to connect to {host}:{port}...")
        with socket.create_connection((host, port), timeout=5):
            print(f"SUCCESS: Port {port} on {host} is reachable!")
    except Exception as e:
        print(f"FAILED: Could not connect to {host}:{port}. Error: {e}")

if __name__ == "__main__":
    check_host("pppc.mysql.database.azure.com")
    print("-" * 40)
    check_host("ppsc.mysql.database.azure.com")
    print("-" * 40)
    check_host("ppsc-paper-bank.mysql.database.azure.com")
