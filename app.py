
#!/usr/bin/env python3
"""
🌐 Minimal Flask Web UI for StockX Tools
Run any script from the web interface
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import subprocess
import threading
import os
import sys
from datetime import datetime

app = Flask(__name__)

# Store running processes and their outputs
running_processes = {}
process_outputs = {}

def run_script_async(script_id, command, working_dir=None):
    """Run script asynchronously and capture output"""
    try:
        if working_dir:
            os.chdir(working_dir)
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        running_processes[script_id] = process
        process_outputs[script_id] = []
        
        # Read output line by line
        for line in iter(process.stdout.readline, ''):
            if line:
                process_outputs[script_id].append(line.rstrip())
        
        # Wait for process to complete
        process.wait()
        
        # Add completion message
        if process.returncode == 0:
            process_outputs[script_id].append(f"\n✅ Script completed successfully (exit code: {process.returncode})")
        else:
            process_outputs[script_id].append(f"\n❌ Script failed (exit code: {process.returncode})")
        
        # Remove from running processes
        if script_id in running_processes:
            del running_processes[script_id]
            
    except Exception as e:
        process_outputs[script_id] = [f"❌ Error running script: {str(e)}"]
        if script_id in running_processes:
            del running_processes[script_id]

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>StockX Tools - Web Interface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <h1>🤖 StockX Tools - Web Interface</h1>
    <p>Run any script from your StockX project</p>
    <hr>
    
    <h2>📊 Available Scripts</h2>
    
    <h3>🔐 Authentication</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="auth">
        <input type="submit" value="Run Authentication System" style="padding: 5px 10px;">
        <p>Authenticate with StockX API (required first)</p>
    </form>
    
    <h3>📝 Examples & Testing</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="examples">
        <input type="submit" value="Run Examples" style="padding: 5px 10px;">
        <p>Test API with example searches</p>
    </form>
    
    <h3>💰 eBay Tools</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="ebay">
        <label for="ebay_file">CSV File (in ebay_tools/ directory):</label><br>
        <input type="text" name="file" id="ebay_file" placeholder="example.csv" style="width: 300px; margin: 5px 0;"><br>
        <input type="submit" value="Run eBay Price Analysis" style="padding: 5px 10px;">
        <p>Compare eBay auction data with StockX prices</p>
    </form>
    
    <h3>📊 Inventory Analysis</h3>
    <form action="/run" method="post" style="margin: 10px 0;">
        <input type="hidden" name="script" value="inventory">
        <label for="inventory_file">CSV File (in pricing_tools/ directory):</label><br>
        <input type="text" name="file" id="inventory_file" placeholder="inventory.csv" style="width: 300px; margin: 5px 0;"><br>
        <input type="submit" value="Run Inventory Analysis" style="padding: 5px 10px;">
        <p>Analyze inventory CSV against StockX market data</p>
    </form>
    
    <hr>
    
    <h2>🔄 Running Processes</h2>
    {% if running_processes %}
        {% for script_id in running_processes %}
            <p>⏳ {{ script_id }} is running...</p>
        {% endfor %}
    {% else %}
        <p>No scripts currently running</p>
    {% endif %}
    
    <h2>📋 Recent Outputs</h2>
    <form action="/clear" method="post" style="margin: 10px 0;">
        <input type="submit" value="Clear All Outputs" style="padding: 5px 10px;">
    </form>
    
    {% for script_id, output in outputs %}
        <h3>{{ script_id }} - {{ output.timestamp }}</h3>
        <pre style="background: #f5f5f5; padding: 10px; border: 1px solid #ddd; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">{{ output.content }}</pre>
        <hr>
    {% endfor %}
    
    {% if not outputs %}
        <p>No script outputs yet</p>
    {% endif %}
    
    <script>
        // Auto-refresh every 5 seconds to show live updates
        setTimeout(function() {
            window.location.reload();
        }, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page with script options"""
    # Prepare outputs for display
    outputs = []
    for script_id, lines in process_outputs.items():
        if lines:
            outputs.append({
                'script_id': script_id,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'content': '\n'.join(lines[-100:])  # Last 100 lines
            })
    
    # Sort by most recent first
    outputs = [(item['script_id'], item) for item in outputs]
    outputs.reverse()
    
    return render_template_string(
        HTML_TEMPLATE,
        running_processes=running_processes.keys(),
        outputs=outputs
    )

@app.route('/run', methods=['POST'])
def run_script():
    """Run selected script"""
    script = request.form.get('script')
    file_param = request.form.get('file', '').strip()
    
    if not script:
        return redirect(url_for('index'))
    
    # Generate script ID with timestamp
    script_id = f"{script}_{datetime.now().strftime('%H%M%S')}"
    
    # Define script commands
    if script == 'auth':
        command = 'python3 auto_auth_system.py'
        working_dir = None
        
    elif script == 'examples':
        command = 'python3 example.py'
        working_dir = None
        
    elif script == 'ebay':
        if not file_param:
            process_outputs[script_id] = ['❌ Error: Please specify a CSV file']
            return redirect(url_for('index'))
        command = f'python3 ebay_stockxpricing.py "{file_param}"'
        working_dir = 'ebay_tools'
        
    elif script == 'inventory':
        if not file_param:
            process_outputs[script_id] = ['❌ Error: Please specify a CSV file']
            return redirect(url_for('index'))
        command = f'python3 inventory_stockx_analyzer.py "{file_param}"'
        working_dir = 'pricing_tools'
        
    else:
        process_outputs[script_id] = ['❌ Error: Unknown script']
        return redirect(url_for('index'))
    
    # Start script in background thread
    thread = threading.Thread(
        target=run_script_async,
        args=(script_id, command, working_dir)
    )
    thread.daemon = True
    thread.start()
    
    # Initialize output
    process_outputs[script_id] = [f"🚀 Starting {script}...", f"Command: {command}"]
    if working_dir:
        process_outputs[script_id].append(f"Working directory: {working_dir}")
    process_outputs[script_id].append("")
    
    return redirect(url_for('index'))

@app.route('/clear', methods=['POST'])
def clear_outputs():
    """Clear all process outputs"""
    global process_outputs
    process_outputs = {}
    return redirect(url_for('index'))

@app.route('/status')
def status():
    """API endpoint for status (JSON)"""
    return jsonify({
        'running_processes': list(running_processes.keys()),
        'completed_processes': list(process_outputs.keys())
    })

if __name__ == '__main__':
    print("🌐 Starting StockX Tools Web Interface...")
    print("📱 Access at: http://0.0.0.0:5000")
    print("🔄 Page auto-refreshes every 5 seconds")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
