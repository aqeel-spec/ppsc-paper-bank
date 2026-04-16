import socket

with open("D:\\2025_practice\\ppsc-paper-bank\\result.txt", "w") as f:
    try:
        ip_pppc = socket.gethostbyname("pppc.mysql.database.azure.com")
        f.write("pppc resolved to: " + ip_pppc + "\n")
    except Exception as e:
        f.write("pppc failed: " + str(e) + "\n")
        
    try:
        ip_ppsc = socket.gethostbyname("ppsc.mysql.database.azure.com")
        f.write("ppsc resolved to: " + ip_ppsc + "\n")
    except Exception as e:
        f.write("ppsc failed: " + str(e) + "\n")
