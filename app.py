# app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from vm_utils import VMMonitor
import logging
import paramiko
import socket
import io
from alerts.app_alerts import create_alerts_routes

# Initialize
monitor = VMMonitor()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
create_alerts_routes(app, monitor)

@app.route('/api/vm/<label>/joget-projects', methods=['GET'])
def api_get_joget_projects(label):
    try:
        data = monitor.get_joget_projects(label)
        return jsonify(data), 200 if data.get("status") == "ok" else 500
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des projets Joget pour VM {label} : {e}")
        return jsonify({"vm": label, "error": str(e), "status": "server_error"}), 500


@app.route('/api/vm/docker/container/start', methods=['POST'])
def api_start_container():
    label = request.headers.get("label")
    container_name = request.headers.get("container_name")

    if not label or not container_name:
        return jsonify({
            "error": "Missing 'label' or 'container_name' in headers",
            "status": "bad_request"
        }), 400

    result = monitor.start_container(label, container_name)
    return jsonify(result), 200 if result.get("status") == "started" else 500


@app.route('/api/vm/docker/container/stop', methods=['POST'])
def api_stop_container():
    label = request.headers.get("label")
    container_name = request.headers.get("container_name")

    if not label or not container_name:
        return jsonify({
            "error": "Missing 'label' or 'container_name' in headers",
            "status": "bad_request"
        }), 400

    result = monitor.stop_container(label, container_name)
    return jsonify(result), 200 if result.get("status") == "stopped" else 500


@app.route('/api/vm/docker/container/logs', methods=['GET'])
def api_get_container_logs():
    print("Headers:", dict(request.headers))
    label = request.headers.get("label")
    container_name = request.headers.get("container_name")
    lines = request.args.get("lines", 100)

    if not label or not container_name:
        return jsonify({
            "error": "Missing 'label' or 'container_name' in headers",
            "status": "bad_request"
        }), 400

    try:
        result = monitor.get_container_logs(label, container_name, lines)
        return jsonify([result]), 200 if result.get("status") == "ok" else 500
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des logs pour {container_name} sur {label}: {e}")
        return jsonify({
            "vm": label,
            "container": container_name,
            "error": str(e),
            "status": "server_error"
        }), 500


@app.route('/api/vms', methods=['GET'])
def api_get_all_vms():
    """Récupère toutes les VMs"""
    try:
        vms = monitor.get_all_vms()
        if isinstance(vms, dict) and "error" in vms:
            return jsonify(vms), 500
        return jsonify({
            "total": len(vms), 
            "vms": vms, 
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in api_get_all_vms: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/vm/stats', methods=['GET'])
def api_get_vm_stats():
    """Récupère les statistiques d'une VM via un header"""
    label = request.headers.get('label')
    if not label:
        return jsonify({
            "error": "Missing 'label' in headers",
            "status": "bad_request"
        }), 400

    try:
        timeout = request.args.get('timeout', 30, type=int)
        stats = monitor.get_vm_stats(label, timeout=timeout)
        
        if isinstance(stats, dict) and "error" in stats:
            status_code = 404 if stats.get("status") == "not_found" else 500
            return jsonify(stats), status_code
            
        return jsonify([stats]), 200
    except Exception as e:
        logger.error(f"Error getting VM stats for {label}: {e}")
        return jsonify({
            "vm": label,
            "error": str(e),
            "status": "server_error"
        }), 500

@app.route('/api/vm/<label>/docker/containers', methods=['GET'])
def api_get_vm_containers(label):
    """Récupère les conteneurs Docker d'une VM"""
    try:
        containers = monitor.get_docker_containers(label)
        
        if isinstance(containers, dict) and "error" in containers:
            status_code = 404 if containers.get("status") == "not_found" else 500
            return jsonify(containers), status_code
            
        return jsonify(containers)
    except Exception as e:
        logger.error(f"Error getting containers for VM {label}: {e}")
        return jsonify({"vm": label, "error": str(e), "status": "server_error"}), 500

@app.route('/api/vm/docker/images', methods=['GET'])
def api_get_vm_images():
    label = request.headers.get('label')
    if not label:
        return jsonify({
            "images": [],
            "error": "Missing 'label' in headers",
            "status": "bad_request"
        }), 400

    try:
        images = monitor.get_docker_images(label)
        
        if isinstance(images, dict) and "error" in images:
            status_code = 404 if images.get("status") == "not_found" else 500
            return jsonify(images), status_code
            
        return jsonify(images), 200
    except Exception as e:
        logger.error(f"Error getting images for VM {label}: {e}")
        return jsonify({
            "vm": label,
            "error": str(e),
            "status": "server_error"
        }), 500



@app.route('/api/vm/<label>/docker/container-stats', methods=['GET'])
def api_get_container_stats(label):
    try:
        stats = monitor.get_container_stats(label)
        if isinstance(stats, dict) and "error" in stats:
            status_code = 404 if stats.get("status") == "not_found" else 500
            return jsonify(stats), status_code
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting container stats for VM {label}: {e}")
        return jsonify({"vm": label, "error": str(e), "status": "server_error"}), 500


@app.route('/api/vm/docker/container/stats', methods=['GET'])
def api_get_single_container_stats():
    # Essayer d'abord les paramètres de requête, puis les headers en fallback
    # if (label = request.args.get("label") or request.headers.get("label")) 
    print("Headers:", dict(request.headers))  # Affiche les headers en tant que dictionnaire lisible

    label = dict(request.headers.get("label")) if request.args.get("label") is not None else request.headers.get("label")

    print("Label (from args or headers):", label)

   
    Container_Name = request.args.get("Container-Name") or request.headers.get("Container-Name")

    if not label or not Container_Name:
        return jsonify({
            "error": "Missing 'label' or 'Container-Name' in query parameters or headers", 
            "status": "bad_request",
            "usage": "Use: /api/vm/docker/container/stats?label=pipeline-ci&container_name=joget"
        }), 400

    try:
        data = monitor.get_single_container_stats(label, Container_Name)
        return jsonify([data]), 200 if data.get("status") == "ok" else 404
    except Exception as e:
        logger.error(f"Erreur API container stats pour {container_name} sur VM {label}: {e}")
        return jsonify({"vm": label, "container": container_name, "error": str(e)}), 500


@app.route('/api/vm/docker/running', methods=['GET'])
def api_get_running_containers():
    label = request.headers.get('label')
    if not label:
        return jsonify({
    "data": [
        {
            "Command": "",
            "CreatedAt": "",
            "ID": "",
            "Image": "",
            "Labels": "",
            "LocalVolumes": "",
            "Mounts": "",
            "Names": "",
            "Networks": "",
            "Ports": "",
            "RunningFor": "",
            "Size": "",
            "State": "",
            "Status": ""
        }
    ]
}), 400

    try:
        data = monitor.get_running_containers(label)
        return jsonify(data), 200 if data.get("status") == "ok" else 404
    except Exception as e:
        logger.error(f"Error getting running containers for VM {label}: {e}")
        return jsonify([{"vm": label, "error": str(e), "status": "server_error"}]), 500
"""
@app.route('/api/vm/<label>/docker/stopped', methods=['GET'])
def api_get_stopped_containers(label):
    try:
        data = monitor.get_stopped_containers(label)
        return jsonify(data), 200 if data.get("status") == "ok" else 404
    except Exception as e:
        logger.error(f"Error getting stopped containers for VM {label}: {e}")
        return jsonify({"vm": label, "error": str(e), "status": "server_error"}), 500
"""

@app.route('/api/vm/docker/stopped', methods=['GET'])
def api_get_stopped_containers():
    label = request.headers.get('label')
    if not label:
        return jsonify({
            "data": [
                {
                    "Command": "",
                    "CreatedAt": "",
                    "ID": "",
                    "Image": "",
                    "Labels": "",
                    "LocalVolumes": "",
                    "Mounts": "",
                    "Names": "",
                    "Networks": "",
                    "Ports": "",
                    "RunningFor": "",
                    "Size": "",
                    "State": "",
                    "Status": ""
                }
            ],
            "error": "Missing label in headers"
        }), 400

    try:
        data = monitor.get_stopped_containers(label)
        return jsonify(data), 200 if data.get("status") == "ok" else 404
    except Exception as e:
        logger.error(f"Error getting stopped containers for VM {label}: {e}")
        return jsonify({
            "vm": label,
            "error": str(e),
            "status": "server_error"
        }), 500


@app.route('/api/vm/<label>/docker/resources', methods=['GET'])
def api_get_container_resources(label):
    try:
        data = monitor.get_active_container_resources(label)
        return jsonify(data), 200 if data.get("status") == "ok" else 404
    except Exception as e:
        logger.error(f"Error getting container resources for VM {label}: {e}")
        
@app.route('/api/vm/<label>/test', methods=['GET'])
def api_test_vm_connection(label):
    """Teste la connexion à une VM"""
    try:
        result = monitor.test_vm_connection(label)
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify({"vm": label, **result}), status_code
    except Exception as e:
        logger.error(f"Error testing VM connection for {label}: {e}")
        return jsonify({"vm": label, "status": "error", "message": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Vérification de l'état de santé de l'API"""
    try:
        cache_info = monitor.get_cache_info()
        return jsonify({
            "status": "healthy", 
            "timestamp": datetime.now().isoformat(), 
            "cache": cache_info,
            "version": "1.0.0"
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Vide le cache"""
    try:
        monitor.clear_cache()
        return jsonify({
            "message": "Cache cleared successfully", 
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/cache/info', methods=['GET'])
def get_cache_info():
    """Informations sur le cache"""
    try:
        cache_info = monitor.get_cache_info()
        return jsonify({
            "cache": cache_info,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting cache info: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/vm/validate', methods=['POST'])
def validate_vm_credentials():
    """Valide les credentials SSH d'une VM"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "message": "Aucune donnée JSON fournie"
            }), 400

        # Vérification des champs obligatoires
        required_fields = ['ip', 'username', 'auth_method']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({
                "status": "error",
                "message": f"Champs requis manquants: {', '.join(missing_fields)}"
            }), 400

        ip = data["ip"]
        port = int(data.get("port", 22))
        username = data["username"]
        auth_method = data["auth_method"]
        password = data.get("password")
        ssh_key = data.get("ssh_key")

        logger.info(f"Tentative de validation SSH pour {username}@{ip}:{port}")

        connect_params = {
            "hostname": ip,
            "port": port,
            "username": username,
            "timeout": 10,
            "banner_timeout": 10
        }

        # Préparer la clé ou le mot de passe
        if auth_method == "ssh_key" and ssh_key:
            try:
                for key_class in [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey]:
                    try:
                        pkey = key_class.from_private_key(io.StringIO(ssh_key))
                        connect_params["pkey"] = pkey
                        break
                    except paramiko.ssh_exception.SSHException:
                        continue
                else:
                    return jsonify({
                        "status": "error",
                        "message": "Format de clé SSH non supporté"
                    }), 400
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"Erreur lors du traitement de la clé SSH : {str(e)}"
                }), 400

        elif auth_method == "password" and password:
            connect_params["password"] = password
        else:
            return jsonify({
                "status": "error",
                "message": "Méthode d'authentification ou credentials manquants"
            }), 400

        # Connexion SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(**connect_params)

        stdin, stdout, stderr = ssh.exec_command('echo "SSH OK"', timeout=5)
        output = stdout.read().decode().strip()
        error_output = stderr.read().decode().strip()
        ssh.close()

        if output == "SSH OK":
            return jsonify({
                "status": "success",
                "message": "Connexion SSH validée avec succès"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": f"Échec du test de commande SSH: {error_output or 'Aucune sortie'}"
            }), 400

    except paramiko.AuthenticationException:
        return jsonify({
            "status": "error",
            "message": "Échec de l'authentification SSH - Vérifiez vos credentials"
        }), 401
    except paramiko.SSHException as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur SSH: {str(e)}"
        }), 400
    except socket.timeout:
        return jsonify({
            "status": "error",
            "message": "Timeout de connexion - Vérifiez l'IP et le port"
        }), 408
    except socket.gaierror:
        return jsonify({
            "status": "error",
            "message": "Impossible de résoudre l'adresse IP"
        }), 400
    except ConnectionRefusedError:
        return jsonify({
            "status": "error",
            "message": "Connexion refusée - Vérifiez que SSH est actif sur la VM"
        }), 400
    except Exception as e:
        logger.error(f"Erreur dans validate_vm_credentials: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Erreur de connexion: {str(e)}"
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting Flask server on http://0.0.0.0:5050")
    app.run(host='0.0.0.0', port=5050, debug=True)