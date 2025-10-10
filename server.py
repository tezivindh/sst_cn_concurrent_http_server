"""
Multi-threaded HTTP Server with Socket Programming
A comprehensive HTTP server implementation supporting GET/POST requests,
binary file transfers, JSON processing, and connection management.
"""

import socket
import threading
import os
import sys
import json
import time
import hashlib
from datetime import datetime
from urllib.parse import unquote
from queue import Queue, Empty
from pathlib import Path


class ThreadPool:
    """
    Thread pool for handling multiple concurrent client connections.
    Implements a fixed-size pool with a connection queue.
    """
    
    def __init__(self, max_threads=10):
        self.max_threads = max_threads
        self.active_threads = 0
        self.connection_queue = Queue()
        self.lock = threading.Lock()
        self.shutdown_flag = threading.Event()
        
        # Start worker threads
        for i in range(max_threads):
            thread = threading.Thread(target=self._worker, name=f"Thread-{i+1}", daemon=True)
            thread.start()
    
    def _worker(self):
        """Worker thread that processes connections from the queue."""
        while not self.shutdown_flag.is_set():
            try:
                # Wait for a connection with timeout to allow checking shutdown flag
                client_socket, client_address, server = self.connection_queue.get(timeout=1)
                
                with self.lock:
                    self.active_threads += 1
                
                log(f"[{threading.current_thread().name}] Connection dequeued, now serving")
                
                # Handle the client connection
                server.handle_client(client_socket, client_address)
                
                with self.lock:
                    self.active_threads -= 1
                    
            except Empty:
                continue
            except Exception as e:
                log(f"[{threading.current_thread().name}] Worker error: {e}")
                with self.lock:
                    self.active_threads -= 1
    
    def submit(self, client_socket, client_address, server):
        """Submit a new connection to the thread pool."""
        if self.connection_queue.qsize() >= 50:
            log(f"Warning: Connection queue full, rejecting connection from {client_address[0]}:{client_address[1]}")
            client_socket.close()
            return
        
        queue_size = self.connection_queue.qsize()
        if queue_size > 0:
            log(f"Warning: Thread pool saturated, queuing connection (queue size: {queue_size})")
        
        self.connection_queue.put((client_socket, client_address, server))
    
    def get_status(self):
        """Get current thread pool status."""
        with self.lock:
            return self.active_threads, self.max_threads
    
    def shutdown(self):
        """Shutdown the thread pool."""
        self.shutdown_flag.set()


class HTTPServer:
    """
    Multi-threaded HTTP Server implementation.
    Handles GET and POST requests with security features and connection management.
    """
    
    def __init__(self, host='127.0.0.1', port=8080, max_threads=10):
        self.host = host
        self.port = port
        self.max_threads = max_threads
        self.resources_dir = 'resources'
        self.uploads_dir = os.path.join(self.resources_dir, 'uploads')
        self.server_socket = None
        self.thread_pool = None
        
        # Connection settings
        self.keep_alive_timeout = 30
        self.max_requests_per_connection = 100
        
        # Create necessary directories
        self._setup_directories()
    
    def _setup_directories(self):
        """Create resources and uploads directories if they don't exist."""
        os.makedirs(self.resources_dir, exist_ok=True)
        os.makedirs(self.uploads_dir, exist_ok=True)
    
    def start(self):
        """Start the HTTP server."""
        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind and listen
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(50)
            
            # Initialize thread pool
            self.thread_pool = ThreadPool(max_threads=self.max_threads)
            
            # Startup logs
            log(f"HTTP Server started on http://{self.host}:{self.port}")
            log(f"Thread pool size: {self.max_threads}")
            log(f"Serving files from '{self.resources_dir}' directory")
            log("Press Ctrl+C to stop the server")
            
            # Accept connections
            while True:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    
                    # Submit to thread pool
                    self.thread_pool.submit(client_socket, client_address, self)
                    
                    # Log thread pool status periodically
                    active, total = self.thread_pool.get_status()
                    if active > total * 0.7:  # Log when >70% utilized
                        log(f"Thread pool status: {active}/{total} active")
                        
                except KeyboardInterrupt:
                    log("\nShutting down server...")
                    break
                except Exception as e:
                    log(f"Error accepting connection: {e}")
            
        except Exception as e:
            log(f"Server error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the server and cleanup resources."""
        if self.thread_pool:
            self.thread_pool.shutdown()
        if self.server_socket:
            self.server_socket.close()
        log("Server stopped")
    
    def handle_client(self, client_socket, client_address):
        """
        Handle a client connection with keep-alive support.
        Maintains connection for multiple requests if keep-alive is enabled.
        """
        thread_name = threading.current_thread().name
        log(f"[{thread_name}] Connection from {client_address[0]}:{client_address[1]}")
        
        request_count = 0
        keep_alive = True
        
        try:
            while keep_alive and request_count < self.max_requests_per_connection:
                # Set timeout for persistent connections
                client_socket.settimeout(self.keep_alive_timeout)
                
                try:
                    # Receive request
                    request_data = b""
                    while True:
                        chunk = client_socket.recv(8192)
                        if not chunk:
                            keep_alive = False
                            break
                        request_data += chunk
                        
                        # Check for end of headers
                        if b"\r\n\r\n" in request_data:
                            # Check if there's a body
                            headers_end = request_data.find(b"\r\n\r\n")
                            headers = request_data[:headers_end].decode('utf-8', errors='ignore')
                            
                            # Check for Content-Length
                            content_length = 0
                            for line in headers.split('\r\n'):
                                if line.lower().startswith('content-length:'):
                                    content_length = int(line.split(':')[1].strip())
                            
                            # If there's a body, make sure we received it all
                            body_received = len(request_data) - headers_end - 4
                            if body_received >= content_length:
                                break
                        
                        # Limit request size
                        if len(request_data) > 8192:
                            break
                    
                    if not request_data:
                        break
                    
                    request_count += 1
                    
                    # Parse and handle request
                    request = self.parse_request(request_data)
                    if request:
                        response, connection_type = self.handle_request(request, thread_name)
                        
                        # Send response
                        client_socket.sendall(response)
                        
                        # Check if we should keep the connection alive
                        if connection_type == 'close' or request.get('version', 'HTTP/1.0') == 'HTTP/1.0':
                            keep_alive = False
                        
                        log(f"[{thread_name}] Connection: {connection_type}")
                    else:
                        # Invalid request
                        response = self.build_error_response(400, "Bad Request")
                        client_socket.sendall(response)
                        keep_alive = False
                
                except socket.timeout:
                    log(f"[{thread_name}] Connection timeout")
                    keep_alive = False
                except Exception as e:
                    log(f"[{thread_name}] Error handling request: {e}")
                    keep_alive = False
        
        finally:
            client_socket.close()
            log(f"[{thread_name}] Connection closed ({request_count} requests served)")
    
    def parse_request(self, request_data):
        """
        Parse HTTP request and extract method, path, version, headers, and body.
        Returns a dictionary with request components or None if invalid.
        """
        try:
            # Split headers and body
            if b"\r\n\r\n" in request_data:
                headers_part, body_part = request_data.split(b"\r\n\r\n", 1)
            else:
                headers_part = request_data
                body_part = b""
            
            # Decode headers
            headers_text = headers_part.decode('utf-8', errors='ignore')
            lines = headers_text.split('\r\n')
            
            if not lines:
                return None
            
            # Parse request line
            request_line = lines[0].split()
            if len(request_line) != 3:
                return None
            
            method, path, version = request_line
            
            # Parse headers into dictionary
            headers = {}
            for line in lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().lower()] = value.strip()
            
            return {
                'method': method.upper(),
                'path': path,
                'version': version,
                'headers': headers,
                'body': body_part
            }
        
        except Exception as e:
            log(f"Error parsing request: {e}")
            return None
    
    def handle_request(self, request, thread_name):
        """
        Route and handle HTTP requests based on method.
        Returns (response_bytes, connection_type).
        """
        method = request['method']
        path = request['path']
        version = request['version']
        headers = request['headers']
        
        log(f"[{thread_name}] Request: {method} {path} {version}")
        
        # Validate Host header
        host_header = headers.get('host', '')
        if not host_header:
            log(f"[{thread_name}] Security violation: Missing Host header")
            return self.build_error_response(400, "Bad Request", "Missing Host header"), 'close'
        
        # Validate Host matches server address
        valid_hosts = [
            f"{self.host}:{self.port}",
            f"localhost:{self.port}",
            f"127.0.0.1:{self.port}",
            self.host,
            "localhost",
            "127.0.0.1"
        ]
        if host_header not in valid_hosts:
            log(f"[{thread_name}] Security violation: Host mismatch ({host_header})")
            return self.build_error_response(403, "Forbidden", "Host header mismatch"), 'close'
        
        log(f"[{thread_name}] Host validation: {host_header} ✓")
        
        # Validate path for security
        if not self.validate_path(path):
            log(f"[{thread_name}] Security violation: Path traversal attempt ({path})")
            return self.build_error_response(403, "Forbidden", "Unauthorized path access"), 'close'
        
        # Determine connection type
        connection_header = headers.get('connection', '').lower()
        if connection_header == 'close':
            connection_type = 'close'
        elif connection_header == 'keep-alive':
            connection_type = 'keep-alive'
        else:
            # Default behavior
            connection_type = 'keep-alive' if version == 'HTTP/1.1' else 'close'
        
        # Route based on method
        if method == 'GET':
            response = self.handle_get(path, thread_name, connection_type)
        elif method == 'POST':
            response = self.handle_post(request, thread_name, connection_type)
        else:
            # Method not allowed
            response = self.build_error_response(405, "Method Not Allowed", 
                                                "Only GET and POST methods are supported",
                                                connection_type)
        
        return response, connection_type
    
    def validate_path(self, path):
        """
        Validate request path to prevent directory traversal attacks.
        Returns True if path is safe, False otherwise.
        """
        # Decode URL encoding
        decoded_path = unquote(path)
        
        # Check for suspicious patterns
        dangerous_patterns = ['..', './', '\\', '//', '\\\\']
        for pattern in dangerous_patterns:
            if pattern in decoded_path:
                return False
        
        # Check for absolute paths
        if decoded_path.startswith('/') and len(decoded_path) > 1:
            # Remove leading slash for further validation
            test_path = decoded_path[1:]
        else:
            test_path = decoded_path
        
        # Ensure path doesn't escape resources directory
        try:
            # Construct full path
            if decoded_path == '/' or decoded_path == '':
                return True
            
            full_path = os.path.join(self.resources_dir, test_path.lstrip('/'))
            canonical_path = os.path.abspath(full_path)
            resources_path = os.path.abspath(self.resources_dir)
            
            # Ensure the canonical path starts with resources directory
            return canonical_path.startswith(resources_path)
        except:
            return False
    
    def handle_get(self, path, thread_name, connection_type):
        """Handle GET requests for serving files."""
        # Handle root path
        if path == '/' or path == '':
            path = '/index.html'
        
        # Remove leading slash and construct file path
        file_path = os.path.join(self.resources_dir, path.lstrip('/'))
        
        # Check if file exists
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return self.build_error_response(404, "Not Found", 
                                            f"The requested resource {path} was not found",
                                            connection_type)
        
        # Get file extension
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        # Determine content type and transfer mode
        if ext == '.html':
            content_type = 'text/html; charset=utf-8'
            is_binary = False
        elif ext in ['.txt', '.png', '.jpg', '.jpeg']:
            content_type = 'application/octet-stream'
            is_binary = True
        else:
            return self.build_error_response(415, "Unsupported Media Type",
                                            f"File type {ext} is not supported",
                                            connection_type)
        
        # Read file
        try:
            if is_binary:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                file_size = len(file_content)
                filename = os.path.basename(file_path)
                
                log(f"[{thread_name}] Sending binary file: {filename} ({file_size} bytes)")
                
                # Build response with binary content
                response = self.build_binary_response(file_content, filename, connection_type)
                log(f"[{thread_name}] Response: 200 OK ({file_size} bytes transferred)")
                
                return response
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                
                file_size = len(file_content.encode('utf-8'))
                
                log(f"[{thread_name}] Sending HTML file: {os.path.basename(file_path)} ({file_size} bytes)")
                
                # Build HTML response
                response = self.build_response(200, "OK", file_content, content_type, connection_type)
                log(f"[{thread_name}] Response: 200 OK ({file_size} bytes transferred)")
                
                return response
        
        except Exception as e:
            log(f"[{thread_name}] Error reading file: {e}")
            return self.build_error_response(500, "Internal Server Error",
                                            "Error reading file",
                                            connection_type)
    
    def handle_post(self, request, thread_name, connection_type):
        """Handle POST requests for JSON file uploads."""
        headers = request['headers']
        body = request['body']
        
        # Check Content-Type
        content_type = headers.get('content-type', '')
        if 'application/json' not in content_type:
            log(f"[{thread_name}] Invalid Content-Type for POST: {content_type}")
            return self.build_error_response(415, "Unsupported Media Type",
                                            "Only application/json is supported for POST requests",
                                            connection_type)
        
        # Parse JSON
        try:
            json_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            log(f"[{thread_name}] Invalid JSON: {e}")
            return self.build_error_response(400, "Bad Request",
                                            "Invalid JSON data",
                                            connection_type)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:4]
        filename = f"upload_{timestamp}_{random_id}.json"
        filepath = os.path.join(self.uploads_dir, filename)
        
        # Save JSON to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2)
            
            # Build success response
            response_data = {
                "status": "success",
                "message": "File created successfully",
                "filepath": f"/uploads/{filename}"
            }
            
            log(f"[{thread_name}] JSON file created: {filename}")
            log(f"[{thread_name}] Response: 201 Created")
            
            response_json = json.dumps(response_data, indent=2)
            return self.build_response(201, "Created", response_json, 
                                      'application/json', connection_type)
        
        except Exception as e:
            log(f"[{thread_name}] Error saving file: {e}")
            return self.build_error_response(500, "Internal Server Error",
                                            "Error saving file",
                                            connection_type)
    
    def build_response(self, status_code, status_text, body, content_type, connection_type='close'):
        """Build HTTP response with text body."""
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body
        
        response_lines = [
            f"HTTP/1.1 {status_code} {status_text}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body_bytes)}",
            f"Date: {get_http_date()}",
            "Server: Multi-threaded HTTP Server",
            f"Connection: {connection_type}"
        ]
        
        if connection_type == 'keep-alive':
            response_lines.append(f"Keep-Alive: timeout={self.keep_alive_timeout}, max={self.max_requests_per_connection}")
        
        response_lines.append("")
        response_lines.append("")
        
        response_header = "\r\n".join(response_lines).encode('utf-8')
        return response_header + body_bytes
    
    def build_binary_response(self, binary_data, filename, connection_type='close'):
        """Build HTTP response for binary file transfer."""
        response_lines = [
            "HTTP/1.1 200 OK",
            "Content-Type: application/octet-stream",
            f"Content-Length: {len(binary_data)}",
            f'Content-Disposition: attachment; filename="{filename}"',
            f"Date: {get_http_date()}",
            "Server: Multi-threaded HTTP Server",
            f"Connection: {connection_type}"
        ]
        
        if connection_type == 'keep-alive':
            response_lines.append(f"Keep-Alive: timeout={self.keep_alive_timeout}, max={self.max_requests_per_connection}")
        
        response_lines.append("")
        response_lines.append("")
        
        response_header = "\r\n".join(response_lines).encode('utf-8')
        return response_header + binary_data
    
    def build_error_response(self, status_code, status_text, message="", connection_type='close'):
        """Build HTTP error response."""
        body = f"""<!DOCTYPE html>
<html>
<head>
    <title>{status_code} {status_text}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 50px; }}
        h1 {{ color: #d32f2f; }}
        p {{ color: #666; }}
    </style>
</head>
<body>
    <h1>{status_code} {status_text}</h1>
    <p>{message}</p>
    <hr>
    <p><em>Multi-threaded HTTP Server</em></p>
</body>
</html>"""
        
        response_lines = [
            f"HTTP/1.1 {status_code} {status_text}",
            "Content-Type: text/html; charset=utf-8",
            f"Content-Length: {len(body.encode('utf-8'))}",
            f"Date: {get_http_date()}",
            "Server: Multi-threaded HTTP Server",
            f"Connection: {connection_type}"
        ]
        
        if status_code == 503:
            response_lines.append("Retry-After: 30")
        
        response_lines.append("")
        response_lines.append("")
        
        response_header = "\r\n".join(response_lines)
        return (response_header + body).encode('utf-8')


def log(message):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_http_date():
    """Get current date in RFC 7231 format."""
    from email.utils import formatdate
    return formatdate(timeval=None, localtime=False, usegmt=True)


def main():
    """Main entry point for the HTTP server."""
    # Parse command-line arguments
    host = '127.0.0.1'
    port = 8080
    max_threads = 10
    
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Error: Port must be a number")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        host = sys.argv[2]
    
    if len(sys.argv) > 3:
        try:
            max_threads = int(sys.argv[3])
        except ValueError:
            print("Error: Max threads must be a number")
            sys.exit(1)
    
    # Create and start server
    server = HTTPServer(host=host, port=port, max_threads=max_threads)
    server.start()


if __name__ == "__main__":
    main()

