"""
Vercel serverless function handler for Flask app
Minimal implementation to avoid Vercel runtime inspection issues
"""
import sys
import os
import io
import traceback
from urllib.parse import urlparse

# Set Vercel environment BEFORE any other imports
os.environ['VERCEL'] = '1'
os.environ['VERCEL_ENV'] = 'production'

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Don't import app at module level - import only in handler
# This avoids Vercel's runtime inspection issues

def handler(request):
    """Vercel Python runtime handler"""
    try:
        # Import app only when handler is called
        # Use importlib to avoid static inspection issues
        import importlib
        import importlib.util
        
        # Try to import app dynamically
        try:
            from app import app as flask_app
        except Exception as import_error:
            # If import fails due to Vercel inspection, try alternative approach
            error_str = str(import_error)
            if 'BaseHTTPRequestHandler' in error_str or 'issubclass' in error_str:
                # Try to import without problematic modules
                import sys
                # Remove problematic modules from sys.modules if they exist
                modules_to_remove = [k for k in sys.modules.keys() if 'http.server' in k or 'smart_stockx' in k or 'auto_auth' in k]
                for mod in modules_to_remove:
                    if mod in sys.modules:
                        del sys.modules[mod]
                
                # Try importing again
                from app import app as flask_app
            else:
                raise
        
        # Get request data
        if hasattr(request, 'method'):
            method = request.method
            url = getattr(request, 'url', getattr(request, 'path', '/'))
            headers = getattr(request, 'headers', {})
            body = getattr(request, 'body', b'')
        elif isinstance(request, dict):
            method = request.get('method', 'GET')
            url = request.get('url', request.get('path', '/'))
            headers = request.get('headers', {})
            body = request.get('body', b'')
        else:
            method = 'GET'
            url = '/'
            headers = {}
            body = b''
        
        # Parse URL
        parsed = urlparse(url if url.startswith('http') else f'https://example.com{url}')
        path = parsed.path or '/'
        query_string = parsed.query or ''
        
        # Convert body to bytes
        if isinstance(body, str):
            body = body.encode('utf-8')
        elif body is None:
            body = b''
        
        # Get host
        host = headers.get('host') or headers.get('Host') or 'localhost'
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
            'CONTENT_TYPE': headers.get('content-type') or headers.get('Content-Type') or '',
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
            key_lower = key.lower()
            if key_lower not in ('content-type', 'content-length', 'host'):
                http_key = 'HTTP_' + key.upper().replace('-', '_')
                environ[http_key] = str(value)
        
        # Response storage
        response_headers = []
        status_code = ['200 OK']
        
        def start_response(status, headers_list):
            status_code[0] = status
            response_headers[:] = headers_list
        
        # Call Flask app
        response = flask_app(environ, start_response)
        
        # Collect response
        body_parts = []
        for part in response:
            if isinstance(part, bytes):
                body_parts.append(part)
            elif isinstance(part, str):
                body_parts.append(part.encode('utf-8'))
            else:
                body_parts.append(str(part).encode('utf-8'))
        
        # Decode body
        try:
            body_str = b''.join(body_parts).decode('utf-8')
        except UnicodeDecodeError:
            body_str = b''.join(body_parts).decode('utf-8', errors='replace')
        
        # Parse status
        try:
            status_num = int(status_code[0].split()[0])
        except (ValueError, IndexError):
            status_num = 200
        
        # Convert headers
        headers_dict = {}
        for k, v in response_headers:
            headers_dict[k] = v
        
        if 'Content-Type' not in headers_dict:
            headers_dict['Content-Type'] = 'text/html; charset=utf-8'
        
        return {
            'statusCode': status_num,
            'headers': headers_dict,
            'body': body_str
        }
        
    except Exception as e:
        error_trace = traceback.format_exc()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain; charset=utf-8'},
            'body': f'Error: {str(e)}\n\n{error_trace}'
        }
