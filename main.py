import time
import socket
from machine import Pin, ADC, time_pulse_us, PWM, I2C
from umqtt.simple import MQTTClient
import network
import dht
import ssd1306

# ==========================================
# 1. CONFIGURAÇÃO DE HARDWARE (PINOS)
# ==========================================
# Atuadores (Relés e Servo)
rele_sala = Pin(2, Pin.OUT)
rele_ar = Pin(4, Pin.OUT)
rele_sala.value(0)
rele_ar.value(0)

servo = PWM(Pin(18), freq=50)
servo.duty(40) # Posição inicial (Portão Fechado)

# Sensores
sensor_dht = dht.DHT22(Pin(15))
sensor_ldr = ADC(Pin(34))
sensor_ldr.atten(ADC.ATTN_11DB)
sensor_pir = Pin(13, Pin.IN)
trig = Pin(12, Pin.OUT)
echo = Pin(14, Pin.IN)
trig.value(0)

# Display OLED
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

def atualizar_oled(temp, umid, luz, dist, status_sala, status_ar):
    oled.fill(0) # Limpa a tela
    oled.text("ESTADO DA CASA", 0, 0)
    oled.text(f"Temp: {temp}C", 0, 15)
    oled.text(f"Umid: {umid}%", 0, 25)
    oled.text(f"Dist: {dist}cm", 0, 35)
    oled.text(f"S:{status_sala} A:{status_ar}", 0, 50)
    oled.show()

# Inicializa o OLED vazio
atualizar_oled("--", "--", "--", "--", "OFF", "OFF")

# ==========================================
# 2. CONFIGURAÇÕES MQTT (HiveMQ Cloud)
# ==========================================
MQTT_CLIENT_ID = b"esp32_automacao_residencial_v1" 
MQTT_BROKER = "6732ba7fb9bf481da315e7a247a59011.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = b"admin"
MQTT_PASSWORD = b"Teste@123"

TOPIC_CMD_SALA = b"residencia/sala/comando"
TOPIC_CMD_AR = b"residencia/ar/comando"
TOPIC_CMD_PORTAO = b"residencia/portao/comando"

TOPIC_STATUS_SALA = b"residencia/sala/status"
TOPIC_STATUS_AR = b"residencia/ar/status"
TOPIC_STATUS_PORTAO = b"residencia/portao/status"

# ==========================================
# 3. FUNÇÕES DE REDE E COMUNICAÇÃO
# ==========================================
def conectar_wifi():
    print("Conectando ao Wi-Fi (Wokwi-GUEST)...")
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    sta_if.connect('Wokwi-GUEST', '')
    while not sta_if.isconnected():
        print(".", end="")
        time.sleep(0.5)
    ip = sta_if.ifconfig()[0]
    print(f"\nWi-Fi OK! IP: {ip}")
    return ip

def callback_mqtt(topic, msg):
    print(f"[MQTT Comando] Tópico: {topic.decode()} | Msg: {msg.decode()}")
    
    if topic == TOPIC_CMD_SALA:
        rele_sala.value(1 if msg == b"LIGAR" else 0)
        status = b"LIGADA" if rele_sala.value() else b"DESLIGADA"
        client.publish(TOPIC_STATUS_SALA, status)

    elif topic == TOPIC_CMD_AR:
        rele_ar.value(1 if msg == b"LIGAR" else 0)
        status = b"LIGADO" if rele_ar.value() else b"DESLIGADO"
        client.publish(TOPIC_STATUS_AR, status)
        
    elif topic == TOPIC_CMD_PORTAO:
        if msg == b"LIGAR": # Abrir
            servo.duty(115)
            client.publish(TOPIC_STATUS_PORTAO, b"ABERTO")
        else:
            servo.duty(40)
            client.publish(TOPIC_STATUS_PORTAO, b"FECHADO")

# ==========================================
# 4. INICIALIZAÇÃO DO SISTEMA
# ==========================================
meu_ip = conectar_wifi()

# Servidor Web (Não-bloqueante)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)
s.settimeout(0.2) # Impede que o socket trave o Loop Principal

# MQTT
print("Conectando ao HiveMQ Cloud...")
client = MQTTClient(client_id=MQTT_CLIENT_ID, server=MQTT_BROKER, port=MQTT_PORT, 
                    user=MQTT_USER, password=MQTT_PASSWORD, ssl=True, 
                    ssl_params={'server_hostname': MQTT_BROKER})
client.set_callback(callback_mqtt)
client.connect()
client.subscribe(TOPIC_CMD_SALA)
client.subscribe(TOPIC_CMD_AR)
client.subscribe(TOPIC_CMD_PORTAO)
print("Sistema Online!")

# ==========================================
# 5. LOOP PRINCIPAL
# ==========================================
ultimo_envio_sensores = 0

def web_page():
    estado_sala = "LIGADA" if rele_sala.value() else "DESLIGADA"
    estado_ar = "LIGADO" if rele_ar.value() else "DESLIGADO"
    
    html = f"""<html><head><title>Painel Local</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{{font-family: Arial; text-align: center; margin-top: 50px;}} 
    .btn{{padding: 15px; font-size: 18px; margin: 10px; border-radius: 5px; text-decoration: none; color: white;}}
    .on{{background-color: green;}} .off{{background-color: red;}}</style></head>
    <body><h1>Automação Residencial</h1>
    <p>Sala está: <strong>{estado_sala}</strong></p>
    <a href="/sala/on" class="btn on">Ligar Sala</a> <a href="/sala/off" class="btn off">Desligar Sala</a>
    <hr>
    <p>Ar-Condicionado está: <strong>{estado_ar}</strong></p>
    <a href="/ar/on" class="btn on">Ligar Ar</a> <a href="/ar/off" class="btn off">Desligar Ar</a>
    </body></html>"""
    return html

try:
    while True:
        # 1. Verifica Comandos MQTT
        client.check_msg()
        
        # 2. Servidor Web (Verifica cliques na página auto-hospedada)
        try:
            conn, addr = s.accept()
            request = conn.recv(1024).decode()
            
            # Sincronização Web <-> MQTT
            if '/sala/on' in request:
                rele_sala.value(1)
                client.publish(TOPIC_STATUS_SALA, b"LIGADA")
            elif '/sala/off' in request:
                rele_sala.value(0)
                client.publish(TOPIC_STATUS_SALA, b"DESLIGADA")
            elif '/ar/on' in request:
                rele_ar.value(1)
                client.publish(TOPIC_STATUS_AR, b"LIGADO")
            elif '/ar/off' in request:
                rele_ar.value(0)
                client.publish(TOPIC_STATUS_AR, b"DESLIGADO")
                
            response = web_page()
            conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close\n\n' + response)
            conn.close()
        except OSError:
            pass # Sem requisições web no momento, continua o código
        
        # 3. Leitura e Publicação de Sensores (A cada 5 segundos)
        agora = time.time()
        if agora - ultimo_envio_sensores >= 5:
            try:
                # Leituras
                sensor_dht.measure()
                temp, umid = sensor_dht.temperature(), sensor_dht.humidity()
                luz = sensor_ldr.read()
                mov = sensor_pir.value()
                
                trig.value(1)
                time.sleep_us(10)
                trig.value(0)
                duracao = time_pulse_us(echo, 1, 30000)
                dist = round((duracao / 2) / 29.1, 1) if duracao > 0 else 0
                
                # Publicação MQTT
                client.publish(b"residencia/sensores/temperatura", str(temp).encode())
                client.publish(b"residencia/sensores/umidade", str(umid).encode())
                client.publish(b"residencia/sensores/luminosidade", str(luz).encode())
                client.publish(b"residencia/sensores/movimento", str(mov).encode())
                client.publish(b"residencia/sensores/distancia", str(dist).encode())
                
                print(f"[Sensores] Temp:{temp}C | Umid:{umid}% | Luz:{luz} | Mov:{mov} | Dist:{dist}cm")
                
                # Atualiza Tela OLED
                st_sala = "ON" if rele_sala.value() else "OFF"
                st_ar = "ON" if rele_ar.value() else "OFF"
                atualizar_oled(temp, umid, luz, dist, st_sala, st_ar)
                
                ultimo_envio_sensores = agora
            except Exception as e:
                print("Erro na leitura de sensores:", e)
                
        time.sleep(0.1)

except KeyboardInterrupt:
    client.disconnect()