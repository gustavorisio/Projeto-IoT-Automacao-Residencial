import time
import socket
from machine import Pin, ADC, PWM, I2C
from umqtt.simple import MQTTClient
import network
import dht
import ssd1306

# ==========================================
# 1. CONFIGURAÇÃO DE HARDWARE
# ==========================================
# 4 Relés + Servo
rele_sala = Pin(2, Pin.OUT)
rele_ar = Pin(4, Pin.OUT)
rele_quarto = Pin(5, Pin.OUT)
rele_cozinha = Pin(19, Pin.OUT)
servo = PWM(Pin(18), freq=50)

for rele in (rele_sala, rele_ar, rele_quarto, rele_cozinha):
    rele.value(0)
servo.duty(40) # Portão inicia fechado

# 4 Sensores
sensor_dht = dht.DHT22(Pin(15))
sensor_ldr = ADC(Pin(34))
sensor_ldr.atten(ADC.ATTN_11DB)
sensor_pir = Pin(13, Pin.IN)
# Sensor Fim de Curso
fim_curso = Pin(12, Pin.IN, Pin.PULL_UP) 

# Display OLED
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

def atualizar_oled(temp, umid, luz, status_portao):
    oled.fill(0)
    oled.text("ESTADO DA CASA", 0, 0)
    oled.text(f"Temp: {temp}C Umid:{umid}%", 0, 15)
    oled.text(f"Luz: {luz}", 0, 25)
    oled.text(f"Portao: {status_portao}", 0, 35)
    oled.text("RELES: S A Q C", 0, 45)
    oled.text(f"       {rele_sala.value()} {rele_ar.value()} {rele_quarto.value()} {rele_cozinha.value()}", 0, 55)
    oled.show()

# ==========================================
# 2. CONFIGURAÇÕES MQTT
# ==========================================
MQTT_CLIENT_ID = b"esp32_automacao_tcc" 
MQTT_BROKER = "6732ba7fb9bf481da315e7a247a59011.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = b"admin"
MQTT_PASSWORD = b"Teste@123"

TOPICOS_CMD = {
    b"residencia/sala/comando": rele_sala,
    b"residencia/ar/comando": rele_ar,
    b"residencia/quarto/comando": rele_quarto,
    b"residencia/cozinha/comando": rele_cozinha
}
TOPIC_CMD_PORTAO = b"residencia/portao/comando"

# ==========================================
# 3. COMUNICAÇÃO E CALLBACKS
# ==========================================
def conectar_wifi():
    print("Conectando Wi-Fi...")
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    sta_if.connect('Wokwi-GUEST', '')
    while not sta_if.isconnected():
        pass
    print("Wi-Fi OK!")

def callback_mqtt(topic, msg):
    print(f"Comando: {topic} -> {msg}")
    
    if topic in TOPICOS_CMD:
        rele = TOPICOS_CMD[topic]
        rele.value(1 if msg == b"LIGAR" else 0)
        # Publica com retain=True para garantir o estado persistente no Node-RED
        client.publish(topic.replace(b"comando", b"status"), b"LIGADO" if rele.value() else b"DESLIGADO", retain=True)
        
    elif topic == TOPIC_CMD_PORTAO:
        if msg == b"LIGAR": # Abrir
            servo.duty(115)
            client.publish(b"residencia/portao/status", b"ABRINDO", retain=True)
        elif msg == b"FECHAR" or msg == b"DESLIGAR": # Fechar
            servo.duty(40)
            client.publish(b"residencia/portao/status", b"FECHANDO", retain=True)

# ==========================================
# 4. INICIALIZAÇÃO
# ==========================================
conectar_wifi()

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)
s.settimeout(0.2) 

client = MQTTClient(client_id=MQTT_CLIENT_ID, server=MQTT_BROKER, port=MQTT_PORT, 
                    user=MQTT_USER, password=MQTT_PASSWORD, ssl=True, 
                    ssl_params={'server_hostname': MQTT_BROKER})
client.set_callback(callback_mqtt)
client.connect()

for topico in TOPICOS_CMD.keys():
    client.subscribe(topico)
client.subscribe(TOPIC_CMD_PORTAO)

# ==========================================
# 5. LOOP PRINCIPAL
# ==========================================
ultimo_envio = 0
ultimo_movimento = 0
luz_quarto_ligada = False

def controlar_rele_e_publicar(rele, estado, topico_status, msg_ligado, msg_desligado):
    """Controla o estado de um relé e publica a mudança no MQTT."""
    if rele.value() != estado:
        rele.value(estado)
        client.publish(topico_status, msg_ligado if estado else msg_desligado, retain=True)
        print(f"LOGICA: {topico_status.decode()} -> {'LIGADO' if estado else 'DESLIGADO'}")

def web_page():
    return f"""<html><body><h2>Automação Local</h2>
    <p>Sala: {rele_sala.value()} <a href="/sala/on">Ligar</a> <a href="/sala/off">Desligar</a></p>
    <p>Ar: {rele_ar.value()} <a href="/ar/on">Ligar</a> <a href="/ar/off">Desligar</a></p>
    <p>Quarto: {rele_quarto.value()} <a href="/quarto/on">Ligar</a> <a href="/quarto/off">Desligar</a></p>
    <p>Cozinha: {rele_cozinha.value()} <a href="/cozinha/on">Ligar</a> <a href="/cozinha/off">Desligar</a></p>
    <p>Portão: <a href="/portao/on">Abrir</a> <a href="/portao/off">Fechar</a></p>
    </body></html>"""

try:
    while True:
        client.check_msg()
        try:
            conn, addr = s.accept()
            req = conn.recv(1024).decode()
            if '/sala/on' in req: rele_sala.value(1)
            elif '/sala/off' in req: rele_sala.value(0)
            elif '/portao/on' in req: servo.duty(115)
            elif '/portao/off' in req: servo.duty(40)
            conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + web_page())
            conn.close()
        except OSError:
            pass 
        
        agora = time.time()
        if agora - ultimo_envio >= 5:
            try:
                sensor_dht.measure()
                temp, umid = sensor_dht.temperature(), sensor_dht.humidity()
                luz = sensor_ldr.read()
                mov = sensor_pir.value()
                status_portao = "FECHADO" if fim_curso.value() == 0 else "ABERTO"
                
                # ==========================================
                # 6. LÓGICA DE AUTOMAÇÃO
                # ==========================================
                # --- Lógica do Ar Condicionado (Temperatura) ---
                if temp > 28:
                    controlar_rele_e_publicar(rele_ar, 1, b"residencia/ar/status", b"LIGADO", b"DESLIGADO")
                elif temp < 26:
                    controlar_rele_e_publicar(rele_ar, 0, b"residencia/ar/status", b"LIGADO", b"DESLIGADO")

                # --- Lógica da Luz da Sala (Luminosidade) ---
                if luz > 3000: # Escuro
                    controlar_rele_e_publicar(rele_sala, 1, b"residencia/sala/status", b"LIGADO", b"DESLIGADO")
                elif luz < 2500: # Claro
                    controlar_rele_e_publicar(rele_sala, 0, b"residencia/sala/status", b"LIGADO", b"DESLIGADO")

                # --- Lógica da Luz do Quarto (Movimento e Luminosidade) ---
                if mov and luz > 3000:
                    if not luz_quarto_ligada:
                        controlar_rele_e_publicar(rele_quarto, 1, b"residencia/quarto/status", b"LIGADO", b"DESLIGADO")
                        luz_quarto_ligada = True
                    ultimo_movimento = agora
                
                if luz_quarto_ligada and (agora - ultimo_movimento > 30):
                    controlar_rele_e_publicar(rele_quarto, 0, b"residencia/quarto/status", b"LIGADO", b"DESLIGADO")
                    luz_quarto_ligada = False

                # --- Publicação dos sensores ---
                client.publish(b"residencia/sensores/temperatura", str(temp).encode())
                client.publish(b"residencia/sensores/umidade", str(umid).encode())
                client.publish(b"residencia/sensores/luminosidade", str(luz).encode())
                client.publish(b"residencia/sensores/movimento", str(mov).encode())
                client.publish(b"residencia/sensores/fim_curso", status_portao.encode(), retain=True)
                
                atualizar_oled(temp, umid, luz, status_portao)
                ultimo_envio = agora
            except Exception:
                pass
                
        time.sleep(0.1)

except KeyboardInterrupt:
    client.disconnect()