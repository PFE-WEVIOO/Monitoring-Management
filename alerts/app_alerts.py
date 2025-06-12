# app_alerts.py
from flask import Blueprint, request, jsonify
from alerts.alerts import (
    check_ram_alert, check_disk_alert,
    check_container_cpu_alert, check_container_ram_alert, check_container_disk_alert
)

import logging

logger = logging.getLogger(__name__)

def create_alerts_routes(app, monitor):
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    @app.route('/api/send-alert-email', methods=['GET'])
    def trigger_email_manually():
        try:
            alerts = []
            vms = monitor.get_all_vms()

            for vm in vms:
                label = vm["label"]

                alerts.append(check_ram_alert(monitor, label))
                alerts.append(check_disk_alert(monitor, label))

                try:
                    containers = monitor.get_vm_containers(label, container_type="running")
                    for container in containers:
                        name = container["Names"]
                        alerts.append(check_container_cpu_alert(monitor, label, name))
                        alerts.append(check_container_ram_alert(monitor, label, name))
                        alerts.append(check_container_disk_alert(monitor, label, name))
                except:
                    continue

            alerts = [a for a in alerts if a["status"] == "alert"]

            if not alerts:
                return jsonify({"status": "no_alerts", "message": "✅ Aucune alerte. Aucun mail envoyé."}), 200

            sender = "mouhamedtrabelsi.28@gmail.com"
            password = "bevh gcel deug hrkr"
            receiver = "mouhamedtrabelsi.28@gmail.com"

            message = MIMEMultipart("alternative")
            message["Subject"] = "🚨 Alertes système détectées"
            message["From"] = sender
            message["To"] = receiver

            text_content = "Voici les alertes détectées :\n\n"
            for alert in alerts:
                text_content += f"- {alert.get('message', 'Alerte inconnue')}\n"

            part = MIMEText(text_content, "plain")
            message.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls(context=context)
                server.login(sender, password)
                server.sendmail(sender, receiver, message.as_string())

            return jsonify({"status": "email_sent", "alerts_sent": len(alerts)}), 200

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/alerts', methods=['GET'])
    def get_all_alerts():
        alerts = []

        vms = monitor.get_all_vms()
        for vm in vms:
            label = vm["label"]

            # Alertes VM
            alerts.append(check_ram_alert(monitor, label))
            alerts.append(check_disk_alert(monitor, label))

            # Conteneurs actifs
            try:
                containers = monitor.get_vm_containers(label, container_type="running")
                for container in containers:
                    name = container["Names"]
                    alerts.append(check_container_cpu_alert(monitor, label, name))
                    alerts.append(check_container_ram_alert(monitor, label, name))
                    alerts.append(check_container_disk_alert(monitor, label, name))
            except:
                continue

        return jsonify({"alerts": alerts})

    @app.route('/api/vm/<label>/alerts/ram', methods=['GET'])
    def api_check_ram_alert(label):
        try:
            threshold = request.args.get('threshold', 40, type=int)
            alert = check_ram_alert(monitor, label, threshold)
            status_code = 200 if alert.get("status") in ["ok", "alert"] else 500
            return jsonify(alert), status_code
        except Exception as e:
            logger.error(f"Error checking RAM alert for VM {label}: {e}")
            return jsonify({"vm": label, "alert_type": "ram", "error": str(e)}), 500

    @app.route('/api/vm/<label>/alerts/disk', methods=['GET'])
    def api_check_disk_alert(label):
        try:
            threshold = request.args.get('threshold', 80, type=int)
            alert = check_disk_alert(monitor, label, threshold)
            status_code = 200 if alert.get("status") in ["ok", "alert"] else 500
            return jsonify(alert), status_code
        except Exception as e:
            logger.error(f"Error checking disk alert for VM {label}: {e}")
            return jsonify({"vm": label, "alert_type": "disk", "error": str(e)}), 500

    @app.route('/api/vm/<label>/alerts/container/<container_name>/cpu', methods=['GET'])
    def api_check_container_cpu_alert(label, container_name):
        try:
            threshold = request.args.get('threshold', 80, type=int)
            alert = check_container_cpu_alert(monitor, label, container_name, threshold)
            status_code = 200 if alert.get("status") in ["ok", "alert"] else 500
            return jsonify(alert), status_code
        except Exception as e:
            logger.error(f"Error checking CPU alert for container {container_name} on VM {label}: {e}")
            return jsonify({
                "vm": label,
                "container": container_name,
                "alert_type": "container_cpu",
                "error": str(e)
            }), 500

    @app.route('/api/vm/<label>/alerts/container/<container_name>/ram', methods=['GET'])
    def api_check_container_ram_alert(label, container_name):
        try:
            threshold = request.args.get('threshold', 80, type=int)
            alert = check_container_ram_alert(monitor, label, container_name, threshold)
            status_code = 200 if alert.get("status") in ["ok", "alert"] else 500
            return jsonify(alert), status_code
        except Exception as e:
            logger.error(f"Error checking RAM alert for container {container_name} on VM {label}: {e}")
            return jsonify({
                "vm": label,
                "container": container_name,
                "alert_type": "container_ram",
                "error": str(e)
            }), 500

    @app.route('/api/vm/<label>/alerts/container/<container_name>/disk', methods=['GET'])
    def api_check_container_disk_alert(label, container_name):
        try:
            threshold = request.args.get('threshold', 80, type=int)
            alert = check_container_disk_alert(monitor, label, container_name, threshold)
            status_code = 200 if alert.get("status") in ["ok", "alert"] else 500
            return jsonify(alert), status_code
        except Exception as e:
            logger.error(f"Error checking disk alert for container {container_name} on VM {label}: {e}")
            return jsonify({
                "vm": label,
                "container": container_name,
                "alert_type": "container_disk",
                "error": str(e)
            }), 500
