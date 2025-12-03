import socket
import threading
import json
import eel
import os
import struct
import base64

# Try to import PyAudio for voice calling
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("[WARNING] PyAudio not available. Voice calling will be disabled.")

# Configuration
HOST = '192.168.43.231'
PORT = 5555
UDP_PORT = 5556

username = ""
current_room = "lobby"
client_socket = None
udp_socket = None
connected = False
file_receiving_mode = False
file_info = {}

# Voice calling state
in_call = False
call_partner = ""
p_audio = None

# Create downloads folder
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Initialize Eel with web folder
eel.init('web')


def audio_send_thread():
    """Thread to capture and send audio via UDP"""
    global in_call, udp_socket, p_audio, username
    
    if not PYAUDIO_AVAILABLE or not p_audio:
        return
    
    try:
        # Audio stream configuration
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        stream = p_audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
        
        print("[VOICE] Microphone active")
        
        while in_call:
            try:
                # Capture audio
                audio_data = stream.read(CHUNK, exception_on_overflow=False)
                
                # Prepend username for server routing (2-byte length + username + audio)
                username_bytes = username.encode('utf-8')
                username_len = struct.pack('>H', len(username_bytes))
                packet = username_len + username_bytes + audio_data
                
                # Send via UDP
                udp_socket.sendto(packet, (HOST, UDP_PORT))
            except Exception as e:
                if in_call:
                    print(f"[VOICE ERROR] Send: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        
    except Exception as e:
        print(f"[VOICE ERROR] Audio capture: {e}")


def audio_receive_thread():
    """Thread to receive and play audio via UDP"""
    global in_call, udp_socket, p_audio
    
    if not PYAUDIO_AVAILABLE or not p_audio:
        return
    
    try:
        # Audio stream configuration
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        
        stream = p_audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            output=True,
                            frames_per_buffer=CHUNK)
        
        print("[VOICE] Speaker active")
        
        while in_call:
            try:
                # Receive audio data (server sends only audio, no header)
                data, addr = udp_socket.recvfrom(8192)
                
                # Play audio directly
                if data and in_call:
                    stream.write(data)
            except socket.timeout:
                # Timeout is normal when no audio is being sent
                continue
            except Exception as e:
                if in_call:
                    print(f"[VOICE ERROR] Receive: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        
    except Exception as e:
        print(f"[VOICE ERROR] Audio playback: {e}")


def start_voice_call():
    """Start voice call audio streams"""
    global in_call, p_audio, udp_socket
    
    if not PYAUDIO_AVAILABLE:
        print("[VOICE] PyAudio not available. Voice calling disabled.")
        eel.display_error("Voice calling requires PyAudio. Please install it.")
        return
    
    in_call = True
    
    try:
        # Initialize PyAudio only once if not already initialized
        if p_audio is None:
            p_audio = pyaudio.PyAudio()
        
        # Start audio threads
        send_thread = threading.Thread(target=audio_send_thread, daemon=True)
        receive_thread = threading.Thread(target=audio_receive_thread, daemon=True)
        
        send_thread.start()
        receive_thread.start()
        
    except Exception as e:
        print(f"[VOICE ERROR] Failed to start call: {e}")
        in_call = False
        eel.display_error(f"Failed to start voice call: {str(e)}")


def stop_voice_call():
    """Stop voice call audio streams"""
    global in_call
    
    # Set flag to false to stop audio threads
    in_call = False
    
    # Give threads time to finish gracefully
    import time
    time.sleep(0.2)


def receive_messages():
    """Thread function to receive messages from server"""
    global connected, current_room, file_receiving_mode, file_info, call_partner
    buffer = ""
    
    while connected:
        try:
            # Check if we're in file receiving mode
            if file_receiving_mode:
                # Read file size header (4 bytes)
                size_data = client_socket.recv(4)
                if len(size_data) != 4:
                    eel.display_error("Invalid file size header")
                    file_receiving_mode = False
                    continue
                
                expected_size = struct.unpack('>I', size_data)[0]
                filename = file_info.get('filename', 'unknown_file')
                sender = file_info.get('sender', 'Unknown')
                
                # Receive raw binary data
                filedata = b''
                remaining = expected_size
                
                while remaining > 0:
                    chunk_size = min(4096, remaining)
                    chunk = client_socket.recv(chunk_size)
                    
                    if not chunk:
                        eel.display_error("Connection lost during file transfer")
                        break
                    
                    filedata += chunk
                    remaining -= len(chunk)
                
                # Save file to downloads folder
                if len(filedata) == expected_size:
                    safe_filename = os.path.basename(filename)
                    filepath = os.path.join('downloads', safe_filename)
                    
                    # Handle duplicate filenames
                    counter = 1
                    base_name, ext = os.path.splitext(safe_filename)
                    while os.path.exists(filepath):
                        filepath = os.path.join('downloads', f"{base_name}_{counter}{ext}")
                        counter += 1
                    
                    with open(filepath, 'wb') as f:
                        f.write(filedata)
                    
                    # Convert to base64 for web display if it's an image
                    file_ext = ext.lower()
                    is_image = file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
                    
                    file_url = None
                    if is_image:
                        file_url = f"data:image/{file_ext[1:]};base64,{base64.b64encode(filedata).decode('utf-8')}"
                    
                    # Display file received message
                    eel.display_file({
                        "type": "received",
                        "sender": sender,
                        "filename": filename,
                        "filepath": filepath,
                        "filesize": expected_size,
                        "is_image": is_image,
                        "file_url": file_url
                    })
                else:
                    eel.display_error(f"File transfer incomplete ({len(filedata)}/{expected_size} bytes)")
                
                file_receiving_mode = False
                file_info = {}
                continue
            
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                eel.display_error("Connection to server lost")
                connected = False
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
                    
                    if msg_type == "login_success":
                        eel.display_message({
                            "type": "notification",
                            "text": payload
                        })
                        
                    elif msg_type == "error":
                        eel.display_error(payload)
                        
                    elif msg_type == "notification":
                        eel.display_message({
                            "type": "notification",
                            "text": payload
                        })
                        
                    elif msg_type == "message":
                        sender = message.get("sender", "Unknown")
                        eel.display_message({
                            "type": "message",
                            "sender": sender,
                            "text": payload
                        })
                    
                    elif msg_type == "private_message":
                        sender = message.get("sender", "Unknown")
                        eel.display_message({
                            "type": "private",
                            "sender": sender,
                            "text": payload
                        })
                    
                    elif msg_type == "private_sent":
                        target = message.get("target", "Unknown")
                        eel.display_message({
                            "type": "private",
                            "sender": f"You → {target}",
                            "text": payload
                        })
                    
                    elif msg_type == "room_info":
                        room_data = payload
                        current_room = room_data['room']
                        eel.update_room_info(room_data)
                    
                    elif msg_type == "room_list":
                        print(f"[DEBUG] Received room_list: {payload}")
                        eel.update_rooms_list(payload)
                    
                    elif msg_type == "user_list":
                        print(f"[DEBUG] Received user_list: {payload}")
                        try:
                            eel.update_users_list(payload)
                            print(f"[DEBUG] Called eel.update_users_list successfully")
                        except Exception as e:
                            print(f"[ERROR] Failed to call eel.update_users_list: {e}")
                    
                    elif msg_type == "file_incoming":
                        file_receiving_mode = True
                        file_info = {
                            'filename': message.get('filename'),
                            'filesize': message.get('filesize'),
                            'sender': message.get('sender')
                        }
                        # File will be received in next iteration
                        continue
                    
                    elif msg_type == "file_transfer_ready":
                        # Server is ready to receive file
                        pass
                    
                    elif msg_type == "file_sent_confirm":
                        eel.display_message({
                            "type": "notification",
                            "text": payload
                        })
                    
                    elif msg_type == "call_incoming":
                        # Incoming call notification
                        caller = payload
                        call_partner = caller
                        eel.display_call_incoming(caller)
                    
                    elif msg_type == "call_ringing":
                        # Call is ringing
                        eel.display_message({
                            "type": "notification",
                            "text": payload
                        })
                    
                    elif msg_type == "call_started":
                        # Call connected
                        partner = payload
                        call_partner = partner
                        eel.display_call_started(partner)
                        
                        if PYAUDIO_AVAILABLE:
                            start_voice_call()
                    
                    elif msg_type == "call_rejected":
                        # Call was rejected
                        eel.display_message({
                            "type": "notification",
                            "text": payload
                        })
                        call_partner = ""
                    
                    elif msg_type == "call_ended":
                        # Call ended
                        eel.display_call_ended(payload)
                        stop_voice_call()
                        call_partner = ""
                        
                except json.JSONDecodeError:
                    print(f"[ERROR] Invalid JSON from server")
                    continue
                    
        except Exception as e:
            if connected:
                print(f"[ERROR] {e}")
                eel.display_error(f"Connection error: {str(e)}")
                connected = False
            break


@eel.expose
def connect_to_server(user, host, port):
    """Connect to the chat server"""
    global username, client_socket, udp_socket, connected, HOST, PORT
    
    try:
        # Store host and port for UDP
        HOST = host
        PORT = port
        
        # Create TCP socket and connect to server
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(10)
        client_socket.connect((host, port))
        client_socket.settimeout(None)
        
        # Create UDP socket for voice
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(2.0)  # Longer timeout to prevent constant errors
        
        username = user
        connected = True
        
        # Send login message
        login_msg = {
            "type": "login",
            "payload": username
        }
        json_message = json.dumps(login_msg) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        
        # Start receive thread
        receive_thread = threading.Thread(target=receive_messages, daemon=True)
        receive_thread.start()
        
        return {"success": True, "message": "Connected successfully"}
        
    except socket.timeout:
        return {"success": False, "message": "Connection timeout. Server not responding."}
    except ConnectionRefusedError:
        return {"success": False, "message": f"Could not connect to {host}:{port}. Make sure the server is running."}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}


@eel.expose
def send_message(message):
    """Send a message to the server"""
    global client_socket, connected
    
    if not connected or not client_socket:
        eel.display_error("Not connected to server")
        return False
    
    try:
        message = message.strip()
        if not message:
            return False
        
        # Handle commands
        if message.startswith('/pm '):
            # Private message: /pm username message
            parts = message.split(' ', 2)
            if len(parts) < 3:
                eel.display_error("Usage: /pm <username> <message>")
                return False
            
            target_user = parts[1]
            private_msg = parts[2]
            
            # Don't display immediately - wait for server confirmation to avoid duplicate
            
            msg_dict = {
                "type": "private_message",
                "target": target_user,
                "payload": private_msg
            }
        
        elif message.startswith('/join '):
            # Join room: /join roomname
            parts = message.split(' ', 1)
            if len(parts) < 2:
                eel.display_error("Usage: /join <room_name>")
                return False
            
            room_name = parts[1].strip()
            
            msg_dict = {
                "type": "join_room",
                "payload": room_name
            }
        
        elif message == '/rooms':
            # List all rooms
            msg_dict = {
                "type": "list_rooms",
                "payload": ""
            }
        
        elif message == '/help':
            eel.display_message({
                "type": "notification",
                "text": "Commands: /pm [user] [msg] | /join [room] | /rooms | /help"
            })
            return True
        
        else:
            # Regular message
            msg_dict = {
                "type": "message",
                "payload": message
            }
            
            # Display the sent message immediately
            eel.display_message({
                "type": "message",
                "sender": username,
                "text": message
            })
        
        json_message = json.dumps(msg_dict) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        return True
        
    except Exception as e:
        eel.display_error(f"Failed to send message: {str(e)}")
        return False


@eel.expose
def join_room(room_name):
    """Join a chat room"""
    return send_message(f"/join {room_name}")


@eel.expose
def request_rooms_list():
    """Request list of all rooms"""
    return send_message("/rooms")


@eel.expose
def get_user_info():
    """Get current user information"""
    return {
        "username": username,
        "room": current_room
    }


@eel.expose
def send_file(filepath, target_user=None):
    """Send a file to room or specific user (for CLI compatibility)"""
    global client_socket, connected
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    try:
        if not os.path.exists(filepath):
            return {"success": False, "message": "File not found"}
        
        if not os.path.isfile(filepath):
            return {"success": False, "message": "Not a file"}
        
        # Read file in binary mode
        with open(filepath, 'rb') as f:
            filedata = f.read()
        
        filename = os.path.basename(filepath)
        filesize = len(filedata)
        
        # Send file transfer header
        file_header = {
            "type": "file_transfer",
            "filename": filename,
            "filesize": filesize,
            "target": target_user
        }
        header_json = json.dumps(file_header) + "\n"
        client_socket.send(header_json.encode('utf-8'))
        
        # Brief pause for server to process header
        import time
        time.sleep(0.1)
        
        # Send file size as 4-byte integer
        client_socket.send(struct.pack('>I', filesize))
        
        # Send raw binary data in chunks
        chunk_size = 4096
        for i in range(0, filesize, chunk_size):
            chunk = filedata[i:i + chunk_size]
            client_socket.send(chunk)
        
        return {"success": True, "message": f"File '{filename}' sent successfully"}
        
    except Exception as e:
        return {"success": False, "message": f"Failed to send file: {str(e)}"}


@eel.expose
def send_file_data(filename, base64_data, target_user=None):
    """Send file data from browser (base64 encoded)"""
    global client_socket, connected
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    try:
        # Decode base64 to binary
        filedata = base64.b64decode(base64_data)
        filesize = len(filedata)
        
        # Send file transfer header
        file_header = {
            "type": "file_transfer",
            "filename": filename,
            "filesize": filesize,
            "target": target_user
        }
        header_json = json.dumps(file_header) + "\n"
        client_socket.send(header_json.encode('utf-8'))
        
        # Brief pause for server to process header
        import time
        time.sleep(0.1)
        
        # Send file size as 4-byte integer
        client_socket.send(struct.pack('>I', filesize))
        
        # Send raw binary data in chunks
        chunk_size = 4096
        for i in range(0, filesize, chunk_size):
            chunk = filedata[i:i + chunk_size]
            client_socket.send(chunk)
        
        return {"success": True, "message": f"File '{filename}' sent successfully"}
        
    except Exception as e:
        return {"success": False, "message": f"Failed to send file: {str(e)}"}


@eel.expose
def start_call(target_user):
    """Start a voice call with a user"""
    global client_socket, connected
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    if not PYAUDIO_AVAILABLE:
        return {"success": False, "message": "PyAudio not available. Voice calling disabled."}
    
    try:
        msg_dict = {
            "type": "call_request",
            "payload": target_user
        }
        json_message = json.dumps(msg_dict) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        return {"success": True, "message": f"Calling {target_user}..."}
    except Exception as e:
        return {"success": False, "message": f"Failed to start call: {str(e)}"}


@eel.expose
def accept_call(caller):
    """Accept an incoming call"""
    global client_socket, connected, call_partner
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    if not call_partner:
        return {"success": False, "message": "No incoming call"}
    
    try:
        msg_dict = {
            "type": "call_accept",
            "payload": caller
        }
        json_message = json.dumps(msg_dict) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        return {"success": True, "message": f"Call accepted with {caller}"}
    except Exception as e:
        return {"success": False, "message": f"Failed to accept call: {str(e)}"}


@eel.expose
def reject_call(caller):
    """Reject an incoming call"""
    global client_socket, connected, call_partner
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    try:
        msg_dict = {
            "type": "call_reject",
            "payload": caller
        }
        json_message = json.dumps(msg_dict) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        call_partner = ""
        return {"success": True, "message": "Call rejected"}
    except Exception as e:
        return {"success": False, "message": f"Failed to reject call: {str(e)}"}


@eel.expose
def end_call():
    """End the current call"""
    global client_socket, connected, in_call, call_partner
    
    if not connected or not client_socket:
        return {"success": False, "message": "Not connected to server"}
    
    if not in_call:
        return {"success": False, "message": "No active call"}
    
    try:
        msg_dict = {
            "type": "call_end",
            "payload": call_partner
        }
        json_message = json.dumps(msg_dict) + "\n"
        client_socket.send(json_message.encode('utf-8'))
        
        stop_voice_call()
        call_partner = ""
        return {"success": True, "message": "Call ended"}
    except Exception as e:
        return {"success": False, "message": f"Failed to end call: {str(e)}"}


@eel.expose
def disconnect():
    """Disconnect from server"""
    global connected, client_socket, udp_socket, p_audio
    
    connected = False
    
    # Stop any active call
    stop_voice_call()
    
    # Clean up PyAudio
    if p_audio:
        try:
            p_audio.terminate()
        except:
            pass
    
    # Close sockets
    if client_socket:
        try:
            client_socket.close()
        except:
            pass
    
    if udp_socket:
        try:
            udp_socket.close()
        except:
            pass
    
    return True


def main():
    """Main function to start the GUI"""
    print("=" * 50)
    print("Multi-Threaded Chat Client - GUI Version")
    print("=" * 50)
    print("Starting GUI...")
    print("Make sure the server is running on the specified host and port.")
    print("=" * 50)
    
    try:
        # Start Eel with the login page
        eel.start('login.html', size=(1200, 800), port=8080)
    except (SystemExit, KeyboardInterrupt):
        print("\n[INFO] Application closed")
    except Exception as e:
        print(f"[ERROR] Failed to start GUI: {e}")
    finally:
        # Stop any active call
        stop_voice_call()
        
        # Clean up PyAudio
        if p_audio:
            try:
                p_audio.terminate()
            except:
                pass
        
        # Close sockets
        if connected and client_socket:
            try:
                client_socket.close()
            except:
                pass
        
        if udp_socket:
            try:
                udp_socket.close()
            except:
                pass


if __name__ == "__main__":
    main()
