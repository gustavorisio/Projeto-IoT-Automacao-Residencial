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
# 3 Relés + Portão (relé + servo)
rele_sala = Pin(2, Pin.OUT)
rele_ar = Pin(4, Pin.OUT)
rele_cozinha = Pin(19, Pin.OUT)
rele_portao = Pin(18, Pin.OUT)
servo_portao = PWM(Pin(5), freq=50)

for rele in (rele_sala, rele_ar, rele_cozinha, rele_portao):
    rele.value(0)
servo_portao.duty(40)

# 4 Sensores
sensor_dht = dht.DHT22(Pin(15))
sensor_ldr = ADC(Pin(34))
sensor_ldr.atten(ADC.ATTN_11DB)
sensor_pir = Pin(13, Pin.IN)

# Sensor de gás na cozinha (MQ2)
sensor_gas = ADC(Pin(35))
sensor_gas.atten(ADC.ATTN_11DB)
try:
    sensor_gas.width(ADC.WIDTH_12BIT)
except Exception:
    pass

GAS_THRESHOLD = 2000
GAS_PPM_MAX = 10000
GAS_SAMPLES = 5
gas_alert_enabled = True

def ler_media_adc(sensor, amostras=5):
    total = 0
    for _ in range(amostras):
        total += sensor.read()
        time.sleep(0.005)
    return int(total / amostras)

def converter_gas_para_ppm(raw):
    # No Wokwi, mapeamos o valor cru (0-4095) diretamente para PPM (0-10000)
    return int((raw / 4095.0) * GAS_PPM_MAX)

def gas_em_alerta(ppm, limite_ppm):
    return ppm > limite_ppm

# Display OLED
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# Últimas leituras globais
last_gas = 0
last_status_portao = "FECHADO"
last_status_gas = "NORMAL"

# Controle do movimento do portão
PORTAO_TEMPO_MOVIMENTO = 3
portao_movendo_ate = 0
portao_estado_desejado = "FECHADO"

def atualizar_oled(temp, umid, luz, gas, status_gas, status_portao):
    oled.fill(0)
    oled.text("ESTADO DA CASA", 0, 0)
    oled.text(f"Temp: {temp}C Umid:{umid}%", 0, 15)
    oled.text(f"Luz: {luz}", 0, 25)
    oled.text(f"Gas: {status_gas}", 0, 35)
    oled.text(f"Portao: {status_portao}", 0, 45)
    oled.text("RELES: S A C", 0, 55)
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
    b"residencia/cozinha/comando": rele_cozinha
}
TOPIC_CMD_PORTAO = b"residencia/portao/comando"
TOPIC_GAS_THRESHOLD_SET = b"residencia/gas/threshold/set"

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

def atualizar_portao(estado, movimento):
    global last_status_portao, portao_movendo_ate, portao_estado_desejado
    # O relé energiza o conjunto do portão e o PWM define a posição do servo.
    try:
        rele_portao.value(1)
        servo_portao.duty(115 if estado == "ABERTO" else 40)
    except Exception:
        pass
    portao_estado_desejado = estado
    portao_movendo_ate = time.time() + PORTAO_TEMPO_MOVIMENTO
    last_status_portao = movimento
    client.publish(b"residencia/portao/status", movimento.encode(), retain=True)
    client.publish(b"residencia/sensores/portao", movimento.encode(), retain=True)

def callback_mqtt(topic, msg):
    global last_status_portao, portao_movendo_ate, portao_estado_desejado, GAS_THRESHOLD, gas_alert_enabled
    print(f"Comando: {topic} -> {msg}")

    if topic in TOPICOS_CMD:
        rele = TOPICOS_CMD[topic]
        if msg in (b"LIGAR", b"ON", b"1", b"ABRIR"):
            rele.value(1)
        else:
            rele.value(0)
        client.publish(topic.replace(b"comando", b"status"), b"LIGADO" if rele.value() else b"DESLIGADO", retain=True)

    elif topic == TOPIC_CMD_PORTAO:
        if msg in (b"LIGAR", b"ABRIR", b"ON", b"1"):
            atualizar_portao("ABERTO", "ABRINDO")
        elif msg in (b"FECHAR", b"DESLIGAR", b"OFF", b"0"):
            atualizar_portao("FECHADO", "FECHANDO")
        else:
            print("Payload do portão não reconhecido:", msg)
            return
            
    elif topic == TOPIC_GAS_THRESHOLD_SET:
        try:
            payload = msg.strip().upper()
            if payload in (b"0", b"OFF", b"DESLIGAR", b"DESLIGADO", b"NORMAL"):
                gas_alert_enabled = False
                client.publish(b"residencia/gas/threshold", b"0", retain=True)
                client.publish(b"residencia/sensores/gas_alerta", b"0", retain=True)
                print("GAS alert disabled")
            elif payload in (b"1", b"ON", b"LIGAR", b"LIGADO", b"ALERTA"):
                gas_alert_enabled = True
                client.publish(b"residencia/gas/threshold", str(GAS_THRESHOLD).encode(), retain=True)
                print("GAS alert enabled with threshold", GAS_THRESHOLD)
            else:
                v = int(payload)
                GAS_THRESHOLD = v
                gas_alert_enabled = True
                print("GAS_THRESHOLD set to", GAS_THRESHOLD)
                client.publish(b"residencia/gas/threshold", str(GAS_THRESHOLD).encode(), retain=True)
        except Exception as e:
            print("Failed to set GAS_THRESHOLD:", e)
        return

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
client.subscribe(TOPIC_GAS_THRESHOLD_SET)

# ==========================================
# 5. LOOP PRINCIPAL
# ==========================================
ultimo_envio = 0
ultimo_envio_gas = 0 # <-- Variável nova para o timer do gás

def controlar_rele_e_publicar(rele, estado, topico_status, msg_ligado, msg_desligado):
    if rele.value() != estado:
        rele.value(estado)
        client.publish(topico_status, msg_ligado if estado else msg_desligado, retain=True)
        print(f"LOGICA: {topico_status.decode()} -> {'LIGADO' if estado else 'DESLIGADO'}")

def web_page():
    return f"""<html><body><h2>Automação Local</h2>
    <p>Sala: {rele_sala.value()} <a href="/sala/on">Ligar</a> <a href="/sala/off">Desligar</a></p>
    <p>Ar: {rele_ar.value()} <a href="/ar/on">Ligar</a> <a href="/ar/off">Desligar</a></p>
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
            elif '/portao/on' in req: atualizar_portao("ABERTO", "ABRINDO")
            elif '/portao/off' in req: atualizar_portao("FECHADO", "FECHANDO")
            conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + web_page())
            conn.close()
        except OSError:
            pass 
        
        agora = time.time()
        
        # ==========================================
        # TIMER DO GÁS (A cada 5 segundos)
        # ==========================================
        if agora - ultimo_envio_gas >= 5:
            try:
                gas_raw = ler_media_adc(sensor_gas, GAS_SAMPLES)
                last_gas = converter_gas_para_ppm(gas_raw)
                
                print("GAS RAW:", gas_raw, "GAS PPM:", last_gas)
                client.publish(b"residencia/sensores/gas_raw", str(gas_raw).encode(), retain=True)
                client.publish(b"residencia/sensores/gas", str(last_gas).encode(), retain=True)
                
                alerta_gas = gas_em_alerta(last_gas, GAS_THRESHOLD)
                if not gas_alert_enabled:
                    alerta_gas = False
                last_status_gas = "ALERTA" if alerta_gas else "NORMAL"
                    
                client.publish(b"residencia/sensores/gas_alerta", b"1" if alerta_gas else b"0", retain=True)
                client.publish(b"residencia/cozinha/status", b"ALERTA_GAS" if alerta_gas else b"NORMAL", retain=True)
                
                ultimo_envio_gas = agora
            except Exception:
                pass

        # ==========================================
        # TIMER GERAL (A cada 1 segundo)
        # ==========================================
        if agora - ultimo_envio >= 1:
            try:
                sensor_dht.measure()
                temp, umid = sensor_dht.temperature(), sensor_dht.humidity()
                luz = sensor_ldr.read()
                
                mov = sensor_pir.value() 
                
                # --- LÓGICA DE AUTOMAÇÃO ---
                if temp > 28:
                    controlar_rele_e_publicar(rele_ar, 1, b"residencia/ar/status", b"LIGADO", b"DESLIGADO")
                elif temp < 26:
                    controlar_rele_e_publicar(rele_ar, 0, b"residencia/ar/status", b"LIGADO", b"DESLIGADO")

                if luz > 3000: 
                    controlar_rele_e_publicar(rele_sala, 1, b"residencia/sala/status", b"LIGADO", b"DESLIGADO")
                elif luz < 2500: 
                    controlar_rele_e_publicar(rele_sala, 0, b"residencia/sala/status", b"LIGADO", b"DESLIGADO")

                # --- Finaliza portão ---
                if portao_movendo_ate and agora >= portao_movendo_ate:
                    last_status_portao = portao_estado_desejado
                    try:
                        rele_portao.value(0)
                    except Exception:
                        pass
                    client.publish(b"residencia/portao/status", last_status_portao.encode(), retain=True)
                    client.publish(b"residencia/sensores/portao", last_status_portao.encode(), retain=True)
                    portao_movendo_ate = 0

                # --- Envio Sensores MQTT ---
                client.publish(b"residencia/sensores/temperatura", str(temp).encode())
                client.publish(b"residencia/sensores/umidade", str(umid).encode())
                client.publish(b"residencia/sensores/luminosidade", str(luz).encode())
                client.publish(b"residencia/sensores/movimento", str(mov).encode())
                
                # A tela OLED atualiza a cada 1 seg, pegando o último valor salvo do gás (last_gas)
                atualizar_oled(temp, umid, luz, last_gas, last_status_gas, last_status_portao)
                ultimo_envio = agora
            except Exception:
                pass
                
        time.sleep(0.1)

except KeyboardInterrupt:
    client.disconnect()