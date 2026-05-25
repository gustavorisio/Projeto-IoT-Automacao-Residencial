Este repositório contém meu projeto individual de automação residencial usando ESP32 programado em MicroPython utilizando Visual Studio Code, integração MQTT e dashboard em Node-RED.

Resumo

- Dispositivo: ESP32 rodando MicroPython (simulado no Wokwi)
- Comunicação: MQTT (HiveMQ sugerido)
- Orquestração/visualização: Node-RED (dashboard em tempo real)
- Interface embarcada: página web servida pelo ESP32 + painel OLED (SSD1306)
- Persistência: registros em Google Sheets a cada 2 horas
- Notificações: envio de e-mail quando são gerados alertas

Funcionalidades implementadas

- Leitura de 4 sensores distintos (ex.: DHTxx, LDR via ADC, PIR, reed switch)
- Controle de 4 atuadores (ex.: LEDs, relé, ventilador) via página web do ESP32 e via Node-RED
- Comunicação bidirecional MQTT entre ESP32 e Node-RED
- Dashboard em Node-RED com visualização em tempo real e botões de controle
- Gravação de dados em Google Sheets a cada 2 horas (via Node-RED)
- Envio de e-mail de alerta quando thresholds são excedidos

Arquivos principais

- [diagram.json](diagram.json) — Diagrama do sistema (Wokwi/diagrama)
- [main.py](main.py) — Código principal do ESP32 (conexão Wi‑Fi, MQTT, loop de sensores)
- [ssd1306.py](ssd1306.py) — Driver/rotinas para o display OLED (SSD1306)
- [upload_manual.py](upload_manual.py) — Script auxiliar de upload (se aplicável)
- [wokwi.toml](wokwi.toml) — Configuração para simulação no Wokwi

Pré-requisitos

- Visual Studio Code
  - Extensões recomendadas: Wokwi
- Node.js e Node-RED
- Conta/serviço de broker MQTT (HiveMQ público para testes: `broker.hivemq.com:1883`) ou broker próprio
- Conta Google para configurar Google Sheets/API (se desejar persistência automática)

Como executar (simulação com Wokwi + VS Code)

1. Clone o repositório:

```
git clone https://github.com/gustavorisio/Projeto-IoT-Automacao-Residencial.git
cd Projeto-IoT-Automacao-Residencial
```

2. Abra o projeto no Visual Studio Code.

3. Abra `wokwi.toml` e inicie a simulação pelo painel da extensão Wokwi ou diretamente pelo diagram.json. O ESP32 será executado com o firmware MicroPython configurado na simulação.

4. Passo a Passo: Inicialização Completa do Projeto

Primeiro, Inicie o Simulador no wokwi, apos isso abra outro terminal no vscode.

Terminal Normal:
```
python upload_manual.py ssd1306.py ssd1306.py rfc2217://localhost:4000
```
depois execute no terminal:
```
python upload_manual.py main.py main.py rfc2217://localhost:4000
```

Volte para o terminal Wokwi Diagram.json:
Ctrl + B
Ctrl + D
Terminal normal para instalar mqtt:
```
pip install paho-mqtt
```

5. Observe o console do dispositivo na simulação para ver as mensagens de inicialização, a versão do MicroPython e os logs MQTT.

Configurar MQTT (HiveMQ)

- No ESP32, edite as credenciais/host no arquivo de configuração (procure por variáveis `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD` no código) antes de iniciar.
- No Node-RED, adicione um nó MQTT apontando para o mesmo broker e use os tópicos `home/...` conforme o código do ESP32.

Node-RED (dashboard, Google Sheets e e-mail)

1. Instale o Node-RED e inicie-o:

```
node-red
```

2. No editor do Node-RED (normalmente http://localhost:1880):
- Instale e importe o import-node-red-example.
- Configure corretamente para envio de email e o servidor HiveMQ

Google Sheets (configuração resumida)

- Crie um projeto no Google Cloud, habilite a Google Sheets API e gere credenciais (OAuth/Service Account) conforme o método escolhido.
- Alternativa simples: crie um Google Apps Script que aceite requisições HTTP do Node-RED e escreva diretamente na planilha.

Notas sobre desenvolvimento local (hardware real)

- Este projeto foi desenvolvido com o objetivo de testar diretamente pelo Visual Studio Code sem a necessidade de usar um ESP32 fisico.

Boas práticas e justificativas técnicas

- Uso de MQTT: garante comunicação leve e bidirecional entre ESP32 e Node-RED.
- Uso de Node-RED: permite visualização, lógica de processamento e integração com serviços externos (Google Sheets, SMTP) sem programar backend completo.
- Uso de SSD1306/framebuf: permite exibir estado local do sistema mesmo sem dashboard externo.

Entrega

- Gravei um vídeo demonstrando a simulação no Wokwi, a integração MQTT e o dashboard do Node-RED.
- Todo o código fonte está neste repositório; veja `main.py` e `ssd1306.py` para pontos de integração.

Abra uma issue no repositório ou entre em contato pelo GitHub.
