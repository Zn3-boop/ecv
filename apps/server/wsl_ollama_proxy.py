"""WSL Ollama HTTP proxy: Windows localhost:11436 -> WSL localhost:11434 via wsl curl"""
import asyncio
import json
import sys
import base64
import os

LOCAL_PORT = 11436
WSL_OLLAMA = "http://127.0.0.1:11434"

async def handle_client(reader, writer):
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not request_line:
            writer.close()
            return
        headers = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line == b"\r\n" or not line:
                break
            if b":" in line:
                k, v = line.decode(errors="replace").strip().split(":", 1)
                headers[k.strip()] = v.strip()
        content_length = int(headers.get("Content-Length", "0"))
        body = b""
        if content_length > 0:
            body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10)
        req_str = request_line.decode(errors="replace").strip()
        parts = req_str.split(" ", 2)
        method, path = parts[0], parts[1]
        tmp_name = None
        try:
            if body:
                import tempfile
                fd, tmp_path = tempfile.mkstemp(suffix=".json")
                os.write(fd, body)
                os.close(fd)
                drive = tmp_path[0].lower()
                rest = tmp_path[3:].replace("\\", "/")
                wsl_tmp = f"/mnt/{drive}/{rest}"
                wsl_cmd = f"curl -s --compressed -X {method} -d @{wsl_tmp} '{WSL_OLLAMA}{path}'"
                tmp_name = tmp_path
            else:
                wsl_cmd = f"curl -s --compressed -X {method} '{WSL_OLLAMA}{path}'"
            proc = await asyncio.create_subprocess_exec(
                "wsl", "-e", "bash", "-c", wsl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            resp_body = stdout
            if not resp_body and stderr:
                resp_body = stderr
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except:
                    pass
        resp_headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(resp_body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        writer.write(resp_headers.encode() + resp_body)
        await writer.drain()
    except Exception as e:
        try:
            err_body = json.dumps({"error": str(e)}).encode()
            resp = f"HTTP/1.1 500 Error\r\nContent-Length: {len(err_body)}\r\n\r\n".encode() + err_body
            writer.write(resp)
            await writer.drain()
        except:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

async def main():
    server = await asyncio.start_server(handle_client, "127.0.0.1", LOCAL_PORT)
    print(f"Ollama WSL proxy: http://localhost:{LOCAL_PORT} -> wsl {WSL_OLLAMA}")
    sys.stdout.flush()
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())