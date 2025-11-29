# server_gui.py
# GUI-based LAN chat server (integrated from original server.py)
# Features: Start/stop server, monitor logs, handle clients with chat/file/call support.
# GUI uses Tkinter for control and logging.

import socket
import threading
import datetime
import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
import queue

HOST = "127.0.0.1"
PORT = 5555
BUFFER = 4096

lock = threading.Lock()
clients = {}   # username -> (conn, addr)
groups = {}    # groupname -> set(usernames)
call_state = {}  # username -> (calling_to_username or None)

class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LAN Chat Server - Stopped")
        self.root.geometry("700x500")

        # Server variables
        self.server_thread = None
        self.server_socket = None
        self.running = False

        # GUI Elements
        # Config Frame
        config_frame = tk.Frame(root)
        config_frame.pack(pady=5)

        tk.Label(config_frame, text="Host IP:").grid(row=0, column=0)
        self.host_entry = tk.Entry(config_frame, width=15)
        self.host_entry.insert(0, HOST)
        self.host_entry.grid(row=0, column=1)

        tk.Label(config_frame, text="Port:").grid(row=0, column=2)
        self.port_entry = tk.Entry(config_frame, width=5)
        self.port_entry.insert(0, str(PORT))
        self.port_entry.grid(row=0, column=3)

        self.start_btn = tk.Button(config_frame, text="Start Server", command=self.start_server)
        self.start_btn.grid(row=0, column=4, padx=5)

        self.stop_btn = tk.Button(config_frame, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=5)

        self.clear_btn = tk.Button(config_frame, text="Clear Logs", command=self.clear_logs)
        self.clear_btn.grid(row=0, column=6, padx=5)

        # Status Label
        self.status_label = tk.Label(root, text="Server Status: Stopped", fg="red")
        self.status_label.pack(pady=5)

        # Log Display
        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED, height=20)
        self.log_area.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

        # Message queue for thread-safe GUI updates
        self.log_queue = queue.Queue()
        self.root.after(100, self.process_queue)  # Check queue periodically

        # Override print to log to GUI
        import builtins
        original_print = builtins.print
        builtins.print = self.gui_print

    def gui_print(self, *args, **kwargs):
        text = " ".join(str(arg) for arg in args)
        if kwargs:
            text += " " + str(kwargs)
        self.log_queue.put(text + "\n")

    def append_to_log(self, text):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, text)
        self.log_area.see(tk.END)  # Auto-scroll
        self.log_area.config(state=tk.DISABLED)

    def process_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.append_to_log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def start_server(self):
        if self.running:
            messagebox.showwarning("Warning", "Server is already running.")
            return

        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.")
            return

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((host, port))
            self.server_socket.listen(100)
            self.running = True
            self.root.title(f"LAN Chat Server - Running on {host}:{port}")
            self.status_label.config(text=f"Server Status: Running on {host}:{port}", fg="green")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.append_to_log(f"Starting server on {host}:{port}\n")

            # Start server thread
            self.server_thread = threading.Thread(target=self.server_main, daemon=True)
            self.server_thread.start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start server: {e}")
            self.server_socket.close()
            self.server_socket = None

    def stop_server(self):
        if not self.running:
            return

        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        self.server_socket = None
        self.root.title("LAN Chat Server - Stopped")
        self.status_label.config(text="Server Status: Stopped", fg="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.append_to_log("Server stopped.\n")
