var socket;
var isConnected = false;

function initWebSocket() {
    socket = io({
        transports: ['websocket', 'polling']
    });
    
    socket.on('connect', function() {
        console.log('WebSocket connected');
        isConnected = true;
    });
    
    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        isConnected = false;
    });
    
    socket.on('process_output', function(data) {
        console.log('Received output:', data);
        // Add visual indicator that message was received
        document.title = '* StockX Tools - New Output';
        setTimeout(function() {
            document.title = 'StockX Tools - Web Interface';
        }, 1000);
        
        // Check if this is a test message and create a special handler
        if (data.script_id === 'websocket_test') {
            console.log('Test message received, creating test container');
            var testContainer = document.getElementById('test-output');
            if (!testContainer) {
                testContainer = document.createElement('div');
                testContainer.id = 'test-output';
                testContainer.innerHTML = '<h3>WebSocket Test Output</h3><pre style="background: #e8f5e8; padding: 10px; border: 1px solid #28a745;"></pre>';
                document.body.appendChild(testContainer);
            }
            var testPre = testContainer.querySelector('pre');
            if (testPre) {
                testPre.textContent += data.line + '\n';
            }
        }
        
        addOutputLine(data.script_id, data.line);
    });
    
    socket.on('process_status', function(data) {
        updateRunningProcesses(data.running_processes);
    });
}

function addOutputLine(scriptId, line) {
    console.log('Adding line for:', scriptId, line);
    
    // Try to find existing container first
    var outputContainer = document.getElementById('output-' + scriptId);
    console.log('Output container found:', outputContainer);
    
    if (!outputContainer) {
        console.log('Creating new container for:', scriptId);
        createOutputContainer(scriptId);
        outputContainer = document.getElementById('output-' + scriptId);
    }
    
    if (!outputContainer) {
        console.error('Failed to create/find output container for:', scriptId);
        // Create emergency container in recent-activity if it exists
        var recentActivity = document.getElementById('recent-activity');
        if (recentActivity) {
            var emergencyDiv = document.createElement('div');
            emergencyDiv.id = 'output-' + scriptId;
            emergencyDiv.innerHTML = '<h3>' + scriptId + ' (WebSocket Stream)</h3><pre style="background: #f5f5f5; padding: 10px; max-height: 300px; overflow-y: auto; border: 1px solid #ddd;"></pre>';
            recentActivity.appendChild(emergencyDiv);
            outputContainer = emergencyDiv;
        } else {
            return;
        }
    }
    
    var pre = outputContainer.querySelector('pre');
    if (pre) {
        // Use textContent for better performance and avoid HTML escaping
        var existingContent = pre.textContent || '';
        pre.textContent = existingContent + line + '\n';
        pre.scrollTop = pre.scrollHeight;
        console.log('Added line to existing pre via textContent, new length:', pre.textContent.length);
        
        // Add visual feedback that content was added
        pre.style.borderLeft = '4px solid #28a745';
        setTimeout(function() {
            pre.style.borderLeft = '1px solid #ddd';
        }, 500);
    } else {
        console.log('Creating new pre element in container');
        var newPre = document.createElement('pre');
        newPre.style.background = '#f5f5f5';
        newPre.style.padding = '10px';
        newPre.style.maxHeight = '300px';
        newPre.style.overflowY = 'auto';
        newPre.style.border = '1px solid #ddd';
        newPre.style.borderRadius = '4px';
        newPre.style.whiteSpace = 'pre-wrap';
        newPre.textContent = line + '\n';
        outputContainer.appendChild(newPre);
        console.log('Created new pre element');
    }
}

function createOutputContainer(scriptId) {
    var container = document.getElementById('recent-activity');
    console.log('Container found:', container);
    if (!container) {
        console.error('recent-activity container not found!');
        return;
    }
    
    // Check if container already exists (from server-side rendering)
    var existingContainer = document.getElementById('output-' + scriptId);
    if (existingContainer) {
        console.log('Container already exists for:', scriptId);
        return;
    }
    
    var div = document.createElement('div');
    var timestamp = new Date().toLocaleString();
    div.innerHTML = '<h3>' + scriptId + ' - ' + timestamp + '</h3><div id="output-' + scriptId + '"><pre style="background: #f5f5f5; padding: 10px; max-height: 300px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap;"></pre></div><hr>';
    container.appendChild(div);
    console.log('Created container for:', scriptId);
}

function updateRunningProcesses(processes) {
    var section = document.querySelector('.running-processes');
    if (!section) return;
    
    var html = '<h2>🔄 Running Processes</h2>';
    if (processes.length > 0) {
        for (var i = 0; i < processes.length; i++) {
            html += '<div style="margin: 10px 0; padding: 10px; border: 1px solid #ddd; background: #f9f9f9;">';
            html += '<span class="running-indicator">⏳ ' + processes[i] + ' is running...</span>';
            html += '<button onclick="stopProcess(\'' + processes[i] + '\')" style="margin-left: 10px; background: #dc3545; color: white; border: none; padding: 4px 8px; cursor: pointer;">Stop Process</button>';
            html += '</div>';
        }
        html += '<p><small>Real-time streaming updates via WebSocket</small></p>';
    } else {
        html += '<p>No scripts currently running</p>';
        html += '<p><small>Real-time streaming updates via WebSocket</small></p>';
    }
    section.innerHTML = html;
}

function stopProcess(scriptId) {
    if (confirm('Stop process: ' + scriptId + '?')) {
        // Disable the button to prevent multiple clicks
        var button = event.target;
        button.disabled = true;
        button.textContent = 'Stopping...';
        
        fetch('/stop_process/' + scriptId, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.success) {
                // Process stopped successfully, the WebSocket will update the UI
                console.log('Process stopped successfully');
            } else {
                alert('Failed to stop process: ' + data.message);
                // Re-enable button on failure
                button.disabled = false;
                button.textContent = 'Stop Process';
            }
        })
        .catch(function(error) {
            alert('Error stopping process: ' + error);
            // Re-enable button on error
            button.disabled = false;
            button.textContent = 'Stop Process';
        });
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    initWebSocket();
});