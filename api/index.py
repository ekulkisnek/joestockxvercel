"""
Vercel serverless function handler for Flask app
"""
import sys
import os
import io
import traceback
from urllib.parse import urlparse, parse_qs

# Set Vercel environment before any imports
os.environ['VERCEL'] = '1'

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize Flask app with error handling - defer import to handler
app = None
import_error = None

# Try to import app at module level to catch import errors early
try:
    from app import app as flask_app
    app = flask_app
    print("✅ Flask app imported successfully")
except Exception as e:
    import_error = e
    error_trace = traceback.format_exc()
    print(f"❌ Failed to import Flask app at module level: {str(e)}\n{error_trace}")

# Vercel Python runtime expects a handler function
def handler(request):
    global app, import_error
    
    # If import failed at module level, return error immediately
    if import_error is not None:
        error_trace = traceback.format_exc()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain; charset=utf-8'},
            'body': f'Failed to import Flask app: {str(import_error)}\n\nTraceback:\n{error_trace}'
        }
    
    # Lazy import app only when handler is called (fallback)
    if app is None:
        try:
            from app import app as flask_app
            app = flask_app
            print("✅ Flask app imported successfully in handler")
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"❌ Failed to import Flask app in handler: {str(e)}\n{error_trace}")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'text/plain; charset=utf-8'},
                'body': f'Failed to import Flask app: {str(e)}\n\nTraceback:\n{error_trace}'
            }
    
    try:
        # Vercel Python runtime passes request as an object with specific attributes
        # Handle both object and dict formats
        if isinstance(request, dict):
            # Dict format from Vercel
            method = request.get('method', 'GET')
            url = request.get('url', '/')
            headers = request.get('headers', {})
            body = request.get('body', b'')
            
            # Parse URL
            parsed = urlparse(url)
            path = parsed.path or '/'
            query_string = parsed.query or ''
        else:
            # Object format - try to get attributes
            method = getattr(request, 'method', 'GET')
            url = getattr(request, 'url', '/')
            headers = getattr(request, 'headers', {})
            body = getattr(request, 'body', b'')
            
            # Convert headers to dict if needed
            if not isinstance(headers, dict):
                try:
                    headers = dict(headers) if headers else {}
                except:
                    headers = {}
            
            # Parse URL
            parsed = urlparse(url)
            path = parsed.path or '/'
            query_string = parsed.query or ''
        
        # Convert body to bytes if needed
        if isinstance(body, str):
            body = body.encode('utf-8')
        elif body is None:
            body = b''
        
        # Get host from headers
        host = headers.get('host') or headers.get('Host') or headers.get('x-forwarded-host') or 'localhost'
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
        
        # Add HTTP headers (convert to WSGI format)
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower not in ('content-type', 'content-length', 'host'):
                http_key = 'HTTP_' + key.upper().replace('-', '_')
                environ[http_key] = str(value)
        
        # Add common headers
        if 'x-forwarded-for' in headers:
            environ['HTTP_X_FORWARDED_FOR'] = headers['x-forwarded-for']
        if 'x-forwarded-proto' in headers:
            environ['HTTP_X_FORWARDED_PROTO'] = headers['x-forwarded-proto']
        
        # Response storage
        response_headers = []
        status_code = ['200 OK']
        
        def start_response(status, headers_list):
            status_code[0] = status
            response_headers[:] = headers_list
        
        # Call Flask app
        try:
            response = app(environ, start_response)
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"Flask app error: {str(e)}\n{error_trace}")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'text/plain; charset=utf-8'},
                'body': f'Flask app error: {str(e)}\n\nTraceback:\n{error_trace}'
            }
        
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
            error_trace = traceback.format_exc()
            print(f"Error collecting response: {str(e)}\n{error_trace}")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'text/plain; charset=utf-8'},
                'body': f'Error collecting response: {str(e)}\n{error_trace}'
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
        error_trace = traceback.format_exc()
        error_msg = f'Handler error: {str(e)}\n\nTraceback:\n{error_trace}'
        print(error_msg)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/plain; charset=utf-8'},
            'body': error_msg
        }
