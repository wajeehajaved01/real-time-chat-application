# Clear clients/groups (optional cleanup)
        with lock:
            for uname in list(clients.keys()):
                try:
                    clients[uname][0].close()
                except:
                    pass
            clients.clear()
            groups.clear()
            call_state.clear()

    def clear_logs(self):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)

    def server_main(self):
        try:
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                    if not self.running:
                        conn.close()
                        break
                    t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                    t.start()
                except OSError:
                    # Socket closed
                    break
        except Exception as e:
            self.log_queue.put(f"Server main error: {e}\n")
        finally:
            self.stop_server()

    # Copied and adapted from original server.py
    def timestamp(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def broadcast(self, msg, exclude=None):
        with lock:
            for uname, (conn, _) in list(clients.items()):
                if exclude and uname == exclude:
                    continue
                try:
                    conn.sendall(msg.encode("utf-8"))
                except:
                    self._remove_client(uname)

    def _remove_client(self, username):
        with lock:
            clients.pop(username, None)
            for g in list(groups.keys()):
                if username in groups[g]:
                    groups[g].remove(username)
                    if len(groups[g]) == 0:
                        groups.pop(g, None)
            call_state.pop(username, None)

    def send_private_text(self, to_user, text):
        with lock:
            t = clients.get(to_user)
            if not t:
                return False
            conn, _ = t
            try:
                conn.sendall(text.encode("utf-8"))
                return True
            except:
                self._remove_client(to_user)
                return False

    def forward_file_bytes(self, to_user, header_bytes, file_iter):
        with lock:
            t = clients.get(to_user)
            if not t:
                return False
            conn, _ = t
            try:
                conn.sendall(header_bytes)
                for chunk in file_iter:
                    conn.sendall(chunk)
                return True
            except:
                self._remove_client(to_user)
                return False

    def handle_client(self, conn, addr):
        username = None
        try:
            conn.sendall(b"USERNAME:")
            username = conn.recv(1024).decode("utf-8").strip()
            if not username:
                conn.close()
                return

            with lock:
                if username in clients:
                    conn.sendall(f"ERROR Username '{username}' taken. Close.\n".encode("utf-8"))
                    conn.close()
                    return
                clients[username] = (conn, addr)
                call_state[username] = None

            print(f"[{self.timestamp()}] {username} connected from {addr}")
            self.broadcast(f"[{self.timestamp()}] SYSTEM: {username} joined.\n", exclude=username)
            conn.sendall("Welcome! Type /help for commands.\n".encode("utf-8"))

            while True:
                data = conn.recv(BUFFER)
                if not data:
                    break

                if data.startswith(b"FILE|"):
                    try:
                        header_end = data.index(b"\n")
                        header_bytes = data[:header_end+1]
                        rest = data[header_end+1:]
                    except ValueError:
                        buffer_acc = data
                        while b"\n" not in buffer_acc:
                            part = conn.recv(BUFFER)
                            if not part:
                                break
                            buffer_acc += part
                        try:
                            header_end = buffer_acc.index(b"\n")
                            header_bytes = buffer_acc[:header_end+1]
                            rest = buffer_acc[header_end+1:]
                        except ValueError:
                            conn.sendall(b"ERROR malformed file header\n")
                            continue

                    header_text = header_bytes.decode("utf-8", errors="ignore").strip()
                    parts = header_text.split("|")
                    if len(parts) < 6:
                        conn.sendall(b"ERROR malformed file header\n")
                        continue
                    _, to_keyword, typ, target, filename, size_str = parts[:6]
                    try:
                        size = int(size_str)
                    except:
                        conn.sendall(b"ERROR invalid size in header\n")
                        continue

                    file_bytes_collected = rest
                    while len(file_bytes_collected) < size:
                        chunk = conn.recv(min(BUFFER, size - len(file_bytes_collected)))
                        if not chunk:
                            break
                        file_bytes_collected += chunk

                    forward_header = f"FILE|FROM|{username}|{filename}|{size}\n".encode("utf-8")

                    if typ.upper() == "USER":
                        success = self.forward_file_bytes(target, forward_header, [file_bytes_collected])
                        if success:
                            conn.sendall(f"[{self.timestamp()}] File sent to {target}\n".encode("utf-8"))
                        else:
                            conn.sendall(f"[{self.timestamp()}] User {target} not found/offline.\n".encode("utf-8"))
                    elif typ.upper() == "GROUP":
                        with lock:
                            members = groups.get(target, set()).copy()
                        if username not in members:
                            conn.sendall(f"You must be member of group {target} to send files.\n".encode("utf-8"))
                        else:
                            for m in members:
                                if m == username: continue
                                self.forward_file_bytes(m, forward_header, [file_bytes_collected])
                            conn.sendall(f"[{self.timestamp()}] File forwarded to group {target}\n".encode("utf-8"))
                    else:
                        conn.sendall(b"ERROR unknown file target type\n")

                else:
                    try:
                        text = data.decode("utf-8", errors="ignore").strip()
                    except:
                        text = ""

                    if not text:
                        continue

                    if text.startswith("/"):
                        parts = text.split(" ", 2)
                        cmd = parts[0].lower()