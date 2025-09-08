#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


class SystemdDashboard:
    def __init__(self, db_path="services.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT UNIQUE NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS service_toggles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                toggle_type TEXT NOT NULL,
                is_expanded BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(service_name, toggle_type)
            )
        """)
        conn.commit()
        conn.close()

    def get_tracked_services(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_name FROM tracked_services ORDER BY service_name"
        )
        services = [row[0] for row in cursor.fetchall()]
        conn.close()
        return services

    def add_service(self, service_name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO tracked_services (service_name) VALUES (?)",
                (service_name,),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def remove_service(self, service_name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM tracked_services WHERE service_name = ?", (service_name,)
        )
        conn.commit()
        conn.close()

    def get_service_status(self, service_name):
        try:
            result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            is_active = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            show_result = subprocess.run(
                [
                    "systemctl",
                    "show",
                    service_name,
                    "--property=MainPID,MemoryCurrent,CPUUsageNSec,ActiveEnterTimestamp,LoadState,UnitFileState",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            service_info = {
                "name": service_name,
                "status": result.stdout,
                "active": is_active.stdout.strip() == "active",
                "state": is_active.stdout.strip(),
                "memory": "N/A",
                "uptime": "N/A",
                "main_pid": "N/A",
                "load_state": "N/A",
                "unit_file_state": "N/A",
            }

            if show_result.returncode == 0:
                for line in show_result.stdout.strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if (
                            key == "MemoryCurrent"
                            and value != "[not set]"
                            and value.isdigit()
                        ):
                            memory_bytes = int(value)
                            if memory_bytes > 0:
                                service_info["memory"] = self._format_bytes(
                                    memory_bytes
                                )
                        elif key == "MainPID" and value != "0":
                            service_info["main_pid"] = value
                        elif key == "ActiveEnterTimestamp" and value:
                            service_info["uptime"] = self._calculate_uptime(value)
                        elif key == "LoadState":
                            service_info["load_state"] = value
                        elif key == "UnitFileState":
                            service_info["unit_file_state"] = value

            return service_info
        except subprocess.TimeoutExpired:
            return {
                "name": service_name,
                "status": "Timeout",
                "active": False,
                "state": "unknown",
                "memory": "N/A",
                "uptime": "N/A",
                "main_pid": "N/A",
                "load_state": "N/A",
                "unit_file_state": "N/A",
            }
        except Exception as e:
            return {
                "name": service_name,
                "status": f"Error: {e!s}",
                "active": False,
                "state": "error",
                "memory": "N/A",
                "uptime": "N/A",
                "main_pid": "N/A",
                "load_state": "N/A",
                "unit_file_state": "N/A",
            }

    def _format_bytes(self, bytes_val):
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f}TB"

    def _calculate_uptime(self, timestamp_str):
        try:
            if not timestamp_str or timestamp_str in ["", "n/a"]:
                return "N/A"

            import re
            from datetime import datetime

            timestamp_match = re.search(
                r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", timestamp_str
            )
            if not timestamp_match:
                return "N/A"

            start_time = datetime.strptime(
                timestamp_match.group(1), "%Y-%m-%d %H:%M:%S"
            )
            uptime_seconds = (datetime.now() - start_time).total_seconds()

            if uptime_seconds < 60:
                return f"{int(uptime_seconds)}s"
            elif uptime_seconds < 3600:
                return f"{int(uptime_seconds // 60)}m"
            elif uptime_seconds < 86400:
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                return f"{hours}h {minutes}m"
            else:
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                return f"{days}d {hours}h"
        except Exception:
            return "N/A"

    def control_service(self, service_name, action):
        try:
            result = subprocess.run(
                ["sudo", "systemctl", action, service_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Operation timed out"}
        except Exception as e:
            return {"success": False, "message": f"Error: {e!s}"}

    def get_service_logs(self, service_name, lines=50):
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return result.stderr or "Error getting logs"
            
            json_logs = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        log_entry = json.loads(line)
                        json_logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue
            
            return json_logs
        except Exception as e:
            return f"Error getting logs: {e!s}"

    def get_toggle_state(self, service_name, toggle_type="logs"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_expanded FROM service_toggles WHERE service_name = ? AND toggle_type = ?",
            (service_name, toggle_type),
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else False

    def set_toggle_state(self, service_name, toggle_type, is_expanded):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO service_toggles (service_name, toggle_type, is_expanded, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
            (service_name, toggle_type, is_expanded),
        )
        conn.commit()
        conn.close()

    def get_all_toggle_states(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_name, toggle_type, is_expanded FROM service_toggles"
        )
        results = cursor.fetchall()
        conn.close()

        toggle_states = {}
        for service_name, toggle_type, is_expanded in results:
            if service_name not in toggle_states:
                toggle_states[service_name] = {}
            toggle_states[service_name][toggle_type] = bool(is_expanded)

        return toggle_states

    def get_disk_usage(self):
        try:
            result = subprocess.run(
                ["df", "-h"], capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return {"error": "Failed to get disk usage"}

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return {"error": "Invalid df output"}

            lines[0].split()
            disk_usage = []

            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    filesystem = parts[0]
                    size = parts[1]
                    used = parts[2]
                    available = parts[3]
                    use_percent = parts[4].rstrip("%")
                    mounted_on = " ".join(parts[5:])

                    try:
                        use_percent_num = (
                            int(use_percent) if use_percent.isdigit() else 0
                        )
                    except (ValueError, TypeError):
                        use_percent_num = 0

                    disk_usage.append(
                        {
                            "filesystem": filesystem,
                            "size": size,
                            "used": used,
                            "available": available,
                            "use_percent": use_percent,
                            "use_percent_num": use_percent_num,
                            "mounted_on": mounted_on,
                        }
                    )

            disk_usage.sort(key=lambda x: x["use_percent_num"], reverse=True)
            return {"disks": disk_usage}

        except subprocess.TimeoutExpired:
            return {"error": "Disk usage check timed out"}
        except Exception as e:
            return {"error": f"Error getting disk usage: {e!s}"}

    def get_ram_usage(self):
        try:
            result = subprocess.run(
                ["free", "-h"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    mem_line = lines[1].split()
                    if len(mem_line) >= 7:
                        total = mem_line[1]
                        used = mem_line[2]
                        free = mem_line[3]
                        available = mem_line[6]

                        try:
                            total_kb = self._parse_memory_value(total)
                            used_kb = self._parse_memory_value(used)
                            use_percent = int((used_kb / total_kb) * 100) if total_kb > 0 else 0
                        except (ValueError, ZeroDivisionError):
                            use_percent = 0

                        return {
                            "total": total,
                            "used": used,
                            "free": free,
                            "available": available,
                            "use_percent": use_percent,
                        }

        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass

        # Fallback to /proc/meminfo if free command fails or is not available
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            mem_data = {}
            for line in meminfo.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    # Extract numeric value in kB
                    value_parts = value.strip().split()
                    if value_parts and value_parts[0].isdigit():
                        mem_data[key.strip()] = int(value_parts[0]) * 1024  # Convert kB to bytes

            if 'MemTotal' in mem_data:
                total_bytes = mem_data.get('MemTotal', 0)
                available_bytes = mem_data.get('MemAvailable', mem_data.get('MemFree', 0))
                free_bytes = mem_data.get('MemFree', 0)
                used_bytes = total_bytes - available_bytes

                total_formatted = self._format_bytes(total_bytes)
                used_formatted = self._format_bytes(used_bytes)
                free_formatted = self._format_bytes(free_bytes)
                available_formatted = self._format_bytes(available_bytes)

                use_percent = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0

                return {
                    "total": total_formatted,
                    "used": used_formatted,
                    "free": free_formatted,
                    "available": available_formatted,
                    "use_percent": use_percent,
                }

        except (IOError, OSError) as e:
            return {"error": f"Error reading memory info: {e!s}"}
        except Exception as e:
            return {"error": f"Error getting RAM usage: {e!s}"}
        
        return {"error": "Unable to determine RAM usage"}

    def _parse_memory_value(self, value):
        if value.endswith('T'):
            return float(value[:-1]) * 1024 * 1024 * 1024
        elif value.endswith('G'):
            return float(value[:-1]) * 1024 * 1024
        elif value.endswith('M'):
            return float(value[:-1]) * 1024
        elif value.endswith('K'):
            return float(value[:-1])
        else:
            return float(value) / 1024

    def _format_memory_kb(self, kb_value):
        if kb_value >= 1024 * 1024 * 1024:
            return f"{kb_value / (1024 * 1024 * 1024):.1f}T"
        elif kb_value >= 1024 * 1024:
            return f"{kb_value / (1024 * 1024):.1f}G"
        elif kb_value >= 1024:
            return f"{kb_value / 1024:.1f}M"
        else:
            return f"{kb_value:.1f}K"

    def get_full_journal(self, service_name):
        try:
            result = subprocess.run(
                ["journalctl", "-u", service_name, "--no-pager", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return result.stderr or "Error getting journal"
            
            json_logs = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        log_entry = json.loads(line)
                        json_logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue
            
            return json_logs
        except Exception as e:
            return f"Error getting journal: {e!s}"


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, dashboard_instance=None, base_url="/", **kwargs):
        self.dashboard = dashboard_instance
        self.base_url = base_url.rstrip('/')
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # Strip base_url from path if present
        if self.base_url and path.startswith(self.base_url):
            path = path[len(self.base_url):] or "/"

        if path == "/":
            self._serve_template()
        elif path == "/api/services":
            self._handle_get_services()
        elif path.startswith("/api/services/") and path.endswith("/logs"):
            service_name = path.split("/")[3]
            lines = int(query_params.get("lines", ["50"])[0])
            self._handle_get_logs(service_name, lines)
        elif path.startswith("/api/services/") and path.endswith("/journal"):
            service_name = path.split("/")[3]
            self._handle_get_journal(service_name)
        elif path == "/api/toggle-states":
            self._handle_get_toggle_states()
        elif path == "/api/disk-usage":
            self._handle_get_disk_usage()
        elif path == "/api/ram-usage":
            self._handle_get_ram_usage()
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        # Strip base_url from path if present
        if self.base_url and path.startswith(self.base_url):
            path = path[len(self.base_url):] or "/"

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(post_data) if post_data else {}
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        if path == "/api/services":
            self._handle_add_service(data)
        elif path == "/api/services/remove":
            self._handle_remove_service(data)
        elif path.startswith("/api/services/") and path.endswith("/control"):
            service_name = path.split("/")[3]
            self._handle_control_service(service_name, data)
        elif path.startswith("/api/services/") and path.endswith("/toggle"):
            service_name = path.split("/")[3]
            self._handle_set_toggle_state(service_name, data)
        else:
            self._send_error(404, "Not Found")

    def do_DELETE(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        # Strip base_url from path if present
        if self.base_url and path.startswith(self.base_url):
            path = path[len(self.base_url):] or "/"

        if path.startswith("/api/services/") and len(path.split("/")) == 4:
            service_name = path.split("/")[3]
            self._handle_remove_service_by_name(service_name)
        else:
            self._send_error(404, "Not Found")

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def _serve_template(self):
        template_path = Path(__file__).parent / "templates" / "index.html"
        try:
            with open(template_path, "r") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self._send_error(404, "Template not found")

    def _handle_get_services(self):
        services = self.dashboard.get_tracked_services()
        service_data = []
        for service in services:
            status = self.dashboard.get_service_status(service)
            service_data.append(status)
        self._send_json_response(service_data)

    def _handle_add_service(self, data):
        service_name = data.get("service_name")
        if not service_name:
            self._send_error(400, "Service name required")
            return

        success = self.dashboard.add_service(service_name)
        if success:
            self._send_json_response(
                {"success": True, "message": f"Added {service_name}"}
            )
        else:
            self._send_error(400, "Service already tracked")

    def _handle_remove_service(self, data):
        service_name = data.get("service_name")
        if not service_name:
            self._send_error(400, "Service name required")
            return

        self.dashboard.remove_service(service_name)
        self._send_json_response(
            {"success": True, "message": f"Stopped tracking {service_name}"}
        )

    def _handle_remove_service_by_name(self, service_name):
        self.dashboard.remove_service(service_name)
        self._send_json_response(
            {"success": True, "message": f"Stopped tracking {service_name}"}
        )

    def _handle_control_service(self, service_name, data):
        action = data.get("action")
        if action not in ["start", "stop", "restart"]:
            self._send_error(400, "Invalid action")
            return

        result = self.dashboard.control_service(service_name, action)
        self._send_json_response(result)

    def _handle_get_logs(self, service_name, lines):
        logs = self.dashboard.get_service_logs(service_name, lines)
        self._send_json_response({"logs": logs})

    def _handle_get_journal(self, service_name):
        journal = self.dashboard.get_full_journal(service_name)
        self._send_json_response({"journal": journal})

    def _handle_set_toggle_state(self, service_name, data):
        toggle_type = data.get("toggle_type", "logs")
        is_expanded = data.get("is_expanded", False)

        self.dashboard.set_toggle_state(service_name, toggle_type, is_expanded)
        self._send_json_response({"success": True})

    def _handle_get_toggle_states(self):
        toggle_states = self.dashboard.get_all_toggle_states()
        self._send_json_response(toggle_states)

    def _handle_get_disk_usage(self):
        disk_usage = self.dashboard.get_disk_usage()
        self._send_json_response(disk_usage)

    def _handle_get_ram_usage(self):
        ram_usage = self.dashboard.get_ram_usage()
        self._send_json_response(ram_usage)

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()


def create_handler(dashboard_instance, base_url="/"):
    def handler(*args, **kwargs):
        return DashboardRequestHandler(
            *args, dashboard_instance=dashboard_instance, base_url=base_url, **kwargs
        )

    return handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Systemd Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--config-dir", default=".", help="Directory for config files")
    parser.add_argument("--base-url", default="/", help="Base URL path")

    args = parser.parse_args()

    db_path = os.path.join(args.config_dir, "services.db")
    dashboard = SystemdDashboard(db_path)

    handler_class = create_handler(dashboard, args.base_url)
    httpd = HTTPServer((args.host, args.port), handler_class)

    print(f"Starting server on {args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()
