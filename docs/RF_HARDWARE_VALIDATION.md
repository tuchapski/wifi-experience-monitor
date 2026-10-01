# P0.1-H — Validação de hardware e execução prolongada

O P0.1-G foi validado em software. A aprovação do P0.1-H depende de evidências
coletadas no notebook com AX201/iwlwifi. Os testes automatizados usam tempo
simulado e não substituem a avaliação da placa, driver ou tráfego real.

## Evidências recebidas — 2026-10-01

Status: **parcialmente validado** em AX201/iwlwifi (`8086:a0f0`), kernel
`7.0.0-34-generic`, notebook `atuchapski-NB`.

| Ensaio | Probes / respostas | Sem resposta | RTT médio | p95 | Máximo | Scans armazenados |
| --- | --- | --- | --- | --- | --- | --- |
| RF, 60 min | 3600 / 3599 | 0,0278% | 7,18 ms | 28,1 ms | 140 ms | 60 |
| Controle, 1200 probes | 1200 / 1197 | 0,25% | 5,68 ms | 10,3 ms | 717 ms | 0 |

A gravação RF `rec_634868323c674fc0b1cf9afbd45ed470` foi concluída e
sincronizada, com captura de 3600,00034 segundos, sem interrupção e com cobertura
completa das janelas dos 60 scans. Os 218 probes sobrepostos às janelas tiveram
RTT médio de 38,21 ms e p95 de 113 ms, sem ausência de respostas. Os 3314 probes
fora das janelas, dentro da faixa de evidência, tiveram média de 5,14 ms e p95 de
14,6 ms; houve uma ausência de resposta. Outros 68 probes ficaram sem classificação.

O controle reiniciado teve zero scans armazenados; o resumo recebido não inclui
os campos de duração, interrupção ou sincronização. Esses resultados descrevem
associação temporal e mostram que picos e ausências de resposta também ocorrem
sem scans. Não demonstram causalidade nem constituem aprovação geral do hardware.

Pendências: execução prolongada de 4 horas **adiada pelo usuário** e recuperação
real após indisponibilidade do Server. Os primeiros ensaios interrompido (56 probes)
e de controle com 25 scans não contam como validações completas.

## Primeiro ensaio: 60 minutos

Mantenha o notebook no mesmo ponto do escritório, ligado à energia, sem VPN.
Escolha um IP de host na LAN que responda a ICMP de forma estável. Um destino que
limita ou bloqueia ICMP não serve para avaliar o efeito dos scans.

1. Mantenha Server, frontend e um único Agent executando.
2. Confirme no Agent: interface `wlp0s20f3`, driver `iwlwifi`, identidade habitual
   e RF scan readiness verificado. Não execute outro `iw scan` durante o ensaio.
3. Em Diagnostics, inicie uma gravação `AX201-P01H-60m`, com limite de **75 minutos**.
   Aguarde o estado `recording` e o primeiro scan RF.
4. Execute a captura no mesmo notebook, substituindo o IP pelo destino escolhido:

```bash
cd ~/wifi-experience-monitor
source .venv/bin/activate

python scripts/validate_rf_session.py capture \
  --interface wlp0s20f3 \
  --target IP_DO_HOST_NA_LAN \
  --minutes 60 \
  --output data/rf-validation/ax201-60m
```

A captura envia aproximadamente um pacote ICMP por segundo, vinculado à interface
informada. Não altera a configuração do Agent, não inicia scans e não inicia/para
gravações. O diretório precisa ser novo para preservar ensaios anteriores. Ctrl+C
salva uma captura parcial, identificada no manifesto.

5. Ao terminar a captura, pare a gravação pela interface web. Aguarde o envio dos
   dados e confirme a conclusão/sincronização. O relatório pode ser atualizado
   depois, sem repetir os probes, se ainda houver dados pendentes.
6. Copie o ID `rec_...` da gravação e gere o relatório:

```bash
python scripts/validate_rf_session.py report \
  --recording-id ID_DA_GRAVACAO \
  --input data/rf-validation/ax201-60m
```

O resultado fica em `data/rf-validation/ax201-60m/report.json`.

## Como interpretar

O relatório registra driver/PCI/kernel, duração efetiva da captura, probes com
resposta, sem resposta e erros da ferramenta. Erros de permissão/execução não
entram no percentual sem resposta. Esse percentual não identifica a causa da
ausência de resposta ICMP. Média, p95 por nearest-rank e máximo usam apenas RTTs
com resposta; ausência de dados resulta em `null`. Uma resposta `time<1 ms` é
tratada como limite superior de 1 ms.

Para comparação temporal, `observed_at` é o horário de **conclusão** do scan no
Agent; o início é estimado subtraindo `duration_ms`. Cada probe usa seu intervalo
de execução, não somente o horário da resposta. As categorias são:

| Campo | Significado |
| --- | --- |
| `overlapping` | Probe coincide com uma janela estimada de scan bem-sucedido |
| `other_in_evidence_range` | Outro probe dentro do intervalo coberto pelas janelas retornadas |
| `unclassified` | Probe fora desse intervalo, ou ausência de scans utilizáveis |

`other_in_evidence_range` não significa que o rádio estava livre de scans: tentativas
com falha, scans de outros processos e dados ainda não enviados não estão nesse
endpoint. Scans rápidos podem coincidir com poucos probes; zero coincidências
não comprova ausência de impacto. Mudanças no relógio também limitam o alinhamento.

O resumo RF cobre todos os scans armazenados. As janelas para comparação usam
até os 2.000 scans mais recentes. `scan_windows_complete=false` identifica
cobertura parcial, interface diferente, janelas inválidas ou falta de scans.
A captura e o Agent da gravação precisam pertencer ao mesmo hostname.

O relatório sempre marca `hardware_validation=pending_review`. Não produz PASS
automático, causalidade, congestionamento, interferência, noise ou airtime.

## Ensaios seguintes

Após revisar o primeiro resultado:

- **Controle sem scans:** no arquivo de ambiente usado pelo Agent, defina
  `WEM_AGENT_RF_SCAN_ENABLED=false`, reinicie o mesmo Agent e capture 20 minutos
  em nova gravação/diretório. Para serviço, o arquivo é
  `/etc/wifi-experience-agent/agent.env`; para execução manual, use a configuração
  habitual de `.env`. Mantenha posição, destino, energia e carga semelhantes.
  Depois restaure `true` e reinicie. O bloco `probes` permite comparar os ensaios;
  o controle sem scans terá comparações temporais não classificadas.
- **Execução prolongada:** repita por **4 horas**, usando `--minutes 240`, limite
  da gravação de 270 minutos e um novo diretório. Verifique a evolução de CPU/RSS
  do Agent e o espaço de armazenamento no começo e fim. A captura ICMP não mede
  throughput, jitter sob carga ou todo o consumo de recursos.
- **Recuperação do Server:** em um ensaio separado, interrompa apenas o Server
  durante 2–3 minutos. Confirme que o Agent continua coletando, reinicie o Server
  e verifique o esvaziamento da fila RF e a presença dos scans daquele período.
  Use o estado e os logs do Agent já instalado, preservando sua identidade.

## Critérios de revisão

1. Readiness sem erros persistentes de permissão, `busy` ou timeout; scans com
   duração/cadência plausíveis e associação ausente explicitamente representada.
2. Gravação concluída, dados sincronizados e RF histórico ainda acessível após
   reinício do Server. Sem perda/duplicação observada na recuperação do envio.
3. Gráficos e resumo consistentes com a janela armazenada; sem transformar
   lacunas em zero ou inventar parâmetros indisponíveis.
4. CPU, RSS e espaço acompanhados no ensaio prolongado; crescimento persistente
   ou aumento de fila sem recuperação exige investigação.
5. Evidência suficiente para avaliar tráfego. Compare números e cobertura do
   controle e do ensaio; estabeleça a tolerância de latência/perda conforme os
   requisitos da LAN. Uma diferença isolada não prova que o scan causou o problema.
6. `./scripts/release-gate.sh` aprovado.

Envie `report.json` do primeiro ensaio para revisão antes de declarar o P0.1-H
concluído. Se necessário, os probes brutos em `probes.jsonl` e logs do Agent
permitem investigar falhas ou lacunas.
