#!/usr/bin/env python3
import os, http.server, socketserver

os.chdir(os.path.dirname(os.path.abspath(__file__)))

PORT = 3838
Handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()
