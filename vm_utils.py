import re
import os
import io
import json
import paramiko
import logging
import mysql.connector
from datetime import datetime, timedelta
from threading import Lock

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "jwdb",
    "port": "3307"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VMMonitor:
    def __init__(self):
        self.vm_stats_cache = {}
        self.cache_lock = Lock()
        self.CACHE_DURATION = timedelta(minutes=5)
        
    def get_context(user_id, key):
        return context.get(f"{user_id}:{key}")

    def update_context(user_id, key, value):
        context.set(f"{user_id}:{key}", value)


    def process_chatbot_message(self, message):
        message = message.lower().strip()

        # Commande : images vm <label>
        match = re.match(r"images\s+vm\s+(\S+)", message)
        if match:
            label = match.group(1)
            return self.get_docker_images(label)

        # Commande : logs conteneur <nom> vm <label>
        match = re.match(r"logs\s+conteneur\s+(\S+)\s+vm\s+(\S+)", message)
        if match:
            container, label = match.group(1), match.group(2)
            return self.get_container_logs(label, container)

        # Commande : conteneurs actifs vm <label>
        match = re.match(r"conteneurs\s+actifs\s+vm\s+(\S+)", message)
        if match:
            label = match.group(1)
            return self.get_running_containers(label)

        # Commande : conteneurs arrêtés vm <label>
        match = re.match(r"conteneurs\s+arr(ê|e)tés\s+vm\s+(\S+)", message)
        if match:
            label = match.group(2)
            return self.get_stopped_containers(label)

        # Commande : projets joget vm <label>
        match = re.match(r"projets\s+joget\s+vm\s+(\S+)", message)
        if match:
            label = match.group(1)
            return self.get_joget_projects(label)

        # Commande inconnue
        return {"status": "unknown", "message": "Commande non reconnue"}


    def get_joget_projects(self, label):
        """Liste les projets Joget dans tous les conteneurs joget d'une VM"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM not found", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info)

            # Lister les conteneurs joget
            list_containers_cmd = "sudo docker ps --format '{{.Names}}' | grep joget"
            containers_output = self._run_ssh_command(ssh, list_containers_cmd)
            containers = containers_output.strip().splitlines()

            all_projects = []

            for container in containers:
                container = container.strip()
                if not container:
                    continue

                list_projects_cmd = f"sudo docker exec {container} ls /opt/joget/wflow/app_src"
                projects_output = self._run_ssh_command(ssh, list_projects_cmd)
                projects = [p.strip() for p in projects_output.strip().splitlines() if p.strip()]

                all_projects.append({
                    "container": container,
                    "projects": projects
                })

            ssh.close()

            return {
                "vm": label,
                "joget_containers": all_projects,
                "status": "ok",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {"vm": label, "error": str(e), "status": "failed"}



    def start_container(self, label, container_name):
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM non trouvée", "status": "not_found"}
        try:
            ssh = self._connect_ssh(vm_info)
            output = self._run_ssh_command(ssh, f"sudo docker start {container_name}")
            ssh.close()
            return {"vm": label, "container": container_name, "message": output, "status": "started"}
        except Exception as e:
            return {"vm": label, "container": container_name, "error": str(e), "status": "failed"}

    def stop_container(self, label, container_name):
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM non trouvée", "status": "not_found"}
        try:
            ssh = self._connect_ssh(vm_info)
            output = self._run_ssh_command(ssh, f"sudo docker stop {container_name}")
            ssh.close()
            return {"vm": label, "container": container_name, "message": output, "status": "stopped"}
        except Exception as e:
            return {"vm": label, "container": container_name, "error": str(e), "status": "failed"}

    def get_container_logs(self, label, container_name, lines=100):
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM non trouvée", "status": "not_found"}
        try:
            ssh = self._connect_ssh(vm_info)
            output = self._run_ssh_command(ssh, f"sudo docker logs --tail {lines} {container_name}")
            ssh.close()
            return {"vm": label, "container": container_name, "logs": output, "status": "ok"}
        except Exception as e:
            return {"vm": label, "container": container_name, "error": str(e), "status": "failed"}

    def _get_vm_info_by_label(self, label):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT c_ip AS ip, c_port AS port, c_username AS username, 
                       c_auth_method AS auth_method, c_password AS password, 
                       c_ssh_key AS ssh_key, c_label AS label
                FROM app_fd_machines_virtuelles 
                WHERE c_label = %s
            """, (label,))
            vm_info = cursor.fetchone()
            conn.close()
            return vm_info
        except Exception as e:
            logger.error(f"Erreur base de données: {e}")
            return None

    def get_all_vms(self):
        """Récupère toutes les VMs depuis la base de données"""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT c_label AS label, c_ip AS ip, c_port AS port, 
                       c_username AS username, c_auth_method AS auth_method
                FROM app_fd_machines_virtuelles 
                ORDER BY c_label
            """)
            vms = cursor.fetchall()
            conn.close()
            
            # Ajouter le statut de base pour chaque VM
            for vm in vms:
                vm['status'] = 'unknown'
                vm['last_check'] = None
            
            return vms
        except Exception as e:
            logger.error(f"Erreur récupération VMs: {e}")
            return {"error": f"Erreur base de données: {str(e)}"}

    def _connect_ssh(self, vm_info, timeout=30):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_params = {
                "hostname": vm_info["ip"],
                "port": int(vm_info.get("port", 22)),
                "username": vm_info["username"],
                "timeout": timeout
            }

            if vm_info["auth_method"] == "ssh_key" and vm_info.get("ssh_key"):
                try:
                    pkey = paramiko.RSAKey.from_private_key(io.StringIO(vm_info["ssh_key"]))
                except paramiko.ssh_exception.SSHException:
                    try:
                        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(vm_info["ssh_key"]))
                    except paramiko.ssh_exception.SSHException:
                        pkey = paramiko.ECDSAKey.from_private_key(io.StringIO(vm_info["ssh_key"]))
                connect_params["pkey"] = pkey

            elif vm_info["auth_method"] == "password" and vm_info.get("password"):
                connect_params["password"] = vm_info["password"]
            else:
                raise Exception("Aucune méthode d'authentification valide trouvée")

            ssh.connect(**connect_params)
            return ssh
        except Exception as e:
            logger.error(f"Connexion SSH échouée: {e}")
            raise

    def _run_ssh_command(self, ssh, command, timeout=15):
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode().strip()
            if exit_status != 0:
                error_output = stderr.read().decode().strip()
                logger.warning(f"Commande échouée: {error_output}")
                return ""
            return output
        except Exception as e:
            logger.error(f"Erreur exécution commande '{command}': {e}")
            return ""

    def parse_cpu(self, raw):
        try:
            match = re.search(r'(\d+\.\d+)\s*us', raw)
            return float(match.group(1)) if match else 0.0
        except: 
            return 0.0

    def parse_ram(self, raw):
        try:
            lines = raw.strip().splitlines()
            mem_line = next((l for l in lines if l.lower().startswith("mem")), None)
            if not mem_line:
                return {}
            parts = mem_line.split()
            total = int(parts[1])
            used = int(parts[2])
            return {
                "total_mb": total,
                "used_mb": used,
                "free_mb": int(parts[3]),
                "usage_percent": round((used/total) * 100, 2) if total > 0 else 0
            }
        except Exception as e:
            logger.error(f"Erreur parsing RAM: {e}")
            return {}

    def parse_disk(self, raw):
        try:
            lines = raw.strip().splitlines()
            if len(lines) < 2:
                return {}
            parts = lines[1].split()
            return {
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "use_percent": parts[4]
            }
        except Exception as e:
            logger.error(f"Erreur parsing disk: {e}")
            return {}

    def get_vm_stats(self, label, timeout=30):
        logger.info(f"Statistiques pour la VM: {label}")

        with self.cache_lock:
            if label in self.vm_stats_cache:
                entry = self.vm_stats_cache[label]
                if datetime.now() - entry["timestamp"] < self.CACHE_DURATION:
                    return entry["data"]

        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM non trouvée", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info, timeout)
            cpu_raw = self._run_ssh_command(ssh, "top -bn1 | grep '%Cpu'")
            ram_raw = self._run_ssh_command(ssh, "free -m")
            disk_raw = self._run_ssh_command(ssh, "df -h /")
            uptime_raw = self._run_ssh_command(ssh, "uptime")
            ssh.close()

            result = {
                "vm": label,
                "ip": vm_info.get("ip"),
                "cpu": self.parse_cpu(cpu_raw),
                "ram": self.parse_ram(ram_raw),
                "disk": self.parse_disk(disk_raw),
                "uptime": uptime_raw,
                "status": "connected",
                "timestamp": datetime.now().isoformat()
            }

            with self.cache_lock:
                self.vm_stats_cache[label] = {"data": result, "timestamp": datetime.now()}

            return result
        except Exception as e:
            return {"vm": label, "error": str(e), "status": "connection_failed"}

    def get_docker_containers(self, label):
        """Récupère tous les conteneurs Docker (en cours d'exécution et arrêtés)"""
        return self.get_docker_data(label, kind="containers")

    def get_docker_images(self, label):
        """Récupère toutes les images Docker"""
        return self.get_docker_data(label, kind="images")

    def get_container_stats(self, label):
        """Récupère les statistiques des conteneurs Docker en cours d'exécution"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM not found", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info)
            
            # Récupérer les conteneurs en cours d'exécution
            containers_cmd = "sudo docker ps --format '{{.Names}}'"
            containers_output = self._run_ssh_command(ssh, containers_cmd)
            
            if not containers_output:
                ssh.close()
                return {
                    "vm": label,
                    "containers_stats": [],
                    "status": "ok",
                    "message": "Aucun conteneur en cours d'exécution",
                    "timestamp": datetime.now().isoformat()
                }
            
            container_names = containers_output.strip().splitlines()
            stats_data = []
            
            for container_name in container_names:
                if not container_name.strip():
                    continue
                    
                try:
                    # Obtenir les stats pour ce conteneur
                    stats_cmd = f"sudo docker stats --no-stream --format 'table {{{{.Container}}}}\\t{{{{.CPUPerc}}}}\\t{{{{.MemUsage}}}}\\t{{{{.MemPerc}}}}\\t{{{{.NetIO}}}}\\t{{{{.BlockIO}}}}' {container_name}"
                    stats_output = self._run_ssh_command(ssh, stats_cmd)
                    
                    if stats_output:
                        lines = stats_output.strip().splitlines()
                        if len(lines) > 1:  # Skip header
                            parts = lines[1].split('\t')
                            if len(parts) >= 6:
                                stats_data.append({
                                    "container": parts[0],
                                    "cpu_percent": parts[1],
                                    "memory_usage": parts[2],
                                    "memory_percent": parts[3],
                                    "network_io": parts[4],
                                    "block_io": parts[5]
                                })
                except Exception as e:
                    logger.warning(f"Erreur stats pour conteneur {container_name}: {e}")
                    continue
            
            ssh.close()
            return {
                "vm": label,
                "containers_stats": stats_data,
                "status": "ok",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"vm": label, "error": str(e), "status": "failed"}

    def get_docker_data(self, label, kind="containers"):
        """Méthode générique pour récupérer les données Docker"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM not found", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info)
            
            if kind == "containers":
                cmd = "sudo docker ps -a --format '{{json .}}'"
            elif kind == "running":
                cmd = "sudo docker ps --format '{{json .}}'"
            elif kind == "images":
                cmd = "sudo docker images --format '{{json .}}'"
            else:
                raise ValueError(f"Type non supporté: {kind}")

            output = self._run_ssh_command(ssh, cmd)
            ssh.close()
            
            data = []
            if output:
                for line in output.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Erreur parsing JSON: {e} - Line: {line}")
                            continue
            
            return {
                "vm": label,
                "data": data,
                "count": len(data),
                "status": "ok",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération données Docker ({kind}) pour VM {label}: {e}")
            return {"vm": label, "error": str(e), "status": "failed"}

    def test_vm_connection(self, label):
        """Teste la connexion à une VM"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"status": "error", "message": "VM non trouvée"}
        
        try:
            ssh = self._connect_ssh(vm_info, timeout=10)
            test_output = self._run_ssh_command(ssh, 'echo "Connection test OK"')
            ssh.close()
            
            if "Connection test OK" in test_output:
                return {"status": "success", "message": "Connexion réussie"}
            else:
                return {"status": "error", "message": "Test de commande échoué"}
                
        except Exception as e:
            return {"status": "error", "message": f"Erreur de connexion: {str(e)}"}

    def clear_cache(self):
        """Vide le cache des statistiques"""
        with self.cache_lock:
            self.vm_stats_cache.clear()
        logger.info("Cache vidé")

    def get_cache_info(self):
        """Retourne des informations sur le cache"""
        with self.cache_lock:
            return {
                "size": len(self.vm_stats_cache),
                "entries": list(self.vm_stats_cache.keys()),
                "cache_duration_minutes": self.CACHE_DURATION.total_seconds() / 60
            }


    def get_running_containers(self, label):
        """Récupère uniquement les conteneurs Docker en cours d'exécution"""
        return self.get_docker_data(label, kind="running")


    def get_stopped_containers(self, label):
        """Récupère uniquement les conteneurs Docker arrêtés"""
        all_data = self.get_docker_data(label, kind="containers")
        if all_data.get("status") != "ok":
            return all_data

        running_data = self.get_docker_data(label, kind="running")
        running_names = set(c.get("Names") or c.get("Names", "").split()[0] for c in running_data.get("data", []))

        stopped = [c for c in all_data.get("data", []) if c.get("Names") not in running_names]
        return {
            "vm": label,
            "data": stopped,
            "count": len(stopped),
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        }

    def get_single_container_stats(self, label, container_name):
        """Récupère les stats CPU/RAM/IO pour un conteneur Docker spécifique"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM not found", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info)
            cmd = f"sudo docker stats --no-stream --format '{{{{.Container}}}}|{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}|{{{{.MemPerc}}}}|{{{{.NetIO}}}}|{{{{.BlockIO}}}}' {container_name}"
            output = self._run_ssh_command(ssh, cmd)
            ssh.close()

            if not output or '|' not in output:
                return {
                    "vm": label,
                    "container": container_name,
                    "status": "not_found",
                    "message": "Conteneur non trouvé ou aucune donnée"
                }

            parts = output.strip().split('|')
            if len(parts) != 6:
                return {
                    "vm": label,
                    "container": container_name,
                    "status": "parse_error",
                    "message": "Format de sortie inattendu",
                    "raw_output": output
                }

            return {
                "vm": label,
                "container": container_name,
                "cpu_percent": parts[1],
                "memory_usage": parts[2],
                "memory_percent": parts[3],
                "network_io": parts[4],
                "block_io": parts[5],
                "status": "ok",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Erreur stats conteneur {container_name} pour VM {label}: {e}")
            return {"vm": label, "container": container_name, "error": str(e), "status": "failed"}


    def get_active_container_resources(self, label):
        """Récupère CPU, RAM, disque des conteneurs actifs"""
        vm_info = self._get_vm_info_by_label(label)
        if not vm_info:
            return {"vm": label, "error": "VM not found", "status": "not_found"}

        try:
            ssh = self._connect_ssh(vm_info)
            cmd = "sudo docker stats --no-stream --format '{{json .}}'"
            output = self._run_ssh_command(ssh, cmd)
            ssh.close()

            stats = []
            if output:
                for line in output.splitlines():
                    try:
                        stats.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Erreur parsing stats JSON: {e} - Line: {line}")
                        continue

            return {
                "vm": label,
                "container_resources": stats,
                "count": len(stats),
                "status": "ok",
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Erreur récupération stats conteneurs pour VM {label}: {e}")
            return {"vm": label, "error": str(e), "status": "failed"}


