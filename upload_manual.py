import argparse
import base64
import time

try:
    from serial import serial_for_url
except ImportError:
    raise SystemExit("pyserial não está instalado. Execute: pip install pyserial")


def connect_uri(uri, baudrate=115200, timeout=2):
    print(f"connecting to {uri}")
    s = serial_for_url(uri, baudrate=baudrate, timeout=timeout)
    s.reset_input_buffer()
    s.reset_output_buffer()
    return s


def enter_raw_repl(s, attempts=5):
    for attempt in range(1, attempts + 1):
        print(f"raw REPL attempt {attempt}/{attempts}")
        s.write(b"\r\x03\x03")
        time.sleep(0.1)
        s.write(b"\r\x01")
        time.sleep(0.2)
        data = s.read(256)
        if b"raw REPL" in data:
            print("entered raw REPL")
            return True
        time.sleep(0.2)
    return False


def exec_raw(s, code):
    if isinstance(code, str):
        code = code.encode("utf-8")
    s.write(code + b"\x04")
    output = b""
    while True:
        chunk = s.read(256)
        if not chunk:
            break
        output += chunk
        if b"\x04" in output:
            break
    output = output.replace(b"\x04", b"")
    return output


def upload_file(s, local_path, remote_path):
    with open(local_path, "rb") as f:
        payload = f.read()

    b64data = base64.b64encode(payload).decode("ascii")
    chunks = [b64data[i : i + 720] for i in range(0, len(b64data), 720)]

    script = f"import ubinascii\r\nf=open('{remote_path}','wb')\r\n"
    for chunk in chunks:
        script += f"f.write(ubinascii.a2b_base64({chunk!r}))\r\n"
    script += "f.close()\r\n"

    print(f"Uploading {local_path} to {remote_path}")
    result = exec_raw(s, script)
    print(result.decode("utf-8", errors="replace"))


def soft_reboot(s):
    print("Reiniciando ESP32...")
    s.write(b"\x04")
    time.sleep(1)
    print("Reboot enviado.")


def main():
    parser = argparse.ArgumentParser(description="Upload manual de main.py via RFC2217 para Wokwi ESP32")
    parser.add_argument("local_path", help="Arquivo local a ser enviado")
    parser.add_argument("remote_path", help="Caminho destino no ESP32")
    parser.add_argument("uri", help="URI RFC2217, por exemplo rfc2217://localhost:4000")
    args = parser.parse_args()

    serial = connect_uri(args.uri)
    if not enter_raw_repl(serial):
        raise SystemExit("Não foi possível entrar no raw REPL.")

    upload_file(serial, args.local_path, args.remote_path)
    soft_reboot(serial)
    serial.close()
    print("Upload concluído com sucesso.")


if __name__ == "__main__":
    main()