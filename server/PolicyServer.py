import socket
import threading

_POLICY = b'''<?xml version="1.0"?>
<!DOCTYPE cross-domain-policy SYSTEM
  "http://www.adobe.com/xml/dtds/cross-domain-policy.dtd">
<cross-domain-policy>
  <allow-access-from domain="*" to-ports="1-65535" secure="false"/>
</cross-domain-policy>\0'''

def start_policy_server(host: str = "127.0.0.1", port: int = 843):

    def _serve():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind((host, port))
            sock.listen(5)
            sock.settimeout(1.0)

            while True:
                try:
                    conn, addr = sock.accept()
                except socket.timeout:
                    continue

                try:
                    conn.settimeout(2.0)
                    data = conn.recv(64)
                    if b"<policy-file-request/>" in data:
                        conn.sendall(_POLICY)
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

        except Exception as e:
            print(f"[Policy] Fatal error: {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    thread = threading.Thread(
        target=_serve,
        name="FlashPolicyServer",
        daemon=True
    )
    thread.start()
    return thread
