// Chat.js - JavaScript Bridge for Eel
let currentRoom = 'lobby';
let currentUsername = '';
let activeUsers = [];
let allRooms = {};
let pmTargetUser = null; // Current user for private messaging

// Initialize chat when page loads
window.onload = function() {
    loadUserInfo();
    scrollToBottom();
    // Request user list after a short delay to ensure connection is established
    setTimeout(() => {
        refreshUserList();
    }, 1000);
    
    // Poll for user list every 10 seconds (less frequent since we have manual refresh)
    setInterval(() => {
        refreshUserList();
    }, 10000);
};

// Load user information
async function loadUserInfo() {
    try {
        const userInfo = await eel.get_user_info()();
        console.log('Loaded user info:', userInfo);
        if (userInfo && userInfo.username) {
            currentUsername = userInfo.username;
            currentRoom = userInfo.room;
            document.getElementById('currentUsername').textContent = currentUsername;
            document.getElementById('currentRoomName').textContent = currentRoom;
            document.getElementById('chatRoomTitle').textContent = currentRoom;
            console.log('Current username set to:', currentUsername);
        } else {
            console.error('User info not available yet, retrying...');
            // Retry after a delay
            setTimeout(loadUserInfo, 500);
        }
    } catch (error) {
        console.error('Failed to load user info:', error);
        setTimeout(loadUserInfo, 500);
    }
}

// Request user list from server
async function refreshUserList() {
    console.log('Refreshing user list...');
    try {
        await eel.send_message('/rooms')();
        // Show a brief success indicator
        const usersList = document.getElementById('usersList');
        const originalHTML = usersList.innerHTML;
        usersList.innerHTML = '<div class="no-users" style="color: var(--success-color);">🔄 Refreshing...</div>';
        setTimeout(() => {
            // If it's still showing the refreshing message, restore original
            if (usersList.innerHTML.includes('Refreshing')) {
                usersList.innerHTML = originalHTML;
            }
        }, 1000);
    } catch (error) {
        console.error('Failed to refresh user list:', error);
    }
}

// Toggle PM mode for a user
function togglePMMode(username) {
    if (pmTargetUser === username) {
        // Disable PM mode
        pmTargetUser = null;
        updatePMIndicator();
        // Refresh user list to update button states
        refreshUserList();
    } else {
        // Enable PM mode for this user
        pmTargetUser = username;
        updatePMIndicator();
        // Refresh user list to update button states
        refreshUserList();
        // Focus on message input
        document.getElementById('messageInput').focus();
    }
}

// Update PM mode indicator in the UI
function updatePMIndicator() {
    const input = document.getElementById('messageInput');
    if (pmTargetUser) {
        input.placeholder = 💬 Private message to ${pmTargetUser}... (Click PM button to disable);
        input.style.borderColor = 'var(--warning-color)';
        input.style.background = 'rgba(254, 202, 87, 0.05)';
    } else {
        input.placeholder = 'Type a message... (Use /pm username message for private chat)';
        input.style.borderColor = '';
        input.style.background = '';
    }
}

// Send message to server
async function sendMessage() {
    const input = document.getElementById('messageInput');
    let message = input.value.trim();
    
    if (!message) return;
    
    try {
        // If PM mode is active and message doesn't start with a command, prefix with /pm
        if (pmTargetUser && !message.startsWith('/')) {
            message = /pm ${pmTargetUser} ${message};
        }
        
        await eel.send_message(message)();
        input.value = '';
        input.focus();
    } catch (error) {
        console.error('Failed to send message:', error);
        displayError('Failed to send message');
    }
}

// Handle Enter key for message input
function handleMessageEnter(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

// Join a room
async function joinRoom() {
    const input = document.getElementById('newRoomInput');
    const roomName = input.value.trim();
    
    if (!roomName) {
        displayError('Please enter a room name');
        return;
    }
    
    try {
        await eel.join_room(roomName)();
        input.value = '';
    } catch (error) {
        console.error('Failed to join room:', error);
        displayError('Failed to join room');
    }
}

// Join room by clicking on room name
function joinRoomByName(roomName) {
    document.getElementById('newRoomInput').value = roomName;
    joinRoom();
}

// Handle Enter key for room input
function handleRoomInputEnter(event) {
    if (event.key === 'Enter') {
        joinRoom();
    }
}

// Refresh rooms list
async function refreshRooms() {
    try {
        await eel.request_rooms_list()();
    } catch (error) {
        console.error('Failed to refresh rooms:', error);
    }
}

// Disconnect from server
async function disconnect() {
    if (confirm('Are you sure you want to disconnect?')) {
        try {
            await eel.disconnect()();
            window.location.href = 'login.html';
        } catch (error) {
            window.location.href = 'login.html';
        }
    }
}

// Show users panel
function showUsersPanel() {
    document.getElementById('usersPanel').classList.remove('hidden');
}

// Hide users panel
function hideUsersPanel() {
    document.getElementById('usersPanel').classList.add('hidden');
}

// Display message in chat (called from Python)
eel.expose(display_message);
function display_message(messageData) {
    const container = document.getElementById('messagesContainer');
    const welcomeMsg = container.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    
    if (messageData.type === 'notification') {
        messageDiv.classList.add('notification');
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="message-text">${escapeHtml(messageData.text)}</div>
            </div>
        `;
    } else if (messageData.type === 'private') {
        messageDiv.classList.add('private');
        const sender = messageData.sender || 'Unknown';
        const initial = sender.charAt(0).toUpperCase();
        messageDiv.innerHTML = `
            <div class="message-avatar">${initial}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-sender">${escapeHtml(sender)} (Private)</span>
                    <span class="message-time">${timeStr}</span>
                </div>
                <div class="message-text">${escapeHtml(messageData.text)}</div>
            </div>
        `;
    } else {
        // Regular message
        const sender = messageData.sender || 'Unknown';
        const initial = sender.charAt(0).toUpperCase();
        messageDiv.innerHTML = `
            <div class="message-avatar">${initial}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-sender">${escapeHtml(sender)}</span>
                    <span class="message-time">${timeStr}</span>
                </div>
                <div class="message-text">${escapeHtml(messageData.text)}</div>
            </div>
        `;
    }
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

// Update room info (called from Python)
eel.expose(update_room_info);
function update_room_info(roomData) {
    currentRoom = roomData.room;
    const members = roomData.members || [];
    
    document.getElementById('currentRoomName').textContent = currentRoom;
    document.getElementById('chatRoomTitle').textContent = currentRoom;
    document.getElementById('roomMembersCount').textContent = ${members.length} member${members.length !== 1 ? 's' : ''};
    
    // Update active room highlight
    document.querySelectorAll('.room-item').forEach(item => {
        item.classList.remove('active');
    });
    const activeRoomItem = document.querySelector(.room-item[onclick*="${currentRoom}"]);
    if (activeRoomItem) {
        activeRoomItem.classList.add('active');
    }
}

// Update users list (called from Python)
eel.expose(update_users_list);
function update_users_list(users) {
    console.log('=== UPDATE USERS LIST ===');
    console.log('Received users:', users);
    console.log('Current username:', currentUsername);
    console.log('========================');
    
    activeUsers = users;
    const usersList = document.getElementById('usersList');
    
    if (!users || users.length === 0) {
        usersList.innerHTML = '<div class="no-users">No users online</div>';
        return;
    }
    
    // If currentUsername is not set yet, load it first
    if (!currentUsername) {
        console.warn('Current username not set, loading user info...');
        loadUserInfo().then(() => {
            // Retry updating the list after username is loaded
            update_users_list(users);
        });
        return;
    }
    
    usersList.innerHTML = '';
    let usersAdded = 0;
    users.forEach(username => {
        // Skip current user
        if (username === currentUsername) {
            console.log('Skipping current user:', username);
            return;
        }
        usersAdded++;
        
        const userItem = document.createElement('div');
        userItem.className = 'user-item';
        
        const initial = username.charAt(0).toUpperCase();
        const isPMActive = pmTargetUser === username;
        userItem.innerHTML = `
            <div class="user-item-avatar" onclick="startPrivateMessage('${username}')" style="cursor: pointer;">${initial}</div>
            <div class="user-item-name" onclick="startPrivateMessage('${username}')" style="cursor: pointer; flex: 1;">${escapeHtml(username)}</div>
            <div class="user-item-actions">
                <button class="user-pm-btn ${isPMActive ? 'active' : ''}" onclick="togglePMMode('${username}'); event.stopPropagation();" title="Toggle private messaging">
                    💬 PM
                </button>
                <button class="user-file-btn" onclick="sendFileToUser('${username}'); event.stopPropagation();" title="Send file to ${escapeHtml(username)}">
                    📎 File
                </button>
                <button class="user-call-btn" onclick="startCall('${username}'); event.stopPropagation();">
                    📞 Call
                </button>
            </div>
        `;
        
        usersList.appendChild(userItem);
    });
    
    console.log('Added', usersAdded, 'users to list');
    
    // If no users were added (all were current user), show no users message
    if (usersAdded === 0) {
        usersList.innerHTML = '<div class="no-users">No other users online</div>';
    }
}

// Update rooms list (called from Python)
eel.expose(update_rooms_list);
function update_rooms_list(rooms) {
    allRooms = rooms;
    const roomsList = document.getElementById('roomsList');
    
    // Keep lobby at top
    roomsList.innerHTML = `
        <div class="room-item ${currentRoom === 'lobby' ? 'active' : ''}" onclick="joinRoomByName('lobby')">
            <span class="room-icon">🏠</span>
            <span>lobby</span>
            <span class="room-count">${rooms['lobby'] ? rooms['lobby'].length : 0}</span>
        </div>
    `;
    
    // Add other rooms
    for (const [roomName, members] of Object.entries(rooms)) {
        if (roomName === 'lobby') continue;
        
        const roomItem = document.createElement('div');
        roomItem.className = room-item ${currentRoom === roomName ? 'active' : ''};
        roomItem.onclick = () => joinRoomByName(roomName);
        
        const icons = ['💬', '🎮', '📚', '🎵', '🎨', '⚽', '🍕', '🌟'];
        const icon = icons[Math.abs(hashCode(roomName)) % icons.length];
        
        roomItem.innerHTML = `
            <span class="room-icon">${icon}</span>
            <span>${escapeHtml(roomName)}</span>
            <span class="room-count">${members.length}</span>
        `;
        
        roomsList.appendChild(roomItem);
    }
}

// Display error message
eel.expose(display_error);
function display_error(errorMsg) {
    displayError(errorMsg);
}

// Helper function to display errors
function displayError(message) {
    const container = document.getElementById('messagesContainer');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'message notification';
    errorDiv.innerHTML = `
        <div class="message-content">
            <div class="message-text" style="color: #f44336;">⚠ ${escapeHtml(message)}</div>
        </div>
    `;
    container.appendChild(errorDiv);
    scrollToBottom();
}

// Start private message with user
function startPrivateMessage(username) {
    if (username === currentUsername) return;
    
    const input = document.getElementById('messageInput');
    input.value = `/pm ${username} `;
    input.focus();
}

// Send file to specific user
function sendFileToUser(username) {
    // Create a hidden file input for this user
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    fileInput.onchange = (e) => handleFileSelectForUser(e, username);
    document.body.appendChild(fileInput);
    fileInput.click();
    // Remove the input after selection
    setTimeout(() => document.body.removeChild(fileInput), 1000);
}

// Handle file selection for specific user
async function handleFileSelectForUser(event, targetUser) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Check file size (limit to 50MB)
    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
        displayError('File too large. Maximum size is 50MB.');
        return;
    }
    
    // Show confirmation
    const confirmed = confirm(Send file "${file.name}" (${formatFileSize(file.size)}) to ${targetUser}?);
    if (!confirmed) {
        return;
    }
    
    try {
        // Read file as ArrayBuffer
        const reader = new FileReader();
        reader.onload = async function(e) {
            try {
                // Convert ArrayBuffer to base64
                const arrayBuffer = e.target.result;
                const bytes = new Uint8Array(arrayBuffer);
                let binary = '';
                for (let i = 0; i < bytes.length; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                const base64 = btoa(binary);
                
                // Send file data through Python with target user
                const result = await eel.send_file_data(file.name, base64, targetUser)();
                
                if (result.success) {
                    displayLocalFile(file.name, file.size, targetUser);
                } else {
                    displayError(result.message || 'Failed to send file');
                }
            } catch (error) {
                console.error('File send error:', error);
                displayError('Failed to send file: ' + error.message);
            }
        };
        
        reader.onerror = function() {
            displayError('Failed to read file');
        };
        
        reader.readAsArrayBuffer(file);
    } catch (error) {
        console.error('File selection error:', error);
        displayError('Failed to select file: ' + error.message);
    }
}

// Scroll to bottom of messages
function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Simple hash function for room icons
function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash;
}

// Send file to specific user
function sendFileToUser(username) {
    // Create a hidden file input for this user
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.style.display = 'none';
    fileInput.onchange = (e) => handleFileSelectForUser(e, username);
    document.body.appendChild(fileInput);
    fileInput.click();
    // Remove the input after selection
    setTimeout(() => document.body.removeChild(fileInput), 1000);
}

// Handle file selection for specific user
async function handleFileSelectForUser(event, targetUser) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Check file size (limit to 50MB)
    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
        displayError('File too large. Maximum size is 50MB.');
        return;
    }
    
    // Show confirmation
    const confirmed = confirm(Send file "${file.name}" (${formatFileSize(file.size)}) to ${targetUser}?);
    if (!confirmed) {
        return;
    }
    
    try {
        // Read file as ArrayBuffer
        const reader = new FileReader();
        reader.onload = async function(e) {
            try {
                // Convert ArrayBuffer to base64
                const arrayBuffer = e.target.result;
                const bytes = new Uint8Array(arrayBuffer);
                let binary = '';
                for (let i = 0; i < bytes.length; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                const base64 = btoa(binary);
                
                // Send file data through Python with target user
                const result = await eel.send_file_data(file.name, base64, targetUser)();
                
                if (result.success) {
                    displayLocalFile(file.name, file.size, targetUser);
                } else {
                    displayError(result.message || 'Failed to send file');
                }
            } catch (error) {
                console.error('File send error:', error);
                displayError('Failed to send file: ' + error.message);
            }
        };
        
        reader.onerror = function() {
            displayError('Failed to read file');
        };
        
        reader.readAsArrayBuffer(file);
    } catch (error) {
        console.error('File selection error:', error);
        displayError('Failed to select file: ' + error.message);
    }
}

// Handle file selection for room (original function)
async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Check file size (limit to 50MB)
    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
        displayError('File too large. Maximum size is 50MB.');
        event.target.value = '';
        return;
    }
    
    // Show confirmation
    const confirmed = confirm(Send file: ${file.name} (${formatFileSize(file.size)}) to room?);
    if (!confirmed) {
        event.target.value = '';
        return;
    }
    
    try {
        // Read file as ArrayBuffer
        const reader = new FileReader();
        reader.onload = async function(e) {
            try {
                // Convert ArrayBuffer to base64
                const arrayBuffer = e.target.result;
                const bytes = new Uint8Array(arrayBuffer);
                let binary = '';
                for (let i = 0; i < bytes.length; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                const base64 = btoa(binary);
                
                // Send file data through Python
                const result = await eel.send_file_data(file.name, base64, null)();
                
                if (result.success) {
                    displayLocalFile(file.name, file.size);
                } else {
                    displayError(result.message || 'Failed to send file');
                }
            } catch (error) {
                console.error('File send error:', error);
                displayError('Failed to send file: ' + error.message);
            }
        };
        
        reader.onerror = function() {
            displayError('Failed to read file');
        };
        
        reader.readAsArrayBuffer(file);
        
    } catch (error) {
        console.error('File selection error:', error);
        displayError('Failed to process file');
    }
    
    // Reset input
    event.target.value = '';
}

// Display file sent by current user
function displayLocalFile(filename, filesize, targetUser = null) {
    const container = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message file';
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const initial = currentUsername.charAt(0).toUpperCase();
    const recipient = targetUser ? to ${escapeHtml(targetUser)} : 'to room';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${initial}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-sender">${escapeHtml(currentUsername)}</span>
                <span class="message-time">${timeStr}</span>
            </div>
            <div class="message-text">
                <div class="file-info">
                    <div class="file-icon">📎</div>
                    <div class="file-details">
                        <div class="file-name">${escapeHtml(filename)}</div>
                        <div class="file-size">${formatFileSize(filesize)}</div>
                    </div>
                </div>
                <div style="color: var(--success-color); font-size: 0.9em;">✓ File sent ${recipient}</div>
            </div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

// Display received file (called from Python)
eel.expose(display_file);
function display_file(fileData) {
    const container = document.getElementById('messagesContainer');
    const welcomeMsg = container.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message file';
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    const sender = fileData.sender || 'Unknown';
    const initial = sender.charAt(0).toUpperCase();
    const filename = fileData.filename || 'unknown_file';
    const filesize = fileData.filesize || 0;
    const filepath = fileData.filepath || '';
    const isImage = fileData.is_image || false;
    const fileUrl = fileData.file_url;
    
    let fileContent = '';
    if (isImage && fileUrl) {
        fileContent = `
            <img src="${fileUrl}" class="file-image" alt="${escapeHtml(filename)}" 
                 onclick="window.open(this.src, '_blank')">
        `;
    } else {
        fileContent = `
            <div style="color: var(--text-secondary); font-size: 0.9em; margin-top: 8px;">
                Saved to: ${escapeHtml(filepath)}
            </div>
        `;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${initial}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-sender">${escapeHtml(sender)}</span>
                <span class="message-time">${timeStr}</span>
            </div>
            <div class="message-text">
                <div class="file-info">
                    <div class="file-icon">${isImage ? '🖼' : '📎'}</div>
                    <div class="file-details">
                        <div class="file-name">${escapeHtml(filename)}</div>
                        <div class="file-size">${formatFileSize(filesize)}</div>
                    </div>
                </div>
                ${fileContent}
            </div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    scrollToBottom();
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ========== VOICE CALLING FUNCTIONS ==========

let currentCaller = null;
let inCall = false;

// Start a call with a user
async function startCall(username) {
    if (username === currentUsername) {
        displayError("You can't call yourself!");
        return;
    }
    
    if (inCall) {
        displayError("Already in a call");
        return;
    }
    
    try {
        const result = await eel.start_call(username)();
        if (result.success) {
            display_message({
                type: 'notification',
                text: result.message
            });
        } else {
            displayError(result.message);
        }
    } catch (error) {
        console.error('Failed to start call:', error);
        displayError('Failed to start call');
    }
}

// Display incoming call modal (called from Python)
eel.expose(display_call_incoming);
function display_call_incoming(caller) {
    currentCaller = caller;
    document.getElementById('callerName').textContent = caller;
    document.getElementById('callIncomingModal').style.display = 'flex';
    
    // Also show notification in chat
    display_message({
        type: 'notification',
        text: 📞 Incoming call from ${caller}
    });
}

// Accept incoming call
async function acceptIncomingCall() {
    if (!currentCaller) return;
    
    try {
        const result = await eel.accept_call(currentCaller)();
        document.getElementById('callIncomingModal').style.display = 'none';
        
        if (!result.success) {
            displayError(result.message);
            currentCaller = null;
        }
    } catch (error) {
        console.error('Failed to accept call:', error);
        displayError('Failed to accept call');
        document.getElementById('callIncomingModal').style.display = 'none';
        currentCaller = null;
    }
}

// Reject incoming call
async function rejectIncomingCall() {
    if (!currentCaller) return;
    
    try {
        const result = await eel.reject_call(currentCaller)();
        document.getElementById('callIncomingModal').style.display = 'none';
        currentCaller = null;
        
        if (result.success) {
            display_message({
                type: 'notification',
                text: 'Call rejected'
            });
        }
    } catch (error) {
        console.error('Failed to reject call:', error);
        document.getElementById('callIncomingModal').style.display = 'none';
        currentCaller = null;
    }
}

// Display call started (called from Python)
eel.expose(display_call_started);
function display_call_started(partner) {
    inCall = true;
    document.getElementById('partnerName').textContent = partner;
    document.getElementById('callActiveModal').style.display = 'flex';
    
    display_message({
        type: 'notification',
        text: 📞 Call connected with ${partner}
    });
}

// Display call ended (called from Python)
eel.expose(display_call_ended);
function display_call_ended(message) {
    inCall = false;
    currentCaller = null;
    document.getElementById('callActiveModal').style.display = 'none';
    document.getElementById('callIncomingModal').style.display = 'none';
    
    display_message({
        type: 'notification',
        text: 📞 ${message}
    });
}

// Hang up current call
async function hangupCall() {
    if (!inCall) return;
    
    try {
        const result = await eel.end_call()();
        document.getElementById('callActiveModal').style.display = 'none';
        inCall = false;
        
        if (result.success) {
            display_message({
                type: 'notification',
                text: 'Call ended'
            });
        }
    } catch (error) {
        console.error('Failed to hang up:', error);
        displayError('Failed to end call');
    }
}