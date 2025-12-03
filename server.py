import socket
import threading
import json
import os
import struct

# Server configuration
HOST = '0.0.0.0'
PORT = 5555
UDP_PORT = 5556  # UDP port for voice data

# Dictionary to keep track of all connected clients: {username: {'socket': socket, 'room': room_name, 'udp_addr': (ip, port)}}
clients = {}
clients_lock = threading.Lock()

# Dictionary to track active calls: {caller: callee}
active_calls = {}
calls_lock = threading.Lock()

# Default room for new users
DEFAULT_ROOM = "lobby"

# UDP socket for voice data
udp_socket = None


def send_json(client_socket, message_dict):
    """Send JSON message to a client"""
    try:
        message = json.dumps(message_dict) + "\n"
        client_socket.send(message.encode('utf-8'))
    except:
        pass


def broadcast(message_dict, sender_username=None, room=None):
    """Send JSON message to clients in a specific room or all clients"""
    with clients_lock:
        for username, user_info in list(clients.items()):
            # Skip sender
            if username == sender_username:
                continue
            
            # If room is specified, only send to users in that room
            if room is not None:
                if user_info['room'] == room:
                    send_json(user_info['socket'], message_dict)
            else:
                # Send to all users (for global notifications)
                send_json(user_info['socket'], message_dict)


def broadcast_active_users():
    """Send the list of active users to all connected clients"""
    with clients_lock:
        user_list = list(clients.keys())
    
    user_list_message = {
        "type": "user_list",
        "payload": user_list
    }
    
    with clients_lock:
        for user_info in clients.values():
            send_json(user_info['socket'], user_list_message)


def send_room_info(client_socket, username):
    """Send current room info and room members to a specific client"""
    with clients_lock:
        if username not in clients:
            return
        
        user_room = clients[username]['room']
        room_members = [uname for uname, info in clients.items() if info['room'] == user_room]
    
    room_info_msg = {
        "type": "room_info",
        "payload": {
            "room": user_room,
            "members": room_members
        }
    }
    send_json(client_socket, room_info_msg)


def send_private_message(sender, target, message):
    """Send a private message from sender to target"""
    with clients_lock:
        if target in clients:
            private_msg = {
                "type": "private_message",
                "sender": sender,
                "payload": message
            }
            send_json(clients[target]['socket'], private_msg)
            return True
        return False


def change_user_room(username, new_room):
    """Change a user's room"""
    with clients_lock:
        if username in clients:
            old_room = clients[username]['room']
            clients[username]['room'] = new_room
            return old_room
        return None


def get_room_users(room):
    """Get list of users in a specific room"""
    with clients_lock:
        return [username for username, info in clients.items() if info['room'] == room]


def send_file_to_user(target_socket, sender, filename, filedata, target_user=None):
    """Send file to a specific user with header-body protocol"""
    try:
        # Send file header as JSON
        file_header = {
            "type": "file_incoming",
            "sender": sender,
            "filename": filename,
            "filesize": len(filedata),
            "target": target_user
        }
        header_json = json.dumps(file_header) + "\n"
        target_socket.send(header_json.encode('utf-8'))
        
        # Send file size as 4-byte integer (for binary mode verification)
        target_socket.send(struct.pack('>I', len(filedata)))
        
        # Send raw binary file data in chunks
        chunk_size = 4096
        for i in range(0, len(filedata), chunk_size):
            chunk = filedata[i:i + chunk_size]
            target_socket.send(chunk)
        
        print(f"[FILE SENT] {filename} ({len(filedata)} bytes) to {target_user or 'room'}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send file: {e}")
        return False


def broadcast_file(filedata, filename, sender, room):
    """Broadcast file to all users in a room except sender"""
    with clients_lock:
        for username, user_info in list(clients.items()):
            if username != sender and user_info['room'] == room:
                send_file_to_user(user_info['socket'], sender, filename, filedata, username)


def handle_udp_voice():
    """Handle UDP voice packets and forward them"""
    global udp_socket
    print(f"[UDP] Voice server listening on {HOST}:{UDP_PORT}")
    
    while True:
        try:
            # Receive voice data (username prefix + audio data)
            data, addr = udp_socket.recvfrom(8192)
            
            if len(data) < 2:
                continue
            
            # First 2 bytes: username length
            username_len = struct.unpack('>H', data[:2])[0]
            
            if len(data) < 2 + username_len:
                continue
            
            # Extract username
            username = data[2:2+username_len].decode('utf-8')
            
            # Update client's UDP address
            with clients_lock:
                if username in clients:
                    clients[username]['udp_addr'] = addr
            
            # Get call partner
            with calls_lock:
                target = active_calls.get(username)
            
            if target:
                # Forward audio to call partner
                with clients_lock:
                    if target in clients and 'udp_addr' in clients[target]:
                        target_addr = clients[target]['udp_addr']
                        # Send only the audio data (skip username header)
                        audio_data = data[2+username_len:]
                        udp_socket.sendto(audio_data, target_addr)
        
        except Exception as e:
            print(f"[UDP ERROR] {e}")
            continue


def handle_client(client_socket, client_address):
    """Handle individual client connection"""
    global active_calls, calls_lock
    print(f"[NEW CONNECTION] {client_address} connected.")
    username = None
    
    try:
        # Wait for login message with username
        client_socket.settimeout(30)  # 30 second timeout for login
        data = client_socket.recv(1024).decode('utf-8')
        
        if not data:
            client_socket.close()
            return
        
        # Parse login message
        try:
            message = json.loads(data.strip())
            if message.get("type") == "login":
                username = message.get("payload", "").strip()
                
                if not username:
                    error_msg = {"type": "error", "payload": "Username cannot be empty"}
                    send_json(client_socket, error_msg)
                    client_socket.close()
                    return
                
                # Check if username already exists
                with clients_lock:
                    if username in clients:
                        error_msg = {"type": "error", "payload": "Username already taken"}
                        send_json(client_socket, error_msg)
                        client_socket.close()
                        return
                    
                    # Add client to dictionary with default room
                    clients[username] = {
                        'socket': client_socket,
                        'room': DEFAULT_ROOM
                    }
                
                print(f"[LOGIN] {username} ({client_address}) logged in.")
                
                # Send success message
                success_msg = {"type": "login_success", "payload": f"Welcome, {username}!"}
                send_json(client_socket, success_msg)
                
                # Send initial room info to the new user
                send_room_info(client_socket, username)
                
                # Notify all clients in the same room about new user
                join_msg = {"type": "notification", "payload": f"{username} joined the chat!"}
                broadcast(join_msg, username, DEFAULT_ROOM)
                
                # Broadcast updated active users list
                broadcast_active_users()
                
            else:
                client_socket.close()
                return
        except json.JSONDecodeError:
            client_socket.close()
            return
        
        # Remove timeout for regular messaging
        client_socket.settimeout(None)
        
        # Handle messages from client
        buffer = ""
        while True:
            data = client_socket.recv(1024).decode('utf-8')
            
            if not data:
                break
            
            buffer += data
            
            # Process complete JSON messages (separated by newlines)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    msg_type = message.get("type")
                    payload = message.get("payload")
                    
                    if msg_type == "message" and payload:
                        # Get user's current room
                        with clients_lock:
                            user_room = clients[username]['room']
                        
                        print(f"[{username}@{user_room}] {payload}")
                        
                        # Broadcast chat message to users in the same room
                        chat_msg = {
                            "type": "message",
                            "sender": username,
                            "room": user_room,
                            "payload": payload
                        }
                        broadcast(chat_msg, username, user_room)
                    
                    elif msg_type == "private_message":
                        target = message.get("target")
                        msg = message.get("payload")
                        
                        if target and msg:
                            print(f"[PRIVATE] {username} -> {target}: {msg}")
                            
                            if send_private_message(username, target, msg):
                                # Send confirmation to sender
                                confirm_msg = {
                                    "type": "private_sent",
                                    "target": target,
                                    "payload": msg
                                }
                                send_json(client_socket, confirm_msg)
                            else:
                                # User not found
                                error_msg = {
                                    "type": "error",
                                    "payload": f"User '{target}' not found or offline"
                                }
                                send_json(client_socket, error_msg)
                    
                    elif msg_type == "join_room":
                        new_room = payload.strip() if payload else DEFAULT_ROOM
                        
                        if not new_room:
                            error_msg = {"type": "error", "payload": "Room name cannot be empty"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        old_room = change_user_room(username, new_room)
                        
                        if old_room:
                            print(f"[ROOM] {username} moved from '{old_room}' to '{new_room}'")
                            
                            # Notify old room that user left
                            if old_room != new_room:
                                leave_notif = {
                                    "type": "notification",
                                    "payload": f"{username} left the room"
                                }
                                broadcast(leave_notif, username, old_room)
                            
                            # Notify new room that user joined
                            join_notif = {
                                "type": "notification",
                                "payload": f"{username} joined the room"
                            }
                            broadcast(join_notif, username, new_room)
                            
                            # Send room info to the user who joined
                            send_room_info(client_socket, username)
                            
                            # Broadcast updated user list to everyone
                            broadcast_active_users()
                    
                    elif msg_type == "list_rooms":
                        # Get all unique rooms
                        with clients_lock:
                            rooms = {}
                            for uname, info in clients.items():
                                room = info['room']
                                if room not in rooms:
                                    rooms[room] = []
                                rooms[room].append(uname)
                        
                        room_list_msg = {
                            "type": "room_list",
                            "payload": rooms
                        }
                        send_json(client_socket, room_list_msg)
                    
                    elif msg_type == "call_request":
                        # Handle voice call request
                        target = payload
                        
                        if not target:
                            error_msg = {"type": "error", "payload": "Invalid call request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        with clients_lock:
                            if target not in clients:
                                error_msg = {"type": "error", "payload": f"User '{target}' not found"}
                                send_json(client_socket, error_msg)
                                continue
                            
                            target_socket = clients[target]['socket']
                        
                        # Check if either user is already in a call
                        with calls_lock:
                            if username in active_calls or target in active_calls:
                                error_msg = {"type": "error", "payload": "User is already in a call"}
                                send_json(client_socket, error_msg)
                                continue
                        
                        print(f"[CALL] {username} calling {target}")
                        
                        # Send call request to target
                        call_notif = {
                            "type": "call_incoming",
                            "payload": username
                        }
                        send_json(target_socket, call_notif)
                        
                        # Send confirmation to caller
                        call_confirm = {
                            "type": "call_ringing",
                            "payload": f"Calling {target}..."
                        }
                        send_json(client_socket, call_confirm)
                    
                    elif msg_type == "call_accept":
                        # Handle call acceptance
                        caller = payload
                        
                        with clients_lock:
                            if caller not in clients:
                                error_msg = {"type": "error", "payload": "Caller not found"}
                                send_json(client_socket, error_msg)
                                continue
                            
                            caller_socket = clients[caller]['socket']
                        
                        # Establish call
                        with calls_lock:
                            active_calls[username] = caller
                            active_calls[caller] = username
                        
                        print(f"[CALL] {username} accepted call from {caller}")
                        
                        # Notify both users
                        call_started = {
                            "type": "call_started",
                            "payload": username
                        }
                        send_json(caller_socket, call_started)
                        
                        call_started_self = {
                            "type": "call_started",
                            "payload": caller
                        }
                        send_json(client_socket, call_started_self)
                    
                    elif msg_type == "call_reject":
                        # Handle call rejection
                        caller = payload
                        
                        with clients_lock:
                            if caller in clients:
                                caller_socket = clients[caller]['socket']
                                call_rejected = {
                                    "type": "call_rejected",
                                    "payload": f"{username} declined the call"
                                }
                                send_json(caller_socket, call_rejected)
                        
                        print(f"[CALL] {username} rejected call from {caller}")
                    
                    elif msg_type == "call_end":
                        # Handle call termination
                        with calls_lock:
                            partner = active_calls.get(username)
                            if partner:
                                del active_calls[username]
                                if username in active_calls.values():
                                    # Remove reverse mapping
                                    active_calls = {k: v for k, v in active_calls.items() if v != username}
                        
                        if partner:
                            with clients_lock:
                                if partner in clients:
                                    partner_socket = clients[partner]['socket']
                                    call_ended = {
                                        "type": "call_ended",
                                        "payload": f"{username} ended the call"
                                    }
                                    send_json(partner_socket, call_ended)
                            
                            print(f"[CALL] Call ended between {username} and {partner}")
                        
                        # Confirm to sender
                        call_ended_self = {
                            "type": "call_ended",
                            "payload": "Call ended"
                        }
                        send_json(client_socket, call_ended_self)
                    
                    elif msg_type == "file_transfer":
                        # Handle file transfer with header-body protocol
                        filename = message.get("filename")
                        filesize = message.get("filesize")
                        target = message.get("target")  # None for room, username for private
                        
                        if not filename or not filesize:
                            error_msg = {"type": "error", "payload": "Invalid file transfer request"}
                            send_json(client_socket, error_msg)
                            continue
                        
                        print(f"[FILE TRANSFER] {username} sending {filename} ({filesize} bytes)")
                        
                        # Send acknowledgment to start binary transfer
                        ack_msg = {"type": "file_transfer_ready", "payload": "Ready to receive"}
                        send_json(client_socket, ack_msg)
                        
                        # Read binary file size header (4 bytes)
                        size_data = client_socket.recv(4)
                        if len(size_data) != 4:
                            print(f"[ERROR] Invalid file size header from {username}")
                            continue
                        
                        expected_size = struct.unpack('>I', size_data)[0]
                        
                        if expected_size != filesize:
                            print(f"[ERROR] File size mismatch from {username}")
                            continue
                        
                        # Receive raw binary data in chunks
                        filedata = b''
                        remaining = filesize
                        
                        while remaining > 0:
                            chunk_size = min(4096, remaining)
                            chunk = client_socket.recv(chunk_size)
                            
                            if not chunk:
                                print(f"[ERROR] Connection lost during file transfer from {username}")
                                break
                            
                            filedata += chunk
                            remaining -= len(chunk)
                        
                        if len(filedata) == filesize:
                            print(f"[FILE RECEIVED] {filename} ({len(filedata)} bytes) from {username}")
                            
                            # Send confirmation to sender
                            confirm_msg = {
                                "type": "file_sent_confirm",
                                "payload": f"File '{filename}' sent successfully"
                            }
                            send_json(client_socket, confirm_msg)
                            
                            # Forward file to target or room
                            if target:
                                # Private file transfer
                                with clients_lock:
                                    if target in clients:
                                        send_file_to_user(
                                            clients[target]['socket'],
                                            username,
                                            filename,
                                            filedata,
                                            target
                                        )
                                    else:
                                        error_msg = {
                                            "type": "error",
                                            "payload": f"User '{target}' not found"
                                        }
                                        send_json(client_socket, error_msg)
                            else:
                                # Broadcast to room
                                with clients_lock:
                                    user_room = clients[username]['room']
                                broadcast_file(filedata, filename, username, user_room)
                        else:
                            print(f"[ERROR] File transfer incomplete from {username}")
                            error_msg = {
                                "type": "error",
                                "payload": "File transfer failed - incomplete data"
                            }
                            send_json(client_socket, error_msg)
                        
                except json.JSONDecodeError:
                    print(f"[ERROR] Invalid JSON from {username}")
                    continue
                
    except socket.timeout:
        print(f"[TIMEOUT] {client_address} did not login in time.")
    except Exception as e:
        print(f"[ERROR] {client_address}: {e}")
    
    finally:
        # Remove client from dictionary and close connection
        if username:
            # End any active call
            with calls_lock:
                partner = active_calls.get(username)
                if partner:
                    del active_calls[username]
                    if partner in active_calls:
                        del active_calls[partner]
                    
                    # Notify partner
                    with clients_lock:
                        if partner in clients:
                            partner_socket = clients[partner]['socket']
                            call_ended = {
                                "type": "call_ended",
                                "payload": f"{username} disconnected"
                            }
                            send_json(partner_socket, call_ended)
            
            with clients_lock:
                if username in clients:
                    del clients[username]
            
            print(f"[DISCONNECTED] {username} ({client_address}) left the chat.")
            
            # Notify other clients
            leave_msg = {"type": "notification", "payload": f"{username} left the chat!"}
            broadcast(leave_msg, username)
            
            # Broadcast updated active users list
            broadcast_active_users()
        
        try:
            client_socket.close()
        except:
            pass


def start_server():
    """Initialize and start the TCP server"""
    global udp_socket
    
    # Setup TCP server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()
    
    print(f"[LISTENING] TCP Server is listening on {HOST}:{PORT}")
    
    # Setup UDP server for voice
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST, UDP_PORT))
    
    # Start UDP handler thread
    udp_thread = threading.Thread(target=handle_udp_voice, daemon=True)
    udp_thread.start()
    
    try:
        while True:
            # Accept new connection
            client_socket, client_address = server.accept()
            
            # Create new thread for this client
            thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            thread.daemon = True
            thread.start()
            
            print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
    
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down...")
    finally:
        server.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Multi-Threaded Chat Server with Voice Calling")
    print("TCP Port: 5555 | UDP Port: 5556")
    print("=" * 50)
    start_server()
