"""
Vercel serverless function handler for Flask app
"""
import sys
import os

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel Python runtime expects a handler function
# The handler receives a request object from Vercel
def handler(request):
    # Convert Vercel request to WSGI environ
    environ = {
        'REQUEST_METHOD': request.method,
        'SCRIPT_NAME': '',
        'PATH_INFO': request.path,
        'QUERY_STRING': request.query_string if hasattr(request, 'query_string') else '',
        'CONTENT_TYPE': request.headers.get('content-type', ''),
        'CONTENT_LENGTH': str(len(request.body)) if hasattr(request, 'body') and request.body else '0',
        'SERVER_NAME': request.headers.get('host', 'localhost').split(':')[0],
        'SERVER_PORT': request.headers.get('host', 'localhost:443').split(':')[1] if ':' in request.headers.get('host', '') else '443',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': 'https',
        'wsgi.input': None,
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': True,
        'wsgi.run_once': False,
    }
    
    # Add HTTP headers to environ
    for key, value in request.headers.items():
        key = 'HTTP_' + key.upper().replace('-', '_')
        environ[key] = value
    
    # Handle request body if present
    if hasattr(request, 'body') and request.body:
        import io
        environ['wsgi.input'] = io.BytesIO(request.body.encode() if isinstance(request.body, str) else request.body)
        environ['CONTENT_LENGTH'] = str(len(request.body))
    
    # Response storage
    response_headers = []
    status_code = ['200 OK']
    
    def start_response(status, headers):
        status_code[0] = status
        response_headers[:] = headers
    
    # Call Flask app
    response = app(environ, start_response)
    
    # Collect response body
    body_parts = []
    for part in response:
        if isinstance(part, bytes):
            body_parts.append(part)
        else:
            body_parts.append(part.encode('utf-8'))
    
    body = b''.join(body_parts).decode('utf-8')
    
    # Return Vercel-compatible response
    return {
        'statusCode': int(status_code[0].split()[0]),
        'headers': {k: v for k, v in response_headers},
        'body': body
    }

