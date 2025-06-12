import re
import os
import io
import json
import paramiko
import logging
import mysql.connector
from vm_utils import VMMonitor
from datetime import datetime, timedelta
from threading import Lock
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart




def check_ram_alert(monitor, label, threshold_percent=40):
    """Vérifie si l'usage RAM dépasse le seuil"""
    try:
        stats = monitor.get_vm_stats(label)
        if stats.get("status") != "connected":
            return {"vm": label, "alert_type": "ram", "status": "vm_error", "message": "VM non accessible"}

        ram_info = stats.get("ram", {})
        if not ram_info.get("usage_percent"):
            return {"vm": label, "alert_type": "ram", "status": "no_data", "message": "Données RAM non disponibles"}

        current_usage = ram_info["usage_percent"]

        if current_usage > threshold_percent:
            return {
                "vm": label,
                "alert_type": "ram",
                "status": "alert",
                "current_usage": current_usage,
                "threshold": threshold_percent,
                "message": f"Alerte RAM: {current_usage}% > {threshold_percent}%",
                "ram_info": ram_info,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "vm": label,
                "alert_type": "ram",
                "status": "ok",
                "current_usage": current_usage,
                "threshold": threshold_percent,
                "message": f"RAM OK: {current_usage}% <= {threshold_percent}%",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {"vm": label, "alert_type": "ram", "status": "error", "message": str(e)}



def check_disk_alert(monitor, label, threshold_percent=80):
    """Vérifie si l'usage disque dépasse le seuil"""
    try:
        stats = monitor.get_vm_stats(label)
        if stats.get("status") != "connected":
            return {"vm": label, "alert_type": "disk", "status": "vm_error", "message": "VM non accessible"}

        disk_info = stats.get("disk", {})
        if not disk_info.get("use_percent"):
            return {"vm": label, "alert_type": "disk", "status": "no_data", "message": "Données disque non disponibles"}

        # Extraire le pourcentage (enlever le %)
        usage_str = disk_info["use_percent"].replace("%", "")
        current_usage = float(usage_str)

        if current_usage > threshold_percent:
            return {
                "vm": label,
                "alert_type": "disk",
                "status": "alert",
                "current_usage": current_usage,
                "threshold": threshold_percent,
                "message": f"Alerte disque: {current_usage}% > {threshold_percent}%",
                "disk_info": disk_info,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "vm": label,
                "alert_type": "disk",
                "status": "ok",
                "current_usage": current_usage,
                "threshold": threshold_percent,
                "message": f"Disque OK: {current_usage}% <= {threshold_percent}%",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {"vm": label, "alert_type": "disk", "status": "error", "message": str(e)}


def check_container_cpu_alert(monitor, label, container_name, threshold_percent=80):
    """Vérifie si le CPU d'un conteneur dépasse le seuil"""
    try:
        container_stats = monitor.get_single_container_stats(label, container_name)
        if container_stats.get("status") != "ok":
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_cpu",
                "status": "container_error",
                "message": f"Conteneur non accessible: {container_stats.get('message', 'Erreur inconnue')}"
            }

        cpu_percent_str = container_stats.get("cpu_percent", "0%").replace("%", "")
        current_cpu = float(cpu_percent_str)

        if current_cpu > threshold_percent:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_cpu",
                "status": "alert",
                "current_cpu": current_cpu,
                "threshold": threshold_percent,
                "message": f"Alerte CPU conteneur {container_name}: {current_cpu}% > {threshold_percent}%",
                "container_stats": container_stats,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_cpu",
                "status": "ok",
                "current_cpu": current_cpu,
                "threshold": threshold_percent,
                "message": f"CPU conteneur {container_name} OK: {current_cpu}% <= {threshold_percent}%",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "vm": label,
            "container": container_name,
            "alert_type": "container_cpu",
            "status": "error",
            "message": str(e)
        }

def check_container_ram_alert(monitor, label, container_name, threshold_percent=80):
    """Vérifie si la RAM d'un conteneur dépasse le seuil"""
    try:
        stats = monitor.get_single_container_stats(label, container_name)
        if stats.get("status") != "ok":
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_ram",
                "status": "container_error",
                "message": f"Conteneur non accessible: {stats.get('message', 'Erreur inconnue')}"
            }

        mem_percent_str = stats.get("memory_percent", "0%").replace("%", "")
        current_ram = float(mem_percent_str)

        if current_ram > threshold_percent:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_ram",
                "status": "alert",
                "current_ram": current_ram,
                "threshold": threshold_percent,
                "message": f"Alerte RAM conteneur {container_name}: {current_ram}% > {threshold_percent}%",
                "container_stats": stats,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_ram",
                "status": "ok",
                "current_ram": current_ram,
                "threshold": threshold_percent,
                "message": f"RAM conteneur {container_name} OK: {current_ram}% <= {threshold_percent}%",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "vm": label,
            "container": container_name,
            "alert_type": "container_ram",
            "status": "error",
            "message": str(e)
        }

def check_container_disk_alert(monitor, label, container_name, threshold_percent=80):
    """Vérifie si le disque d'un conteneur dépasse le seuil d'écriture/lecture"""
    try:
        stats = monitor.get_single_container_stats(label, container_name)
        if stats.get("status") != "ok":
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_disk",
                "status": "container_error",
                "message": f"Conteneur non accessible: {stats.get('message', 'Erreur inconnue')}"
            }

        # Exemple : stats["block_io"] = "1.23MB / 3.45MB"
        block_io = stats.get("block_io", "")
        if not block_io or "/" not in block_io:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_disk",
                "status": "no_data",
                "message": "Block I/O non disponible"
            }

        read_str, write_str = block_io.split("/")
        read_mb = parse_size_to_mb(read_str.strip())
        write_mb = parse_size_to_mb(write_str.strip())

        total_io = read_mb + write_mb

        if total_io > threshold_percent:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_disk",
                "status": "alert",
                "current_io_mb": total_io,
                "threshold_mb": threshold_percent,
                "message": f"Alerte disque conteneur {container_name}: {total_io:.2f}MB > {threshold_percent}MB",
                "container_stats": stats,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "vm": label,
                "container": container_name,
                "alert_type": "container_disk",
                "status": "ok",
                "current_io_mb": total_io,
                "threshold_mb": threshold_percent,
                "message": f"Disque conteneur {container_name} OK: {total_io:.2f}MB <= {threshold_percent}MB",
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        return {
            "vm": label,
            "container": container_name,
            "alert_type": "container_disk",
            "status": "error",
            "message": str(e)
        }

def parse_size_to_mb(size_str):
    """Convertit une taille (comme 1.2kB, 2MB, 500B) en MB"""
    size_str = size_str.upper()
    try:
        if size_str.endswith("MB"):
            return float(size_str.replace("MB", "").strip())
        elif size_str.endswith("KB"):
            return float(size_str.replace("KB", "").strip()) / 1024
        elif size_str.endswith("B"):
            return float(size_str.replace("B", "").strip()) / (1024 * 1024)
        else:
            return 0.0
    except:
        return 0.0
