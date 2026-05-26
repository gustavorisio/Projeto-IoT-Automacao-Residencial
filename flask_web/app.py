from threading import Lock

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
import paho.mqtt.client as mqtt


app = Flask(__name__)
app.secret_key = "dev"

# MQTT settings (match firmware)
MQTT_BROKER = "6732ba7fb9bf481da315e7a247a59011.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "admin"
MQTT_PASSWORD = "Teste@123"

TOPIC_GAS_THRESHOLD_SET = "residencia/gas/threshold/set"

DEVICES = [
    {
        "key": "sala",
        "label": "Sala",
        "status_topic": "residencia/sala/status",
        "cmd_topic": "residencia/sala/comando",
    },
    {
        "key": "ar",
        "label": "Ar Condicionado",
        "status_topic": "residencia/ar/status",
        "cmd_topic": "residencia/ar/comando",
    },
    {
        "key": "cozinha",
        "label": "Cozinha",
        "status_topic": "residencia/cozinha/status",
        "cmd_topic": "residencia/cozinha/comando",
    },
]

state_lock = Lock()
latest_state = {
    "temperatura": "--",
    "umidade": "--",
    "luminosidade": "--",
    "gas": "--",
    "gas_alerta": False,
    "gas_threshold": 2000,
    "portao": "FECHADO",
    "status": {"sala": False, "ar": False, "cozinha": False},
}


def on_connect(client, userdata, flags, reason_code=None, properties=None):
    topics = [
        ("residencia/sensores/temperatura", 0),
        ("residencia/sensores/umidade", 0),
        ("residencia/sensores/luminosidade", 0),
        ("residencia/sensores/gas", 0),
        ("residencia/sensores/gas_alerta", 0),
        ("residencia/portao/status", 0),
        ("residencia/sala/status", 0),
        ("residencia/ar/status", 0),
        ("residencia/cozinha/status", 0),
        ("residencia/gas/threshold", 0),
    ]
    for topic, qos in topics:
        client.subscribe(topic, qos)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode(errors="ignore").strip()

    with state_lock:
        if topic.endswith("temperatura"):
            latest_state["temperatura"] = payload
        elif topic.endswith("umidade"):
            latest_state["umidade"] = payload
        elif topic.endswith("luminosidade"):
            latest_state["luminosidade"] = payload
        elif topic.endswith("gas") and not topic.endswith("gas_alerta"):
            latest_state["gas"] = payload
        elif topic.endswith("gas_alerta"):
            latest_state["gas_alerta"] = payload.upper() in ("1", "TRUE", "ON", "ALERTA")
        elif topic.endswith("portao/status"):
            latest_state["portao"] = payload
        elif topic.endswith("threshold"):
            try:
                latest_state["gas_threshold"] = int(payload)
            except ValueError:
                pass
        elif topic.endswith("sala/status"):
            latest_state["status"]["sala"] = payload.upper() in ("LIGADO", "ON", "1")
        elif topic.endswith("ar/status"):
            latest_state["status"]["ar"] = payload.upper() in ("LIGADO", "ON", "1")
        elif topic.endswith("cozinha/status"):
            latest_state["status"]["cozinha"] = payload.upper() in ("LIGADO", "ON", "1")


def build_view():
    with state_lock:
        snapshot = {
            "temperatura": latest_state["temperatura"],
            "umidade": latest_state["umidade"],
            "luminosidade": latest_state["luminosidade"],
            "gas": latest_state["gas"],
            "gas_alerta": latest_state["gas_alerta"],
            "gas_threshold": latest_state["gas_threshold"],
            "portao": latest_state["portao"],
            "status": dict(latest_state["status"]),
        }

    cards = []
    for device in DEVICES:
        key = device["key"]
        is_on = snapshot["status"].get(key, False)
        cards.append(
            {
                "key": key,
                "label": device["label"],
                "status_topic": device["status_topic"],
                "is_on": is_on,
                "status": "LIGADO" if is_on else "DESLIGADO",
            }
        )

    return {
        "temperatura": snapshot["temperatura"],
        "umidade": snapshot["umidade"],
        "luminosidade": snapshot["luminosidade"],
        "gas": snapshot["gas"],
        "gas_alerta": snapshot["gas_alerta"],
        "gas_threshold": snapshot["gas_threshold"],
        "portao": snapshot["portao"],
        "cards": cards,
    }


def create_mqtt_client():
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        mqtt_client = mqtt.Client()

    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    try:
        mqtt_client.tls_set()
    except Exception:
        pass

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception:
        pass

    return mqtt_client


client = create_mqtt_client()


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", view=build_view())


@app.get("/api/state")
def api_state():
    return jsonify(build_view())


@app.route("/device/<device>/<action>", methods=["POST"])
def device_control(device, action):
    dev = next((item for item in DEVICES if item["key"] == device), None)
    if not dev:
        flash("Dispositivo desconhecido")
        return redirect(url_for("index"))

    payload = "LIGAR" if action == "on" else "DESLIGAR"
    try:
        client.publish(dev["cmd_topic"], payload)
        flash(f"Comando enviado: {dev['label']} -> {payload}")
    except Exception:
        flash("Falha ao enviar comando MQTT")
    return redirect(url_for("index"))


@app.route("/portao/<action>", methods=["POST"], endpoint="portao_control")
def portao_control(action):
    payload = "ABRIR" if action == "open" else "FECHAR"
    try:
        client.publish("residencia/portao/comando", payload)
        flash(f"Comando portao: {payload}")
    except Exception:
        flash("Falha ao enviar comando do portao")
    return redirect(url_for("index"))


@app.route("/gas_threshold", methods=["POST"])
def gas_threshold():
    raw = request.form.get("threshold", "").strip()
    try:
        payload = str(int(raw))
    except Exception:
        payload = "OFF" if raw.upper() in ("OFF", "0") else raw

    try:
        client.publish(TOPIC_GAS_THRESHOLD_SET, payload)
        flash(f"Limite de gas atualizado: {payload}")
    except Exception:
        flash("Falha ao publicar novo limite de gas")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)