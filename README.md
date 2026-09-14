# Transcreve Local

Interface gráfica, CLI e biblioteca Python para transcrever áudio localmente com
[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper). Foi projetada para
arquivos longos e computadores com pouca memória: o áudio é decodificado em
blocos pequenos e nenhum conteúdo é enviado para serviços externos.

## Recursos

- formatos de entrada suportados pelo PyAV, incluindo M4A, MP3, WAV, OGG e Opus;
- saídas TXT, SRT, WebVTT e JSON;
- perfis `economico`, `equilibrado`, `qualidade` e `maximo`;
- blocos sobrepostos para não cortar palavras nas divisões;
- VAD configurável para ignorar silêncio sem perder falas curtas;
- processamento de vários arquivos com um único carregamento do modelo;
- checkpoints para retomar uma transcrição interrompida;
- CPU, CUDA e detecção automática de dispositivo;
- vocabulário contextual para nomes próprios e termos específicos;
- API Python separada da interface de linha de comando.

## Requisitos

- Python 3.10 ou superior;
- aproximadamente 1 GB de espaço para o ambiente, além do modelo escolhido;
- FFmpeg do sistema não é obrigatório: a leitura é feita pelo PyAV.
- Para links do YouTube, instale Node.js 22 ou superior; o aplicativo o detecta
  automaticamente para a extração com `yt-dlp`.

O modelo é baixado na primeira utilização. Modelos maiores são mais precisos,
porém consomem mais memória e levam mais tempo.
Na interface, o estado do modelo aparece ao escolher um perfil. Use **Preparar
modelo** enquanto houver internet para guardar os arquivos no cache local. O
modo **Usar somente arquivos locais e modelo salvo** exige que o modelo esteja
completo no cache e impede downloads durante a transcrição. Links de YouTube,
Vimeo e outros sites continuam dependendo da internet para obter a mídia.
Mesmo com o modelo salvo, carregá-lo na memória e processar o áudio levam tempo;
o preparo antecipado elimina apenas o download inicial.

## Instalação

Clone o repositório e instale em um ambiente virtual:

```bash
git clone https://github.com/RafaelDella/audio-video-transcriptor.git
cd audio-video-transcriptor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Para contribuir ou executar os testes:

```bash
python -m pip install -e ".[dev]"
```

## Uso rápido

### Interface gráfica

Instale o extra da interface e abra a janela. A interface usa HTML, CSS e
JavaScript locais em uma janela Qt; o processamento continua em Python:

```bash
python -m pip install -e ".[gui]"
transcreve-gui
```

No Windows, após a instalação, também é possível abrir a interface com dois
cliques em [`iniciar-programa.cmd`](iniciar-programa.cmd). Esse iniciador usa
o ambiente `.venv` da pasta do projeto; para levar o aplicativo a outro
computador, é preciso instalar Python e as dependências nesse computador.

Selecione ou arraste arquivos, ou adicione um link de mídia para o qual você tem
permissão de download. Links do YouTube, Vimeo e outros sites compatíveis são
obtidos com `yt-dlp` quando a transcrição começa; a mídia temporária é removida
depois. Para links, escolha uma pasta de destino. Depois escolha formato e perfil.
A barra mostra o download e o progresso estimado do arquivo atual; o log
mostra os blocos concluídos e os retomados de checkpoints. Sem pasta de saída,
cada resultado de um arquivo local é gravado ao lado da origem. A transcrição
acontece no computador; links e o primeiro uso de um modelo exigem internet.
Durante a execução, **Cancelar transcrição** interrompe a fonte atual e as
demais fontes da fila. Se um bloco ou o carregamento do modelo estiver em curso,
o cancelamento termina assim que essa operação permitir a interrupção. Arquivos
já concluídos permanecem disponíveis.
Para renomear a transcrição, selecione o arquivo na lista e edite **Nome da
transcrição** antes de iniciar. A extensão é adicionada conforme o formato
escolhido; o áudio ou vídeo original não é renomeado.
Após concluir, selecione um resultado na área de atividade para abrir o arquivo
ou sua pasta.

### Linha de comando

```bash
transcreve audio.m4a
```

Isso cria `audio.txt` ao lado da entrada usando o perfil `equilibrado`.

```bash
# Legenda SRT com maior qualidade
transcreve entrevista.mp3 --profile qualidade --format srt

# Vários arquivos no mesmo diretório de saída
transcreve audios/*.ogg --output-dir transcricoes

# Idioma detectado automaticamente e termos próprios
transcreve reuniao.m4a --language auto \
  --vocabulary "Acme, Maria Silva, Projeto Aurora"

# GPU NVIDIA (CUDA/cuDNN compatíveis devem estar instalados)
transcreve palestra.wav --device cuda --compute-type float16
```

Use `transcreve --help` para ver todas as opções.
As opções principais também possuem aliases em português, como `--modelo`,
`--idioma`, `--saida`, `--perfil`, `--formato` e `--vocabulario`.

## Perfis

| Perfil | Modelo | Indicação |
| --- | --- | --- |
| `economico` | `base` | pouca memória e resultado rápido |
| `equilibrado` | `small` | uso geral; padrão recomendado |
| `qualidade` | `medium` | melhor português em CPU, porém mais lento |
| `maximo` | `large-v3` | GPU ou máquina com bastante memória |

Qualquer propriedade do perfil pode ser substituída:

```bash
transcreve audio.m4a --profile equilibrado --model medium \
  --chunk-minutes 4 --overlap-seconds 12 --beam-size 5 --threads 2
```

Em computadores com 8 GB de RAM, prefira `equilibrado` ou `qualidade` com CPU,
`int8`, duas threads e blocos entre três e cinco minutos.

## Formatos de saída

```bash
transcreve audio.m4a --format txt
transcreve audio.m4a --format srt
transcreve audio.m4a --format vtt
transcreve audio.m4a --format json
```

Ao informar `--output legenda.srt`, o formato é inferido pela extensão. No TXT,
`--timestamps` inclui o horário de cada trecho.

## Interrupção e retomada

Após cada bloco, o programa grava `<saida>.checkpoint.jsonl`. Se o processo for
interrompido, execute o mesmo comando e os blocos concluídos serão reutilizados.
O checkpoint é invalidado automaticamente se o áudio ou a configuração mudar.
Ele é removido ao final; use `--keep-checkpoint` para preservá-lo ou
`--no-resume` para começar novamente.

O arquivo final é escrito atomicamente: uma transcrição existente não é
sobrescrita por uma execução incompleta.

## Uso como biblioteca

```python
from pathlib import Path

from transcreve.config import profile
from transcreve.engine import Transcriber

config = profile("equilibrado", language="pt", vocabulary="Projeto Aurora")
segments = Transcriber(config).transcribe(
    Path("audio.m4a"),
    Path("resultado.json"),
    format_name="json",
)
```

Para uma barra de progresso ou log visual, passe `progress=callback` a
`transcribe`. O callback recebe um `ProgressEvent` com `phase` (`started`,
`completed` ou `finished`), `chunk_index`, `completed_chunks`, `total_chunks`,
`skipped` e os tempos do bloco em segundos. `total_chunks` é uma estimativa
baseada na duração informada pelo arquivo e pode ser `None`; no evento
`finished`, ele é o total efetivo. O evento `completed` só é emitido depois
que o bloco foi transcrito ou retomado do checkpoint. A interface deve
encaminhar esses eventos à thread principal antes de atualizar seus componentes.

Os módulos têm responsabilidades independentes:

- `audio`: leitura incremental, conversão e divisão;
- `config`: perfis e validação;
- `engine`: modelo e orquestração;
- `checkpoint`: persistência e retomada;
- `output`: TXT, SRT, VTT e JSON;
- `cli`: interface de terminal;
- `model_store`: verificação e preparo do cache de modelos;
- `remote`: validação e download temporário de links de mídia;
- `web_gui` e `web`: interface gráfica e seus arquivos locais.

## Privacidade

A transcrição acontece localmente. Links de mídia são obtidos pela internet e
o modelo pode ser baixado na primeira utilização. Áudios, transcrições,
checkpoints e modelos são ignorados pelo Git para reduzir o risco de publicar
dados pessoais.

## Desenvolvimento

```bash
pytest
ruff check .
```

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) antes de enviar uma contribuição.

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
