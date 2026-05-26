from flask import Flask, render_template, request, redirect, url_for, flash
import paho.mqtt.client as mqtt
import threading

app = Flask(__name__)
app.secret_key = "dev"

# MQTT settings (match firmware)
MQTT_BROKER = "6732ba7fb9bf481da315e7a247a59011.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "admin"
MQTT_PASSWORD = "Teste@123"

# Topics
TOPIC_GAS_THRESHOLD_SET = "residencia/gas/threshold/set"

# In-memory state
latest_state = {
    "temperatura": "--",
    "umidade": "--",
    "luminosidade": "--",
    "gas": 0,
    "gas_alerta": False,
    "gas_threshold": 2000,
    "portao": "FECHADO",
    "status": {
        "sala": False,
        "ar": False,
        "cozinha": False
    }
}

DEVICES = [
    {"key": "sala", "label": "Sala", "status_topic": "residencia/sala/status", "cmd_topic": "residencia/sala/comando"},
    {"key": "ar", "label": "Ar Condicionado", "status_topic": "residencia/ar/status", "cmd_topic": "residencia/ar/comando"},
    {"key": "cozinha", "label": "Cozinha", "status_topic": "residencia/cozinha/status", "cmd_topic": "residencia/cozinha/comando"}
]


def on_connect(client, userdata, flags, rc):
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
        ("residencia/gas/threshold", 0)
    ]
    for t, q in topics:
        client.subscribe(t)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode(errors="ignore")
    try:
        if topic.endswith("temperatura"):
            latest_state["temperatura"] = payload
        elif topic.endswith("umidade"):
            latest_state["umidade"] = payload
        elif topic.endswith("luminosidade"):
            latest_state["luminosidade"] = payload
        elif topic.endswith("gas") and not topic.endswith("gas_alerta"):
            latest_state["gas"] = int(payload)
        elif topic.endswith("gas_alerta"):
            latest_state["gas_alerta"] = payload in ("1", "True", "true", "ON", "1", "ALERTA")
        elif topic.endswith("portao/status"):
            latest_state["portao"] = payload
        elif topic.endswith("threshold"):
            try:
                latest_state["gas_threshold"] = int(payload)
            except Exception:
                pass
        # device status topics
        elif topic.endswith("sala/status"):
            latest_state["status"]["sala"] = payload.upper() in ("LIGADO", "ON", "1") or "LIGADO" in payload
        elif topic.endswith("ar/status"):
            latest_state["status"]["ar"] = payload.upper() in ("LIGADO", "ON", "1") or "LIGADO" in payload
        elif topic.endswith("cozinha/status"):
            latest_state["status"]["cozinha"] = payload.upper() in ("LIGADO", "ON", "1") or "LIGADO" in payload
    except Exception:
        pass


client = mqtt.Client()
try:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set()
except Exception:
    pass
client.on_connect = on_connect
client.on_message = on_message
try:
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
except Exception:
    # If broker not reachable, the app still runs and shows defaults
    pass


def build_view():
    cards = []
    for d in DEVICES:
        k = d["key"]
        is_on = latest_state["status"].get(k, False)
        status = "LIGADO" if is_on else "DESLIGADO"
        cards.append({
            "key": k,
            "label": d["label"],
            "status_topic": d["status_topic"],
            "is_on": is_on,
            "status": status
        })

    return {
        "temperatura": latest_state["temperatura"],
        "umidade": latest_state["umidade"],
        "luminosidade": latest_state["luminosidade"],
        "gas": latest_state["gas"],
        "gas_alerta": latest_state["gas_alerta"],
        "gas_threshold": latest_state["gas_threshold"],
        "portao": latest_state["portao"],
        "cards": cards
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", view=build_view())


@app.route("/device/<device>/<action>", methods=["POST"])
def device_control(device, action):
    dev = next((d for d in DEVICES if d["key"] == device), None)
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
    payload = "ABRIR" if action == "open" or action == "open" else "FECHAR"
    try:
        client.publish("residencia/portao/comando", payload)
        flash(f"Comando portão: {payload}")
    except Exception:
        flash("Falha ao enviar comando do portão")
    return redirect(url_for("index"))


@app.route("/gas_threshold", methods=["POST"])
def gas_threshold():
    val = request.form.get("threshold", "")
    try:
        v = int(val)
        payload = str(v)
    except Exception:
        payload = "OFF" if val.strip().upper() in ("OFF", "0") else val
    try:
        client.publish(TOPIC_GAS_THRESHOLD_SET, payload)
        flash(f"Limite de gás atualizado: {payload}")
    except Exception:
        flash("Falha ao publicar novo limite de gás")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
import os
import threading

from flask import Flask, flash, redirect, render_template, request, url_for
import paho.mqtt.client as mqtt


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


MQTT_BROKER = os.environ.get(
    "MQTT_BROKER",
    "6732ba7fb9bf481da315e7a247a59011.s1.eu.hivemq.cloud",
)
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_USER = os.environ.get("MQTT_USER", "admin")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "Teste@123")


TOPICS = {
    "sala": {
        "cmd": "residencia/sala/comando",
        "status": "residencia/sala/status",
        "label": "Sala",
    },
    "ar": {
        "cmd": "residencia/ar/comando",
        "status": "residencia/ar/status",
        "label": "Ar Condicionado",
    },
    "cozinha": {
        "cmd": "residencia/cozinha/comando",
        "status": "residencia/cozinha/status",
        "label": "Cozinha",
    },
}

PORTAO_CMD = "residencia/portao/comando"
PORTAO_STATUS = "residencia/portao/status"
GAS_THRESHOLD_SET = "residencia/gas/threshold/set"

STATUS_TOPICS = [
    *(item["status"] for item in TOPICS.values()),
    PORTAO_STATUS,
    "residencia/sensores/temperatura",
    "residencia/sensores/umidade",
    "residencia/sensores/luminosidade",
    "residencia/sensores/gas",
    "residencia/sensores/gas_alerta",
    "residencia/gas/threshold",
]

latest_state = {
    "residencia/sala/status": "DESCONHECIDO",
    "residencia/ar/status": "DESCONHECIDO",
    "residencia/cozinha/status": "DESCONHECIDO",
    "residencia/portao/status": "DESCONHECIDO",
    "residencia/sensores/temperatura": "--",
    "residencia/sensores/umidade": "--",
    "residencia/sensores/luminosidade": "--",
    "residencia/sensores/gas": "--",
    "residencia/sensores/gas_alerta": "0",
    "residencia/gas/threshold": "2000",
}

state_lock = threading.Lock()


def mqtt_connect() -> mqtt.Client:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    try:
        client.tls_set()
    except Exception:
        pass

    def on_connect(client_instance, userdata, flags, rc):
        for topic in STATUS_TOPICS:
            client_instance.subscribe(topic)

    def on_message(client_instance, userdata, message):
        payload = message.payload.decode(errors="ignore")
        with state_lock:
            latest_state[message.topic] = payload

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client


mqtt_client = mqtt_connect()


def publish(topic: str, payload: str) -> None:
    mqtt_client.publish(topic, payload, retain=True)


def build_view_model():
    with state_lock:
        data = dict(latest_state)

    cards = []
    for key, info in TOPICS.items():
        status = data.get(info["status"], "DESCONHECIDO")
        cards.append(
            {
                "key": key,
                "label": info["label"],
                "status": status,
                "is_on": status in ("LIGADO", "1", "ON"),
                "status_topic": info["status"],
            }
        )

    return {
        "cards": cards,
        "portao": data.get(PORTAO_STATUS, "DESCONHECIDO"),
        "temperatura": data.get("residencia/sensores/temperatura", "--"),
        "umidade": data.get("residencia/sensores/umidade", "--"),
        "luminosidade": data.get("residencia/sensores/luminosidade", "--"),
        "gas": data.get("residencia/sensores/gas", "--"),
        "gas_alerta": data.get("residencia/sensores/gas_alerta", "0") == "1",
        "gas_threshold": data.get("residencia/gas/threshold", "2000"),
    }


@app.route("/")
def index():
    return render_template("index.html", view=build_view_model())


@app.post("/device/<device>/<action>")
def device_control(device, action):
    topic_info = TOPICS.get(device)
    if not topic_info:
        flash("Dispositivo invalido.")
        return redirect(url_for("index"))

    payload = "LIGAR" if action == "on" else "DESLIGAR"
    publish(topic_info["cmd"], payload)
    flash(f"Comando enviado para {topic_info['label']}.")
    return redirect(url_for("index"))


@app.post("/portao/<action>")
def portao_control(action):
    payload = "ABRIR" if action == "open" else "FECHAR"
    publish(PORTAO_CMD, payload)
    flash("Comando do portao enviado.")
    return redirect(url_for("index"))


@app.post("/gas-threshold")
def gas_threshold():
    threshold = request.form.get("threshold", "").strip()
    if not threshold:
        flash("Informe um valor para o limite de gas.")
        return redirect(url_for("index"))

    publish(GAS_THRESHOLD_SET, threshold)
    flash("Limite de gas atualizado.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)