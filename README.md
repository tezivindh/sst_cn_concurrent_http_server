# Multi-threaded HTTP Server

A comprehensive HTTP server implementation built from scratch using low-level socket programming in Python. This project demonstrates advanced networking concepts, concurrent programming with thread pools, binary file transfers, and security best practices.

## 🚀 Quick Start

```bash
# Start the server
python server.py

# Open in browser
http://localhost:8080/
```

## 📋 Features

- ✅ **Multi-threaded Architecture** - Thread pool with configurable workers (default: 10)
- ✅ **HTTP/1.1 Protocol** - Full implementation with persistent connections
- ✅ **Binary File Transfer** - Efficient serving of images (PNG, JPEG) and text files
- ✅ **JSON API** - POST endpoint for uploading and storing JSON data
- ✅ **Security Features** - Path traversal protection and host header validation
- ✅ **Connection Management** - Keep-alive support with timeout and request limits
- ✅ **Comprehensive Logging** - Detailed request/response tracking with timestamps

## 🏗️ Architecture

### Thread Pool Implementation

```
TCP Socket Listener (Queue: 50)
        ↓
Thread Pool Manager (Size: 10)
        ↓
    Worker Threads
    Thread-1 ... Thread-10
```

### Request Processing Flow

```
Client Request
    ↓
Parse HTTP Request
    ↓
Validate Host Header & Path
    ↓
Route by Method (GET/POST)
    ↓
Build & Send Response
```

## 💻 Usage

### Starting the Server

**Default** (localhost:8080, 10 threads):

```bash
python server.py
```

**Custom port**:

```bash
python server.py 8000
```

**Custom port and host**:

```bash
python server.py 8000 0.0.0.0
```

**Full customization** (port, host, threads):

```bash
python server.py 8000 0.0.0.0 20
```

### Access the Server

Open your browser and navigate to:

- `http://localhost:8080/` - Home page
- `http://localhost:8080/about.html` - About page
- `http://localhost:8080/contact.html` - Contact page

## 🧪 Testing

### HTML File Serving

```bash
curl http://localhost:8080/
curl http://localhost:8080/about.html
```

### Binary File Downloads

```bash
# Download PNG image
curl -O http://localhost:8080/logo.png

# Download JPEG image
curl -O http://localhost:8080/photo.jpg

# Download text file
curl -O http://localhost:8080/sample.txt
```

### JSON Upload (POST)

```bash
curl -X POST http://localhost:8080/upload \
  -H "Content-Type: application/json" \
  -H "Host: localhost:8080" \
  -d '{
    "name": "Test Upload",
    "timestamp": "2024-10-10T23:45:00",
    "data": [1, 2, 3, 4, 5]
  }'
```

**Expected Response** (201 Created):

```json
{
  "status": "success",
  "message": "File created successfully",
  "filepath": "/uploads/upload_20241010_234500_a7b9.json"
}
```

### Security Tests

**Path Traversal** (should return 403):

```bash
curl http://localhost:8080/../etc/passwd
curl http://localhost:8080/../../config
```

**Host Header Validation** (should return 400/403):

```bash
# Missing Host header
curl -H "Host:" http://localhost:8080/

# Invalid Host header
curl -H "Host: evil.com" http://localhost:8080/
```

**Method Validation** (should return 405):

```bash
curl -X PUT http://localhost:8080/index.html
curl -X DELETE http://localhost:8080/index.html
```

## 🔒 Security Features

### 1. Path Traversal Protection

- Blocks `..`, `./`, `//`, `\` patterns
- Canonical path resolution
- Directory boundary checks

**Blocked Examples:**

- `/../etc/passwd`
- `/../../config`
- `//etc/hosts`

### 2. Host Header Validation

- Validates all incoming requests
- Only accepts matching host headers
- Returns 400 for missing, 403 for mismatch

**Valid Host Headers:**

- `localhost:8080`
- `127.0.0.1:8080`

### 3. Input Validation

- Request size limit: 8192 bytes
- JSON validation with error handling
- Strict Content-Type checking
- File type validation

## 📚 API Documentation

### GET Requests

**Serve HTML File:**

```http
GET /index.html HTTP/1.1
Host: localhost:8080

Response: 200 OK
Content-Type: text/html; charset=utf-8
```

**Download Binary File:**

```http
GET /logo.png HTTP/1.1
Host: localhost:8080

Response: 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="logo.png"
```

### POST Requests

**Upload JSON:**

```http
POST /upload HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "name": "Test",
  "data": [1, 2, 3]
}

Response: 201 Created
Content-Type: application/json
```

### Error Responses

| Code | Status                 | Description                               |
| ---- | ---------------------- | ----------------------------------------- |
| 400  | Bad Request            | Malformed request or missing Host header  |
| 403  | Forbidden              | Unauthorized path access or Host mismatch |
| 404  | Not Found              | Resource doesn't exist                    |
| 405  | Method Not Allowed     | Non-GET/POST methods                      |
| 415  | Unsupported Media Type | Wrong Content-Type or file type           |
| 500  | Internal Server Error  | Server-side errors                        |

## ⚡ Performance

### Specifications

- **Concurrent Connections**: 10 (configurable)
- **Connection Queue**: 50 pending connections
- **Request Size Limit**: 8192 bytes
- **Keep-Alive Timeout**: 30 seconds
- **Max Requests per Connection**: 100

## 📁 Project Structure

```
sst_cn_concurrent_http_server/
│
├── server.py                    # Main HTTP server (800+ lines)
├── README.md                    # Documentation
├── .gitignore                   # Git ignore file
│
└── resources/                   # Served files
    ├── index.html               # Home page
    ├── about.html               # About page
    ├── contact.html             # Contact page
    ├── sample.txt               # Test text file
    ├── document.txt             # Documentation text
    ├── logo.png                 # PNG image (9.4 MB)
    ├── photo.png                # PNG image (27 MB)
    ├── logo.jpg                 # JPEG image (3.3 MB)
    ├── photo.jpg                # JPEG image (4.6 MB)
    └── uploads/                 # JSON uploads directory
```

## 🔧 Implementation Details

### Key Components

**ThreadPool Class:**

- Manages worker threads
- Connection queue handling
- Thread synchronization with locks

**HTTPServer Class:**

- Socket setup and lifecycle
- Request parsing
- GET/POST request handlers
- Security validation
- Response builders

### Thread Safety

- Mutex locks for shared resources
- Thread-safe queue for connections
- Proper synchronization

### HTTP Protocol

- Complete request parsing
- RFC 7231 compliant dates
- Accurate Content-Length headers
- Comprehensive status codes

## 📝 Requirements

### Assignment Requirements Met

✅ **Server Configuration:**

- Runs on localhost (127.0.0.1) by default
- Default port 8080
- Command-line arguments for port, host, thread pool size

✅ **Socket Implementation:**

- TCP sockets
- Listen queue size: 50
- Proper socket lifecycle management

✅ **Multi-threading:**

- Thread pool (default: 10 threads)
- Connection queue
- Proper synchronization

✅ **HTTP Handling:**

- GET and POST methods
- Request parsing (method, path, version, headers)
- Returns 405 for other methods

✅ **GET Implementation:**

- Serves HTML files (text/html)
- Binary file transfer (images, text)
- Content-Disposition headers
- Supports .html, .txt, .png, .jpg, .jpeg

✅ **POST Implementation:**

- Accepts application/json
- Creates files in uploads/
- Returns 201 Created with JSON response

✅ **Security:**

- Path traversal protection
- Host header validation
- Security violation logging

✅ **Connection Management:**

- Keep-alive support
- 30-second timeout
- Max 100 requests per connection

✅ **Logging:**

- Timestamps on all logs
- Server startup logging
- Request/response logging
- Thread pool status logging

## 🚧 Known Limitations

1. **No HTTPS Support** - Educational server without SSL/TLS
2. **Single Process** - Uses threading (GIL limitations apply)
3. **Memory Buffering** - Entire files loaded into memory
4. **Limited HTTP Features** - Only GET and POST methods
5. **No Compression** - Does not support gzip
6. **No Caching** - No ETag or Last-Modified headers
7. **IPv4 Only** - No IPv6 support

## 👨‍💻 Author

Created as part of SST Computer Networks Assignment

## 📄 License

This project is for educational purposes.

---

**Note:** This server is for educational purposes and should not be used in production. For production use, consider Apache, Nginx, or frameworks like Flask/Django with proper WSGI servers.
