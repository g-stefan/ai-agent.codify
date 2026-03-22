# Remote SSH VPN Utility (`remote-ssh-vpn.py`)

## Description
The `remote-ssh-vpn.py` script is a resilient, command-line SSH port-forwarding client built entirely in Python using the `paramiko` library. It acts as a lightweight "VPN" by tunneling local network traffic securely through an SSH connection to a remote destination network.

Unlike standard `ssh -L` commands which can silently drop or hang, this script is designed for high reliability in automated or background environments. It features:
1.  **Concurrent Tunneling:** Handles multiple simultaneous connections and multi-port forwarding rules.
2.  **Keep-Alive Monitoring:** Runs a dedicated background thread that actively pings the SSH server to ensure the connection isn't dropped by aggressive firewalls or NAT gateways.
3.  **Auto-Reconnection:** If the connection drops or the keep-alive monitor detects a failure, the script will automatically clean up the broken sockets and attempt to reconnect.

## Command-Line Options

The script requires arguments to specify the SSH connection details, authentication method, and at least one forwarding rule.

### Required Arguments
| Argument | Description |
| :--- | :--- |
| `host` | *Positional*: The SSH server hostname or IP address. |
| `-u`, `--user` | The username to authenticate with on the SSH server. |
| `-L`, `--forward` | The local port forwarding rule in the format `local_port:remote_host:remote_port`. You can specify this argument multiple times to forward multiple ports. |

### Authentication (Must provide exactly one)
| Argument | Description |
| :--- | :--- |
| `-k`, `--key` | Path to your SSH private key file (e.g., `~/.ssh/id_rsa`). |
| `--password` | The SSH password. *(Note: Using keys is strongly recommended for automation).* |

### Optional Arguments
| Argument | Default | Description |
| :--- | :--- | :--- |
| `-p`, `--port` | `22` | The SSH server port. |
| `-K`, `--keep-alive` | `30` | The interval in seconds between sending keep-alive pings to the server. |
| `-R`, `--retries` | `5` | The maximum number of times to retry connecting if the connection drops. Set to `-1` for infinite retries. |
| `-D`, `--delay` | `5` | The delay in seconds between reconnection attempts. |
| `-h`, `--help`| | Shows the help message and exits. |

## Prerequisites
This script requires the `paramiko` library to handle SSH protocols:
```sh
pip install paramiko
```

## Exit Codes
*   **`0` (Success)**: The script was cleanly interrupted by the user (e.g., via `Ctrl+C`).
*   **`1` (Error)**: The script failed to authenticate, or the connection dropped and the maximum number of retry attempts was reached.

## Examples

### 1. Basic Local Port Forwarding (Password)
Forward local port `8080` to an internal web server `192.168.1.50:80` accessible only from the SSH host:
```sh
python remote-ssh-vpn.py bastion.example.com -u myuser --password "supersecret" -L 8080:192.168.1.50:80
```
*You can now open `http://localhost:8080` in your browser.*

### 2. Multiple Forwarding Rules (SSH Key)
Forward a database port and a web port simultaneously using an SSH key for authentication:
```sh
python remote-ssh-vpn.py 10.0.0.5 -u admin -k ~/.ssh/id_ed25519 \
  -L 3306:127.0.0.1:3306 \
  -L 9000:127.0.0.1:9000
```

### 3. Highly Resilient "Always-On" Tunnel
Create an infinite-retry tunnel with aggressive keep-alives (every 15 seconds) that reconnects instantly (1-second delay) if dropped:
```sh
python remote-ssh-vpn.py vpn.company.com -u service_account -k /secure/keys/svc.pem \
  -L 5432:db.internal:5432 \
  --keep-alive 15 \
  --retries -1 \
  --delay 1
```