var socket;
var isConnected = false;

function initWebSocket() {
    socket = io();
    
    socket.on('connect', function() {
        console.log('WebSocket connected');
        isConnected = true;
    });
    
    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        isConnected = false;
    });
    
    socket.on('process_output', function(data) {
        addOutputLine(data.script_id, data.line);
    });
    
    socket.on('process_status', function(data) {
        updateRunningProcesses(data.running_processes);
    });
}

function addOutputLine(scriptId, line) {
    var outputContainer = document.getElementById('output-' + scriptId);
    if (!outputContainer) {
        createOutputContainer(scriptId);
        outputContainer = document.getElementById('output-' + scriptId);
    }
    
    var pre = outputContainer.querySelector('pre');
    if (pre) {
        pre.textContent = pre.textContent + line + '\n';
        pre.scrollTop = pre.scrollHeight;
    } else {
        // Fallback: create the pre element if it doesn't exist
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
    }
}

function createOutputContainer(scriptId) {
    var container = document.getElementById('recent-activity');
    if (!container) return;
    
    var div = document.createElement('div');
    var timestamp = new Date().toLocaleString();
    div.innerHTML = '<h3>' + scriptId + ' - ' + timestamp + '</h3><div id="output-' + scriptId + '"><pre style="background: #f5f5f5; padding: 10px; max-height: 300px; overflow-y: auto; border: 1px solid #ddd;"></pre></div><hr>';
    container.appendChild(div);
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