"""
Server-Sent Events (SSE) streaming implementation as an alternative to WebSocket
"""
from flask import Response
import time
import json

def generate_sse_stream(script_id, process):
    """Generate Server-Sent Events stream for a process"""
    def generate():
        try:
            for line in iter(process.stdout.readline, b''):
                if line:
                    line = line.decode('utf-8').strip()
                    data = {
                        'script_id': script_id,
                        'line': line,
                        'status': 'running'
                    }
                    yield f"data: {json.dumps(data)}\n\n"
            
            # Process completed
            data = {
                'script_id': script_id,
                'line': '✅ Process completed',
                'status': 'completed'
            }
            yield f"data: {json.dumps(data)}\n\n"
        except Exception as e:
            data = {
                'script_id': script_id,
                'line': f'❌ Error: {str(e)}',
                'status': 'error'
            }
            yield f"data: {json.dumps(data)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')