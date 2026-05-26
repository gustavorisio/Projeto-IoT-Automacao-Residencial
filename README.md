Este repositório contém meu projeto individual de automação residencial usando ESP32 programado em MicroPython utilizando Visual Studio Code, integração MQTT e dashboard em Node-RED.

## Resumo

- **Dispositivo:** ESP32 rodando MicroPython (simulado via Wokwi no VS Code)
- **Comunicação:** MQTT Seguro (HiveMQ Cloud via TLS/SSL na porta 8883)
- **Interface Externa:** Aplicação Web em Flask (Dashboard customizado e interativo)
- **Orquestração/Visualização:** Node-RED (Dashboard em tempo real e orquestração na nuvem)
- **Interface Embarcada:** Página Web local (servida via Socket na porta 80) + Display OLED (SSD1306 via I2C)
- **Persistência de Dados:** Registro histórico de sensores no Google Sheets a cada 2 horas (via Node-RED)
- **Notificações:** Envio de e-mail automático em caso de alertas críticos de segurança (vazamento de gás)

## Funcionalidades Implementadas

- **Leitura de 4 Sensores:**
  - Temperatura e Umidade (**DHT22**)
  - Luminosidade (**LDR** via conversor ADC de 11dB)
  - Presença/Movimento (**PIR**)
  - Concentração de Gás/Fumaça (**MQ2** com amostragem por média e conversão para PPM)
- **Controle de Atuadores:**
  - 4 Relés simulando cargas residenciais e atuação mecânica (Sala, Ar Condicionado, Cozinha e Portão)
  - 1 Servo Motor simulando a movimentação física de um Portão de Garagem (sincronizado com o relé do portão)
- **Lógica de Automação Local (Resiliente a quedas de Internet):**
  - **Ar Condicionado:** Liga automaticamente se a temperatura for > 28°C e desliga se for < 26°C.
  - **Luz da Sala:** Acende quando o ambiente escurece (LDR > 3000) e apaga quando clareia (LDR < 2500).
  - **Segurança da Cozinha (Gás):** Alerta disparado se a concentração ultrapassar o limite configurado (padrão 2000 PPM). Possui proteção onde o monitoramento e o limite de acionamento (threshold) podem ser alterados ou desativados remotamente via interface Flask ou MQTT.
- **Comunicação Bidirecional MQTT:** Publicação de telemetria dos sensores e escuta activa para comandos remotos com persistência de mensagens (`retain=True`).

## Arquivos Principais

- `diagram.json` — Configuração do layout físico, pinagem e conexões elétricas dos componentes no Wokwi.
- `main.py` — Código-fonte principal do ESP32 (gerenciamento de rede, conexão HiveMQ Cloud, rotinas dos sensores e regras de automação).
- `ssd1306.py` — Driver e biblioteca gráfica para controle do Display OLED via protocolo I2C.
- `upload_manual.py` — Script utilitário em Python executado localmente na máquina de desenvolvimento para realizar o upload automatizado de arquivos para o sistema de arquivos do ESP32 simulado (via Raw REPL).
- `app.py` — Backend em Python (Flask) responsável por renderizar a interface web externa e interagir com o broker MQTT.
- `index.html` e `style.css` — Arquivos de frontend da aplicação Flask, exibindo um painel responsivo com atualização de estado em tempo real.
- `firmware.bin` (Interpretador MicroPython): Este é o arquivo binário pré-compilado que atua como o "sistema operacional" base do ESP32. Ele contém o núcleo do MicroPython e  todos os drivers de baixo nível necessários para controlar o hardware da placa (como Wi-Fi, pinos GPIO, ADC e I2C). O microcontrolador precisa ter esse arquivo gravado (flasheado) 
em sua memória flash antes de receber qualquer outro script do projeto. É o firmware que permite que a placa entenda a linguagem Python, traduzindo em tempo real a nossa lógica de programação (como o main.py e o ssd1306.py) para instruções de máquina que o processador do ESP32 consegue executar.
## Pré-requisitos

- Visual Studio Code
  - Extensões recomendadas: Wokwi
- Python 3.x (para rodar a interface Flask e scripts de upload)
- Node.js e Node-RED
- Conta/serviço de broker MQTT (HiveMQ Cloud)
- Conta Google para configurar Google Sheets/API

## Como executar (simulação com Wokwi + VS Code e Flask)

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
Use um Terminal normal para instalar o mqtt:
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
```
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var dataHora = new Date();
  
  try {
    var dados = JSON.parse(e.postData.contents);
    
    // Captura todos os 5 dados + evento
    var evento = dados.evento || "Registro Automático";
    var temp = dados.temperatura || "0";
    var umid = dados.umidade || "0";
    var luz = dados.luminosidade || "0";
    var mov = dados.movimento || "0";
    var gas = dados.gas || "0";
    // Adiciona a linha com as 7 colunas (Data + Evento + 5 Sensores)
    sheet.appendRow([dataHora, evento, temp, umid, luz, mov, gas]);
    
    return ContentService.createTextOutput("Sucesso: Todos os dados gravados");
  } catch (erro) {
    return ContentService.createTextOutput("Erro: " + erro.message);
  }
}
```
3. Flask web:
no terminal, dentro de PROJETO IOT - AUTOMACAO RESIDENCIAL digite:
```
cd .\flask_web\
```
Apos isso inicie o flask web:
```
python app.py
```

Notas sobre desenvolvimento local (hardware real)

- Este projeto foi desenvolvido com o objetivo de testar diretamente pelo Visual Studio Code sem a necessidade de usar um ESP32 fisico.

Boas práticas e justificativas técnicas

- Uso de MQTT: garante comunicação leve e bidirecional entre ESP32 e Node-RED.
- Uso de Node-RED: permite visualização, lógica de processamento e integração com serviços externos (Google Sheets, SMTP) sem programar backend completo.
- Uso de SSD1306/framebuf: permite exibir estado local do sistema mesmo sem dashboard externo.

Entrega

- Gravei um vídeo demonstrando a simulação no Wokwi, a integração MQTT e o dashboard do Node-RED.
  Video no Youtube: https://www.youtube.com/watch?v=e15WSmF2Ams
  
- Todo o código fonte está neste repositório; veja `main.py` e `ssd1306.py` para pontos de integração.

Abra uma issue no repositório ou entre em contato pelo GitHub.
