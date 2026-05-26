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
    "quarto": {
        "cmd": "residencia/quarto/comando",
        "status": "residencia/quarto/status",
        "label": "Quarto",
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
    "residencia/quarto/status": "DESCONHECIDO",
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