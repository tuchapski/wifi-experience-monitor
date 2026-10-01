# Contexto temporal dos scans RF na gravação

Os gráficos compactos, os gráficos de telemetria e a timeline de investigação
compartilham a opção **Show estimated RF scan windows**, ligada por padrão.
As faixas roxas mostram quando um scan RF armazenado provavelmente esteve em
execução. A opção oculta as faixas e a linha de scans na timeline.

O início estimado é `observed_at - duration_ms`; o término é `observed_at`.
Os intervalos são recortados aos limites da gravação. Scans muito curtos usam
um marcador mínimo de 0,8 unidade SVG; o tooltip mantém os horários e a duração
originais. A largura visual mínima não representa uma duração maior.

`GET /api/v1/recordings/{recording_id}/rf/windows?limit=2000` retorna apenas
timings e interface, sem carregar inventário BSS. O limite permitido é de 1 a
2000. Os scans mais recentes são selecionados, ordenados por término e ID;
a resposta contém `total_scans`, `loaded_scans`, `invalid_windows`, `truncated`
e `windows`, em ordem cronológica. Durações negativas, não finitas ou que
excedem o intervalo de datetime são omitidas e contabilizadas. Gravações
desconhecidas retornam 404.

A cobertura parcial aparece explicitamente quando há mais scans armazenados
que carregados. Ausência de faixas não comprova ausência de scans: falhas,
uploads pendentes e intervalos antigos fora do limite não são representados.
Os timings são atualizados a cada 30 segundos enquanto a gravação ou sua
sincronização está ativa, e uma última vez ao atingir o estado final.

Essas faixas são contexto temporal para investigação. Não alteram scores,
diagnósticos, thresholds ou a frequência de scans do Agent. A comparação pode
ser afetada por resolução das amostras, relógios e envio tardio; proximidade
temporal não demonstra que um scan causou degradação.
