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
        
        # Bridge the local socket and the SSH channel
        while True:
            r, w, x = select.select([self.request, chan], [], [])
            if self.request in r:
                data = self.request.recv(1024)
                if len(data) == 0:
                    break
                chan.send(data)
            if chan in r:
                data = chan.recv(1024)
                if len(data) == 0:
                    break
                self.request.send(data)
                
        chan.close()
        self.request.close()
        logging.debug(f"Tunnel closed: {peer_name}")


def keep_alive_monitor(client, interval, stop_event, error_event):
    """
    Periodically sends a keep-alive message to the SSH server.
    If it fails, it triggers the error_event to initiate a reconnection.
    """
    logging.info(f"Keep-alive monitor started (Interval: {interval}s)")
    transport = client.get_transport()
    
    while not stop_event.is_set():
        # Wait for the interval, but allow quick interruption if stop_event is set
        stop_event.wait(interval)
        if stop_event.is_set():
            break
            
        try:
            # Send a global request to keep the connection alive
            # This is more lightweight than executing a full shell command
            transport.send_ignore()
            logging.debug("Keep-alive packet sent successfully.")
        except Exception as e:
            logging.error(f"Keep-alive failed, connection appears dead: {e}")
            error_event.set()
            break


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
    # Automatically add unknown host keys (Note: in high security envs, you might want to remove this)
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

        # Main thread simply waits for an error (connection drop) or a KeyboardInterrupt
        while not error_event.is_set():
            time.sleep(1)

        # If we reach here, error_event was set by the monitor thread
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
        # Cleanup routine
        stop_event.set()
        for server in servers:
            server.shutdown()
            server.server_close()
        client.close()
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
    parser.add_argument("-R", "--retries", type=int, default=5, help="Number of times to retry connecting if dropped. Set to -1 for infinite. (default: 5)")
    parser.add_argument("-D", "--delay", type=int, default=5, help="Delay in seconds between reconnect attempts (default: 5)")

    args = parser.parse_args()

    attempts = 0
    max_retries = args.retries

    while True:
        success = run_client(args)
        
        # If run_client returns, the connection dropped (or failed to establish)
        if success is False:
            if max_retries != -1 and attempts >= max_retries:
                logging.error(f"Maximum retry limit ({max_retries}) reached. Exiting.")
                sys.exit(1)
                
            attempts += 1
            logging.warning(f"Connection dropped. Reconnecting in {args.delay} seconds... (Attempt {attempts} of {'infinity' if max_retries == -1 else max_retries})")
            time.sleep(args.delay)
        else:
            # Should only happen on clean exit
            break

if __name__ == "__main__":
    main()