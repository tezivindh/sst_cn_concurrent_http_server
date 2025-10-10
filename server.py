# HTTP Server Assignment - Socket Programming
# Multi-threaded server implementation

import socket
import threading
import os, sys
import json
import time
import hashlib
from datetime import datetime
from urllib.parse import unquote
from queue import Queue, Empty


class ThreadPool:
    def __init__(self, size=10):
        self.size = size
        self.active = 0
        self.q = Queue()
        self.lock = threading.Lock()
        self.running = True
        
        # create worker threads
        for i in range(size):
            thread_name = "Thread-" + str(i+1)
            t = threading.Thread(target=self.worker, name=thread_name, daemon=True)
            t.start()
    
    def worker(self):
        while self.running == True:
            try:
                # get next connection from queue
                client, addr, server = self.q.get(timeout=1)
                
                # increment active count
                self.lock.acquire()
                self.active = self.active + 1
                self.lock.release()
                
                print_log("[%s] Connection dequeued, now serving" % threading.current_thread().name)
                
                # handle the client
                server.handle_client(client, addr)
                
                # decrement active count
                self.lock.acquire()
                self.active = self.active - 1
                self.lock.release()
                
            except Empty:
                # no work to do, continue
                pass
            except Exception as ex:
                print_log("[%s] Worker error: %s" % (threading.current_thread().name, str(ex)))
                # make sure to decrement count on error
                self.lock.acquire()
                self.active = self.active - 1
                self.lock.release()
    
    def submit(self, client, addr, server):
        # check queue size
        qsize = self.q.qsize()
        if qsize >= 50:
            print_log("Warning: Connection queue full, rejecting connection from %s:%d" % (addr[0], addr[1]))
            client.close()
            return
        
        if qsize > 0:
            print_log("Warning: Thread pool saturated, queuing connection (queue size: %d)" % qsize)
        
        # add to queue
        self.q.put((client, addr, server))
    
    def status(self):
        self.lock.acquire()
        active_count = self.active
        self.lock.release()
        return active_count, self.size
    
    def stop(self):
        self.running = False
class HTTPServer:
    def __init__(self, host='127.0.0.1', port=8080, threads=10):
        self.host = host
        self.port = port
        self.threads = threads
        self.resources = 'resources'
        self.uploads = self.resources + '/uploads'
        self.socket = None
        self.pool = None
        self.timeout = 30
        self.max_requests = 100
        
        # setup directories
        try:
            os.makedirs(self.resources)
        except:
            pass
        try:
            os.makedirs(self.uploads)
        except:
            pass
    
    def start(self):
        try:
            # setup socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(50)
            self.socket = sock
            
            # thread pool
            pool = ThreadPool(size=self.threads)
            self.pool = pool
            
            print_log("HTTP Server started on http://%s:%d" % (self.host, self.port))
            print_log("Thread pool size: %d" % self.threads)
            print_log("Serving files from '%s' directory" % self.resources)
            print_log("Press Ctrl+C to stop the server")
            
            # accept connections
            while 1:
                try:
                    c, a = self.socket.accept()
                    self.pool.submit(c, a, self)
                    
                    # thread status
                    act, tot = self.pool.status()
                    if act > tot * 0.7:
                        print_log("Thread pool status: %d/%d active" % (act, tot))
                        
                except KeyboardInterrupt:
                    print_log("\nShutting down server...")
                    break
                except Exception as ex:
                    print_log("Error accepting connection: " + str(ex))
        
        except Exception as ex:
            print_log("Server error: " + str(ex))
        finally:
            if self.pool != None:
                self.pool.stop()
            if self.socket != None:
                self.socket.close()
            print_log("Server stopped")
    
    def handle_client(self, client, addr):
        t = threading.current_thread().name
        print_log("[%s] Connection from %s:%d" % (t, addr[0], addr[1]))
        
        cnt = 0
        keep_alive = True
        
        try:
            while keep_alive == True and cnt < self.max_requests:
                client.settimeout(self.timeout)
                
                try:
                    # read request from client
                    req_data = b""
                    while 1:
                        ch = client.recv(8192)
                        if len(ch) == 0:
                            keep_alive = False
                            break
                        req_data = req_data + ch
                        
                        # check for end of headers
                        if b"\r\n\r\n" in req_data:
                            p = req_data.find(b"\r\n\r\n")
                            hdr = req_data[:p].decode('utf-8', errors='ignore')
                            
                            # check content length
                            cl = 0
                            lines = hdr.split('\r\n')
                            for line in lines:
                                if line.lower().startswith('content-length:'):
                                    cl = int(line.split(':')[1].strip())
                                    break
                            
                            bl = len(req_data) - p - 4
                            if bl >= cl:
                                break
                        
                        # limit size
                        if len(req_data) > 8192:
                            break
                    
                    if len(req_data) == 0:
                        break
                    
                    cnt = cnt + 1
                    
                    # parse request
                    parsed = self.parse(req_data)
                    if parsed != None:
                        resp, ctype = self.handle(parsed, t)
                        client.sendall(resp)
                        
                        ver = parsed.get('version', 'HTTP/1.0')
                        if ctype == 'close' or ver == 'HTTP/1.0':
                            keep_alive = False
                        
                        print_log("[%s] Connection: %s" % (t, ctype))
                    else:
                        e = self.error(400, "Bad Request")
                        client.sendall(e)
                        keep_alive = False
                
                except socket.timeout:
                    print_log("[%s] Connection timeout" % t)
                    keep_alive = False
                except Exception as ex:
                    print_log("[%s] Error handling request: %s" % (t, str(ex)))
                    keep_alive = False
        
        finally:
            client.close()
            print_log("[%s] Connection closed (%d requests served)" % (t, cnt))
    
    def parse(self, data):
        try:
            if b"\r\n\r\n" in data:
                h, b = data.split(b"\r\n\r\n", 1)
            else:
                h = data
                b = b""
            
            ht = h.decode('utf-8', errors='ignore')
            lines = ht.split('\r\n')
            
            if not lines:
                return None
            
            p = lines[0].split()
            if len(p) != 3:
                return None
            
            m, path, v = p
            
            headers = {}
            for l in lines[1:]:
                if ':' in l:
                    k, val = l.split(':', 1)
                    headers[k.strip().lower()] = val.strip()
            
            return {'method': m.upper(), 'path': path, 'version': v, 'headers': headers, 'body': b}
        
        except Exception as e:
            print_log("Error parsing request: " + str(e))
            return None
    
    def handle(self, req, tname):
        m = req['method']
        p = req['path']
        v = req['version']
        h = req['headers']
        
        print_log("[%s] Request: %s %s %s" % (tname, m, p, v))
        
        # check host header
        host = h.get('host', '')
        if not host:
            print_log("[%s] Security violation: Missing Host header" % tname)
            return self.error(400, "Bad Request", "Missing Host header"), 'close'
        
        # validate host
        valid = [self.host + ":" + str(self.port), "localhost:" + str(self.port), 
                 "127.0.0.1:" + str(self.port), self.host, "localhost", "127.0.0.1"]
        if host not in valid:
            print_log("[%s] Security violation: Host mismatch (%s)" % (tname, host))
            return self.error(403, "Forbidden", "Host header mismatch"), 'close'
        
        print_log("[%s] Host validation: %s ✓" % (tname, host))
        
        # path validation
        if not self.safe_path(p):
            print_log("[%s] Security violation: Path traversal attempt (%s)" % (tname, p))
            return self.error(403, "Forbidden", "Unauthorized path access"), 'close'
        
        # connection type
        c = h.get('connection', '').lower()
        if c == 'close':
            conn = 'close'
        elif c == 'keep-alive':
            conn = 'keep-alive'
        else:
            conn = 'keep-alive' if v == 'HTTP/1.1' else 'close'
        
        # route
        if m == 'GET':
            r = self.get(p, tname, conn)
        elif m == 'POST':
            r = self.post(req, tname, conn)
        else:
            r = self.error(405, "Method Not Allowed", "Only GET and POST methods are supported", conn)
        
        return r, conn
    
    def safe_path(self, p):
        clean = unquote(p)
        
        bad = ['..', './', '\\', '//', '\\\\']
        for b in bad:
            if b in clean:
                return False
        
        if clean.startswith('/') and len(clean) > 1:
            t = clean[1:]
        else:
            t = clean
        
        try:
            if clean == '/' or clean == '':
                return True
            
            fp = os.path.join(self.resources, t.lstrip('/'))
            rp = os.path.abspath(fp)
            bp = os.path.abspath(self.resources)
            
            return rp.startswith(bp)
        except:
            return False
    
    def get(self, path, t, conn):
        # default to index
        if path == '/' or path == '':
            path = '/index.html'
        
        # build file path
        filepath = self.resources + '/' + path.lstrip('/')
        
        # check if file exists
        if os.path.exists(filepath) == False or os.path.isfile(filepath) == False:
            return self.error(404, "Not Found", "The requested resource %s was not found" % path, conn)
        
        # get file extension
        parts = os.path.splitext(filepath)
        ext = parts[1].lower()
        
        # determine content type
        if ext == '.html':
            content_type = 'text/html; charset=utf-8'
            is_binary = False
        elif ext in ['.txt', '.png', '.jpg', '.jpeg']:
            content_type = 'application/octet-stream'
            is_binary = True
        else:
            return self.error(415, "Unsupported Media Type", "File type %s is not supported" % ext, conn)
        
        try:
            if is_binary == True:
                # read binary file
                f = open(filepath, 'rb')
                data = f.read()
                f.close()
                
                size = len(data)
                filename = os.path.basename(filepath)
                
                print_log("[%s] Sending binary file: %s (%d bytes)" % (t, filename, size))
                
                resp = self.binary(data, filename, conn)
                print_log("[%s] Response: 200 OK (%d bytes transferred)" % (t, size))
                
                return resp
            else:
                # read text file
                f = open(filepath, 'r', encoding='utf-8')
                content = f.read()
                f.close()
                
                size = len(content.encode('utf-8'))
                
                print_log("[%s] Sending HTML file: %s (%d bytes)" % (t, os.path.basename(filepath), size))
                
                resp = self.response(200, "OK", content, content_type, conn)
                print_log("[%s] Response: 200 OK (%d bytes transferred)" % (t, size))
                
                return resp
        
        except Exception as ex:
            print_log("[%s] Error reading file: %s" % (t, str(ex)))
            return self.error(500, "Internal Server Error", "Error reading file", conn)
    
    def post(self, req, tname, conn):
        h = req['headers']
        b = req['body']
        
        ct = h.get('content-type', '')
        if 'application/json' not in ct:
            print_log("[%s] Invalid Content-Type for POST: %s" % (tname, ct))
            return self.error(415, "Unsupported Media Type", 
                            "Only application/json is supported for POST requests", conn)
        
        try:
            d = json.loads(b.decode('utf-8'))
        except json.JSONDecodeError as e:
            print_log("[%s] Invalid JSON: %s" % (tname, str(e)))
            return self.error(400, "Bad Request", "Invalid JSON data", conn)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rid = hashlib.md5(str(time.time()).encode()).hexdigest()[:4]
        fn = "upload_%s_%s.json" % (ts, rid)
        fp = os.path.join(self.uploads, fn)
        
        try:
            f = open(fp, 'w', encoding='utf-8')
            json.dump(d, f, indent=2)
            f.close()
            
            rd = {"status": "success", "message": "File created successfully", 
                  "filepath": "/uploads/" + fn}
            
            print_log("[%s] JSON file created: %s" % (tname, fn))
            print_log("[%s] Response: 201 Created" % tname)
            
            rj = json.dumps(rd, indent=2)
            return self.response(201, "Created", rj, 'application/json', conn)
        
        except Exception as e:
            print_log("[%s] Error saving file: %s" % (tname, str(e)))
            return self.error(500, "Internal Server Error", "Error saving file", conn)
    
    def response(self, code, msg, body, ct, conn='close'):
        bd = body.encode('utf-8') if isinstance(body, str) else body
        
        l = ["HTTP/1.1 %d %s" % (code, msg), "Content-Type: %s" % ct, 
             "Content-Length: %d" % len(bd), "Date: %s" % http_date(),
             "Server: Multi-threaded HTTP Server", "Connection: %s" % conn]
        
        if conn == 'keep-alive':
            l.append("Keep-Alive: timeout=%d, max=%d" % (self.timeout, self.max_requests))
        
        l.append("")
        l.append("")
        
        h = "\r\n".join(l).encode('utf-8')
        return h + bd
    
    def binary(self, d, fn, conn='close'):
        l = ["HTTP/1.1 200 OK", "Content-Type: application/octet-stream",
             "Content-Length: %d" % len(d), 'Content-Disposition: attachment; filename="%s"' % fn,
             "Date: %s" % http_date(), "Server: Multi-threaded HTTP Server",
             "Connection: %s" % conn]
        
        if conn == 'keep-alive':
            l.append("Keep-Alive: timeout=%d, max=%d" % (self.timeout, self.max_requests))
        
        l.append("")
        l.append("")
        
        h = "\r\n".join(l).encode('utf-8')
        return h + d
    
    def error(self, code, msg, det="", conn='close'):
        b = """<!DOCTYPE html>
<html>
<head>
    <title>%d %s</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 50px; }
        h1 { color: #d32f2f; }
        p { color: #666; }
    </style>
</head>
<body>
    <h1>%d %s</h1>
    <p>%s</p>
    <hr>
    <p><em>Multi-threaded HTTP Server</em></p>
</body>
</html>""" % (code, msg, code, msg, det)
        
        l = ["HTTP/1.1 %d %s" % (code, msg), "Content-Type: text/html; charset=utf-8",
             "Content-Length: %d" % len(b.encode('utf-8')), "Date: %s" % http_date(),
             "Server: Multi-threaded HTTP Server", "Connection: %s" % conn]
        
        if code == 503:
            l.append("Retry-After: 30")
        
        l.append("")
        l.append("")
        
        h = "\r\n".join(l)
        return (h + b).encode('utf-8')


def print_log(m):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[%s] %s" % (t, m))


def http_date():
    from email.utils import formatdate
    return formatdate(timeval=None, localtime=False, usegmt=True)


def main():
    h = '127.0.0.1'
    p = 8080
    t = 10
    
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            print("Error: Port must be a number")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        h = sys.argv[2]
    
    if len(sys.argv) > 3:
        try:
            t = int(sys.argv[3])
        except ValueError:
            print("Error: Max threads must be a number")
            sys.exit(1)
    
    s = HTTPServer(host=h, port=p, threads=t)
    s.start()


if __name__ == "__main__":
    main()
