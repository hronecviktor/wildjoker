"""Run the server: ``python -m wildjoker.server [--host HOST] [--port PORT]``."""

import argparse
import logging

import uvicorn

from . import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
logging.basicConfig(level=logging.INFO)
uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=True, ws_max_size=65536)
