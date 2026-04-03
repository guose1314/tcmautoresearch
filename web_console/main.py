"""本地启动 Web Console API。"""

from importlib import import_module

from web_console.app import app

if __name__ == "__main__":
    uvicorn = import_module("uvicorn")

    uvicorn.run(app, host="127.0.0.1", port=8000)