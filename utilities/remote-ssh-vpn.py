# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import select
import socketserver
import threading
import time
import sys
import logging
import socket
import paramiko

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ForwardServer(socketserver.ThreadingTCPServer):
    """
    Custom ThreadingTCPServer that allows address reuse and 
    keeps track of SSH transport and remote targets.
    """
    daemon_threads = True
    allow_reuse_address = True

class ForwardHandler(socketserver.BaseRequestHandler):
    """
    Handles incoming connections to the local port and tunnels them 
    through the SSH connection to the remote destination.
    """
    def handle(self):
        # Save peername before any operations that might close the socket
        try:
            peer_name = self.request.getpeername()
        except Exception:
            peer_name = ("unknown", 0)

        chan = None
        try:
            # Request a port forwarding channel from the SSH server
            chan = self.server.ssh_transport.open_channel(
                "direct-tcpip",
                (self.server.chain_host, self.server.chain_port),
                peer_name,
            )
        except Exception as e:
            logging.error(f"Incoming request to {self.server.chain_host}:{self.server.chain_port} failed: {e}")
            return

        if chan is None:
            logging.error(f"Incoming request to {self.server.chain_host}:{self.server.chain_port} was rejected by the SSH server.")
            return

        logging.debug(f"Tunnel open: {peer_name} -> local:{self.server.server_address[1]} -> remote:{self.server.chain_host}:{self.server.chain_port}")
        
        try:
            # Bridge the local socket and the SSH channel
            while True:
                # Use select with a 5-second timeout to allow periodic health checks
                r, w, x = select.select([self.request, chan], [], [], 5.0)
                if not r:
                    # Check if the transport underlying the channel is still alive
                    if not self.server.ssh_transport.is_active():
                        break
                    continue

                if self.request in r:
                    data = self.request.recv(1024)
                    if len(data) == 0:
                        break
                    chan.sendall(data)
                if chan in r:
                    data = chan.recv(1024)
                    if len(data) == 0:
                        break
                    self.request.sendall(data)
        except Exception as e:
            logging.debug(f"Tunnel exception on connection {peer_name}: {e}")
        finally:
            if chan:
                try:
                    chan.close()
                except Exception:
                    pass
            try:
                self.request.close()
            except Exception:
                pass
            logging.debug(f"Tunnel closed: {peer_name}")


def keep_alive_monitor(client, interval, stop_event, error_event):
    """
    Periodically sends a keep-alive message to the SSH server.
    If it fails, it triggers the error_event to initiate a reconnection.
    """
    logging.info(f"Keep-alive monitor started (Interval: {interval}s)")
    try:
        transport = client.get_transport()
        if not transport:
            error_event.set()
            return
        
        while not stop_event.is_set():
            # Wait for the interval, but allow quick interruption if stop_event is set
            stop_event.wait(interval)
            if stop_event.is_set():
                break
                
            try:
                if not transport.is_active():
                    raise socket.error("SSH transport is inactive.")
                # Send a global request to keep the connection alive
                transport.send_ignore()
                logging.debug("Keep-alive packet sent successfully.")
            except Exception as e:
                logging.error(f"Keep-alive failed, connection appears dead: {e}")
                error_event.set()
                break
    except Exception as e:
        logging.error(f"Keep-alive monitor exception: {e}")
        error_event.set()


def parse_forward_rule(rule):
    """Parses a forwarding rule string 'local_port:remote_host:remote_port'"""
    parts = rule.split(':')
    if len(parts) != 3:
        raise ValueError(f"Invalid forward rule format '{rule}'. Expected local_port:remote_host:remote_port")
    
    try:
        local_port = int(parts[0])
        remote_host = parts[1]
        remote_port = int(parts[2])
        return local_port, remote_host, remote_port
    except ValueError:
        raise ValueError(f"Ports must be integers in rule '{rule}'")


def run_client(args):
    """
    Main execution logic for establishing the SSH connection and setting up forwards.
    Returns True if successful and running, False if a critical error occurred.
    """
    client = paramiko.SSHClient()
    # Automatically add unknown host keys
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    servers = []
    stop_event = threading.Event()
    error_event = threading.Event()
    monitor_thread = None

    try:
        logging.info(f"Connecting to SSH server {args.user}@{args.host}:{args.port}...")
        
        # Determine authentication method
        connect_kwargs = {
            "hostname": args.host,
            "port": args.port,
            "username": args.user,
            "timeout": 15
        }
        if args.key:
            connect_kwargs["key_filename"] = args.key
        if args.password:
            connect_kwargs["password"] = args.password

        client.connect(**connect_kwargs)
        logging.info("SSH connection established successfully.")

        # Setup local port forwarding
        transport = client.get_transport()
        if transport is None:
            raise paramiko.SSHException("Failed to obtain SSH transport layer.")

        for rule in args.forward:
            local_port, remote_host, remote_port = parse_forward_rule(rule)
            
            # Create the server
            server = ForwardServer(('', local_port), ForwardHandler)
            # Inject required SSH parameters into the server instance so the handler can access them
            server.ssh_transport = transport
            server.chain_host = remote_host
            server.chain_port = remote_port
            
            servers.append(server)
            
            # Start the server in a background thread
            t = threading.Thread(target=server.serve_forever)
            t.daemon = True
            t.start()
            logging.info(f"Forwarding local port {local_port} to {remote_host}:{remote_port}")

        # Start the keep-alive monitor thread
        monitor_thread = threading.Thread(
            target=keep_alive_monitor, 
            args=(client, args.keep_alive, stop_event, error_event)
        )
        monitor_thread.daemon = True
        monitor_thread.start()

        # Monitor connection active state
        while not error_event.is_set():
            if not transport.is_active():
                logging.warning("SSH transport dropped active status.")
                error_event.set()
                break
            time.sleep(1)

        # If we reach here, connection dropped
        return False

    except paramiko.AuthenticationException:
        logging.error("Authentication failed. Please check your credentials.")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Shutting down...")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Connection error: {e}")
        return False
        
    finally:
        # Cleanup routine to allow fresh reconnect
        stop_event.set()
        
        # Shutdown and close port-forwarding sockets
        for server in servers:
            try:
                server.shutdown()
                server.server_close()
            except Exception as e:
                logging.debug(f"Error shutting down forwarding server: {e}")
        
        # Shut down SSH client cleanly
        try:
            client.close()
        except Exception as e:
            logging.debug(f"Error closing SSH client: {e}")
            
        # Join keep-alive thread
        if monitor_thread:
            monitor_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(
        description="Resilient SSH Port Forwarding CLI Client",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("host", help="SSH server hostname or IP address")
    parser.add_argument("-p", "--port", type=int, default=22, help="SSH server port (default: 22)")
    parser.add_argument("-u", "--user", required=True, help="SSH username")
    
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument("-k", "--key", help="Path to SSH private key file")
    auth_group.add_argument("--password", help="SSH password")
    
    parser.add_argument(
        "-L", "--forward", action="append", required=True,
        help="Local port forward rule. Format: local_port:remote_host:remote_port\n"
             "Can be specified multiple times. Example: -L 8080:127.0.0.1:80"
    )
    
    parser.add_argument("-K", "--keep-alive", type=int, default=30, help="Keep-alive interval in seconds (default: 30)")
    parser.add_argument("-R", "--retries", type=int, default=-1, help="Number of times to retry connecting if dropped. Set to -1 for infinite. (default: -1)")
    parser.add_argument("-D", "--delay", type=int, default=30, help="Initial delay in seconds between reconnect attempts. Increases by 10s on consecutive failures (default: 30)")

    args = parser.parse_args()

    attempts = 0
    max_retries = args.retries

    while True:
        start_time = time.time()
        success = run_client(args)
        duration = time.time() - start_time
        
        # If run_client returns, the connection dropped (or failed to establish)
        if success is False:
            # If the connection survived and stayed stable for at least 30 seconds,
            # we reset consecutive failures back to 0.
            if duration > 30:
                if attempts > 0:
                    logging.info("Connection was stable. Resetting backoff attempt counter.")
                attempts = 0

            if max_retries != -1 and attempts >= max_retries:
                logging.error(f"Maximum retry limit ({max_retries}) reached. Exiting.")
                sys.exit(1)
                
            # Wait time starts at args.delay (30s) and increases by 10s on each consecutive fail
            current_delay = args.delay + (attempts * 10)
            attempts += 1
            
            logging.warning(
                f"Connection dropped. Reconnecting in {current_delay} seconds... "
                f"(Attempt {attempts} of {'infinity' if max_retries == -1 else max_retries})"
            )
            time.sleep(current_delay)
        else:
            # Clean exit
            break

if __name__ == "__main__":
    main()