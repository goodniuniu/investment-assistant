# -*- coding: utf-8 -*-
"""本地开发预览服务器（npm run dev 入口）。

纯标准库静态服务器，服务于项目根目录（GitHub Pages 同源）。
支持 npm 转发的主机/端口参数：
    npm run dev                      # 默认 127.0.0.1:7100
    npm run dev -- --port 8123       # 指定端口
    npm run dev -- --host 0.0.0.0 --port 8123
"""
import argparse
import functools
import http.server
import os
import socketserver


def main():
    parser = argparse.ArgumentParser(description="投资辅助站本地预览服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7100)
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print("投资辅助站预览: http://%s:%d/" % (args.host, args.port))
        print("根目录: %s" % root)
        print("Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
