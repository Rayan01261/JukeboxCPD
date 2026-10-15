# CPDbox

Fila colaborativa de vídeos do YouTube para ambientes compartilhados. As pessoas entram pelo celular, pedem vídeos e controlam a reprodução, enquanto uma segunda tela (a TV) toca tudo em sequência.

Construído com **Flask + Socket.IO** (tempo real), **yt-dlp** (extração do stream) e um **proxy de streaming** próprio, que repassa o vídeo ao navegador da TV com suporte a `Range`.

---

## Como funciona

```
Celular (/)                      Servidor Flask                     TV (/player)
 cliente.html  ──Socket.IO──►  fila + estado do player  ──Socket.IO──►  player.html
                                      │                                    │
                                      │  yt-dlp (extrai URL do stream)     │
                                      ▼                                    │
                              /stream/<youtube_id>  ◄──── <video src> ─────┘
                                      │
                              YouTube (via proxy)
```

1. Alguém cola um link (ou ID) do YouTube na página do cliente.
2. O servidor extrai o ID, busca o título com o `yt-dlp` e adiciona o vídeo à fila.
3. Se for o primeiro da fila, o servidor manda a TV tocar `/stream/<id>`.
4. Quando o vídeo termina (ou é pulado), o próximo começa automaticamente.

---

## Funcionalidades

- Adição de vídeos por **link ou ID** do YouTube (`watch`, `youtu.be`, `embed`, `shorts`)
- **Fila compartilhada** em tempo real, mostrando quem pediu cada vídeo
- Controles remotos: **pausar, reproduzir, pular** e **volume da TV**
- **Lista de pessoas conectadas** e contador online
- **Proxy de streaming** (`/stream/<id>`) com suporte a requisições `Range` (permite avançar/retroceder no vídeo)
- **Retentativas**: se o vídeo falhar no player, tenta mais 2 vezes antes de pular para o próximo
- Se a extração do stream falhar, o servidor remove o vídeo da fila e segue para o próximo
- Suporte a rede com **proxy HTTP/HTTPS**

---

## Requisitos

- Python 3.9+
- Acesso à internet (ou a um proxy que alcance o YouTube)

```bash
pip install flask flask-socketio yt-dlp requests
```

---

## Instalação e execução

```bash
git clone https://github.com/<seu-usuario>/cpdbox.git
cd cpdbox

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

O servidor sobe em `http://0.0.0.0:5000`.

| Página | URL | Uso |
|---|---|---|
| Cliente | `http://<ip-do-servidor>:5000/` | Celulares: pedir vídeos e controlar |
| Player | `http://<ip-do-servidor>:5000/player` | Tela/TV que reproduz os vídeos |

> Abra a página `/player` na TV e deixe aberta. Alguns navegadores bloqueiam autoplay com som até haver uma interação na página, então clique uma vez na tela da TV se o vídeo não iniciar sozinho.

---

## Estrutura do projeto

```
.
├── app.py
├── templates/
│   ├── cliente.html     # interface dos usuários
│   └── player.html      # tela da TV
├── requirements.txt
└── README.md
```

---

## Configuração

No `app.py`:

| Item | Descrição |
|---|---|
| `SECRET_KEY` | Troque o valor padrão antes de expor o servidor |
| `HTTP_PROXY` / `HTTPS_PROXY` / `PROXY_URL` | Endereço do proxy da rede (`http://IP:PORTA`). Remova ou ajuste se não usar proxy |
| `port` | Porta do servidor (padrão `5000`) |
| `debug=True` | Desative em produção |

> O endereço do proxy aparece em mais de um ponto do código. Se mudar, atualize todos (ou centralize em uma única constante).

---

## Eventos Socket.IO

### Cliente → Servidor

| Evento | Payload | Descrição |
|---|---|---|
| `registrar_usuario` | `{nome}` | Registra o nome da pessoa conectada |
| `adicionar_video` | `{url}` | Adiciona um vídeo (link ou ID) à fila |
| `pausar_video` | n/d | Pausa a reprodução na TV |
| `play_video` | n/d | Retoma a reprodução na TV |
| `skip_video` | n/d | Pula o vídeo atual |
| `alterar_volume` | `{volume}` (0.0 a 1.0) | Ajusta o volume da TV |
| `video_finalizado` | n/d | Enviado pela TV ao fim do vídeo |
| `atualizar_tempo_servidor` | `{tempo, tocando}` | Atualiza o estado de reprodução no servidor |
| `solicitar_estado_atual` | n/d | Pede o estado atual do player |
| `enviar_mensagem` | `{texto}` | Mensagem em broadcast |

### Servidor → Cliente

| Evento | Descrição |
|---|---|
| `atualizar_fila` | `{fila: [{id, titulo, adicionado_por}]}` |
| `atualizar_online` | `{online}`: quantidade de pessoas registradas |
| `atualizar_pessoas_conectadas` | `{pessoas: [...]}` |
| `tocar_video` | `{url_mp4, tempo_atual}`: manda a TV tocar (ou parar, com `url_mp4: null`) |
| `pausar_video` / `play_video` | Comandos de reprodução para a TV |
| `mudar_volume_tv` | `{volume}` |
| `sincronizar_player` | Estado atual do player |
| `nova_mensagem` | `{texto}` |

---

## Rotas HTTP

| Rota | Descrição |
|---|---|
| `/` | Página do cliente |
| `/player` | Página da TV |
| `/stream/<youtube_id>` | Proxy do stream do vídeo (aceita `Range`, responde `200`/`206`) |

---

## Limitações conhecidas

- A fila e o estado ficam **em memória**: reiniciar o servidor zera tudo.
- Há **uma única fila global** e uma única TV; não há salas.
- O stream é extraído a cada requisição a `/stream/<id>`, então o início de cada vídeo depende da velocidade do `yt-dlp`.
- O `yt-dlp` precisa ser mantido atualizado (`pip install -U yt-dlp`), pois o YouTube muda com frequência.
- Os controles não têm autenticação: qualquer pessoa na rede pode pular ou pausar.

---

## Ideias futuras

- Remover vídeos específicos da fila
- Votação para pular
- Persistência da fila (SQLite/Redis)
- Autenticação ou salas separadas
- Cache da URL do stream

