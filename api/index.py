"""
Vercel serverless function handler for Flask app
"""
import sys
import os
import io
import traceback

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize Flask app with error handling
app = None
try:
    from app import app as flask_app
    app = flask_app
except Exception as e:
    # Store error for later use
    import_error = f"Import error: {str(e)}\n{traceback.format_exc()}"

# Vercel Python runtime expects a handler function
def handler(request):
    global app
    
    # If app failed to import, return error
    if app is None:
        try:
            from app import app as flask_app
            app = flask_app
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'text/plain; charset=utf-8'},
                'body': f'Failed to import Flask app: {str(e)}\n\nTraceback:\n{traceback.format_exc()}'
            }
    
    try:
        # Get request attributes - handle different formats
        if hasattr(request, 'method'):
            method = request.method
        elif isinstance(request, dict):
            method = request.get('method', 'GET')
        else:
            method = 'GET'
        
        if hasattr(request, 'path'):
            path = request.path
        elif isinstance(request, dict):
            path = request.get('path', '/')
        elif hasattr(request, 'url'):
            from urllib.parse import urlparse
            parsed = urlparse(request.url)
            path = parsed.path
        else:
            path = '/'
        
        # Extract query string
        if hasattr(request, 'query_string'):
            query_string = request.query_string
        elif isinstance(request, dict):
            query_string = request.get('query_string', '')
        elif '?' in path:
            path, query_string = path.split('?', 1)
        else:
            query_string = ''
        
        # Get headers
        if hasattr(request, 'headers'):
            headers = request.headers
            if not isinstance(headers, dict):
                headers = dict(headers) if headers else {}
        elif isinstance(request, dict):
            headers = request.get('headers', {})
        else:
            headers = {}
        
        # Get body
        if hasattr(request, 'body'):
            body = request.body
        elif isinstance(request, dict):
            body = request.get('body', b'')
        else:
            body = b''
        
        # Convert body to bytes if needed
        if isinstance(body, str):
            body = body.encode('utf-8')
        
        # Get host
        host = headers.get('host', headers.get('Host', 'localhost:443'))
        if ':' in str(host):
            server_name, server_port = str(host).split(':', 1)
        else:
            server_name = str(host)
            server_port = '443'
        
        # Build WSGI environ
        environ = {
            'REQUEST_METHOD': method,
            'SCRIPT_NAME': '',
            'PATH_INFO': path,
            'QUERY_STRING': query_string,
            'CONTENT_TYPE': headers.get('content-type', headers.get('Content-Type', '')),
            'CONTENT_LENGTH': str(len(body)),
            'SERVER_NAME': server_name,
            'SERVER_PORT': server_port,
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https',
            'wsgi.input': io.BytesIO(body) if body else io.BytesIO(),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': True,
            'wsgi.run_once': False,
        }
        
        # Add HTTP headers
        for key, value in headers.items():
            if key.lower() not in ('content-type', 'content-length', 'host'):
                http_key = 'HTTP_' + key.upper().replace('-', '_')
                environ[http_key] = str(value)
        
        # Response storage
        response_headers = []
        status_code = ['200 OK']
        
        def start_response(status, headers_list):
            status_code[0] = status
            response_headers[:] = headers_list
        
        # Call Flask app
        response = app(environ, start_response)
        
        # Collect response body
        body_parts = []
        try:
            for part in response:
                if isinstance(part, bytes):
                    body_parts.append(part)
                elif isinstance(part, str):
                    body_parts.append(part.encode('utf-8'))
                else:
                    body_parts.append(str(part).encode('utf-8'))
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'text/plain; charset=utf-8'},
                'body': f'Error collecting response: {str(e)}\n{traceback.format_exc()}'
            }
        
        # Decode body
        try:
            body_str = b''.join(body_parts).decode('utf-8')
        except UnicodeDecodeError:
            body_str = b''.join(body_parts).decode('utf-8', errors='replace')
        
        # Parse status code
        try:
            status_num = int(status_code[0].split()[0])
        except (ValueError, IndexError):
            status_num = 200
        
        # Convert headers to dict
        headers_dict = {}
        for k, v in response_headers:
            headers_dict[k] = v
        
        # Ensure Content-Type is set
        if 'Content-Type' not in headers_dict and 'content-type' not in headers_dict:
            headers_dict['Content-Type'] = 'text/html; charset=utf-8'
        
        return {
            'statusCode': status_num,
            'headers': headers_dict,
            'body': body_str
        }
        
    except Exception as e:
        # Return detailed error
        error_msg = f'Handler error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}'
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain; charset=utf-8'},
            'body': error_msg
        }
