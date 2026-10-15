from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import yt_dlp
import os
from flask import Flask, render_template, Response, stream_with_context, request
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma_chave_secreta_aqui'

socketio = SocketIO(app, cors_allowed_origins="*")

# Caso o seu proxy precise ser desativado ou configurado com IP:PORTA direto (sem wpad.dat)

os.environ["HTTPS_PROXY"] = "http://172.17.0.19:3128"
os.environ["HTTP_PROXY"] = "http://172.17.0.19:3128"

fila_de_videos = []
pessoas_conectadas = {}

estado_player = {
    'tempo_atual': 0,      # Tempo em segundos
    'tocando': False,       # True se estiver tocando, False se pausado
    'url_mp4': None         # URL atual tocando
}

import re

def extrair_youtube_id(url_ou_id):
    """
    Extrai o ID do vídeo do YouTube a partir de qualquer formato de URL comum.
    Se já for um ID direto de 11 caracteres, retorna o próprio ID.
    """
    if not url_ou_id:
        return None
    
    url_ou_id = url_ou_id.strip()
    
    # Padrão Regex para capturar os 11 caracteres do ID do YouTube
    padrao = r'(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?.*v=|embed/|v/|shorts/)|youtu\.be/)([\w-]{11})'
    
    match = re.search(padrao, url_ou_id)
    
    if match:
        return match.group(1)
    
    # Se o usuário já tiver colado o ID de 11 caracteres diretamente (ex: "dQw4w9WgXcQ")
    if len(url_ou_id) == 11 and re.match(r'^[\w-]{11}$', url_ou_id):
        return url_ou_id
        
    return None

def obter_titulo_video(youtube_id):
    PROXY_URL = "http://172.17.0.19:3128"
    url_youtube = f"https://www.youtube.com/watch?v={youtube_id}"
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 10,
        'proxy': PROXY_URL,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_youtube, download=False)
            return info.get('title', youtube_id)
    except Exception as e:
        print(f"Erro ao extrair título ({youtube_id}): {e}")
        return youtube_id

def obter_stream_info(youtube_id):
    """
    Retorna um dicionário com 'url' e 'headers' do melhor stream mp4 disponível.
    Retorna None se não achar nada tocável.
    """
    url_youtube = f"https://www.youtube.com/watch?v={youtube_id}"
    PROXY_URL = "http://172.17.0.19:3128"
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 10,
        'proxy': PROXY_URL,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_youtube, download=False)

        if not info or 'url' not in info:
            return None

        return {
            'url': info['url'],
            'headers': info.get('http_headers', {})
        }
    except Exception as e:
        print(f"[yt-dlp] Erro ao extrair vídeo: {e}")
        return None

def processar_e_tocar(youtube_id):
    stream_info = obter_stream_info(youtube_id)
    if stream_info:
        estado_player['youtube_id'] = youtube_id
        estado_player['tempo_atual'] = 0
        estado_player['tocando'] = True

        socketio.emit('tocar_video', {
            'url_mp4': f'/stream/{youtube_id}',   # <-- aponta pro seu Flask, não pro Google
            'tempo_atual': 0
        })
    else:
        # Se falhou, limpa o estado e pula
        if fila_de_videos and fila_de_videos[0]['id'] == youtube_id:
            fila_de_videos.pop(0)
            socketio.emit('atualizar_fila', {'fila': fila_de_videos})
            if fila_de_videos:
                socketio.start_background_task(processar_e_tocar, fila_de_videos[0]['id'])
            else:
                estado_player['url_mp4'] = None
                estado_player['tocando'] = False
                socketio.emit('tocar_video', {'url_mp4': None, 'tempo_atual': 0})

@app.route('/stream/<youtube_id>')
def stream_video(youtube_id):
    stream_info = obter_stream_info(youtube_id)
    if not stream_info:
        return "Vídeo indisponível", 404

    url_real = stream_info['url']
    headers_yt = stream_info['headers']

    range_header = request.headers.get('Range', None)
    req_headers = dict(headers_yt)
    if range_header:
        req_headers['Range'] = range_header

    
    PROXY_URL = "http://172.17.0.19:3128"

    resp_google = requests.get(
        url_real,
        headers=req_headers,
        stream=True,
        timeout=15,
        proxies={'http': PROXY_URL, 'https': PROXY_URL}
    )
    print(f"[stream] status={resp_google.status_code} content-type={resp_google.headers.get('Content-Type')} content-length={resp_google.headers.get('Content-Length')}")

    if resp_google.status_code not in (200, 206):
        print(f"[stream] Erro do Google: {resp_google.text[:500]}")
        return "Erro ao buscar stream do vídeo", 502

    def generate():
        for chunk in resp_google.iter_content(chunk_size=1024 * 256):
            yield chunk

    status = 206 if range_header and resp_google.status_code == 206 else 200
    headers_resposta = {
        'Content-Type': resp_google.headers.get('Content-Type', 'video/mp4'),
        'Accept-Ranges': 'bytes',
    }
    if 'Content-Range' in resp_google.headers:
        headers_resposta['Content-Range'] = resp_google.headers['Content-Range']
    if 'Content-Length' in resp_google.headers:
        headers_resposta['Content-Length'] = resp_google.headers['Content-Length']

    return Response(stream_with_context(generate()), status=status, headers=headers_resposta)

@app.route('/')
def index():
    return render_template('cliente.html')

@app.route('/player')
def player():
    return render_template('player.html')

@socketio.on('connect')
def handle_connect():
    print('Cliente conectado!')
    emit('resposta_servidor', {'msg': 'Conexão estabelecida com sucesso!'})
    emit('atualizar_fila', {'fila': fila_de_videos})
    emit('atualizar_online', {'online': len(pessoas_conectadas)}, broadcast=True)
    emit('atualizar_pessoas_conectadas', {'pessoas': list(pessoas_conectadas.values())}, broadcast=True)
    

@socketio.on('solicitar_estado_atual')
def enviar_estado_atual():
    emit('sincronizar_player', estado_player)

@socketio.on('alterar_volume')
def alterar_volume(dados):
   
    volume = dados.get('volume', 1)
    emit('mudar_volume_tv', {'volume': volume}, broadcast=True)

@socketio.on('skip_video')
def skip_video():
    if fila_de_videos:
        video_removido = fila_de_videos.pop(0)
        print(f"Vídeo pulado: {video_removido.get('titulo')}")
        emit('atualizar_fila', {'fila': fila_de_videos}, broadcast=True)
        
        if fila_de_videos:
            proximo_id = fila_de_videos[0]['id']
            socketio.start_background_task(processar_e_tocar, proximo_id)
        else:
            print("Fila de vídeos está vazia após o skip.")
            estado_player['url_mp4'] = None
            estado_player['tocando'] = False
            emit('tocar_video', {'url_mp4': None, 'tempo_atual': 0}, broadcast=True)

# Evento emitido pela "TV Principal" para manter o tempo atualizado no servidor
@socketio.on('atualizar_tempo_servidor')
def atualizar_tempo_servidor(dados):
    estado_player['tempo_atual'] = dados.get('tempo', 0)
    estado_player['tocando'] = dados.get('tocando', False)


@socketio.on('registrar_usuario')
def registrar_usuario(dados):
    nome_usuario = dados.get('nome')
    if nome_usuario:
        print(f"Usuário registrado: {nome_usuario}")
        pessoas_conectadas[request.sid] = nome_usuario
        emit('atualizar_pessoas_conectadas', {'pessoas': list(pessoas_conectadas.values())}, broadcast=True)
        emit('atualizar_online', {'online': len(pessoas_conectadas)}, broadcast=True)
    else:
        emit('erro_registro', {'msg': 'Nome de usuário inválido.'})

@socketio.on('atualizar_pessoas_conectadas')
def atualizar_pessoas_conectadas():
    emit('atualizar_pessoas_conectadas', {'pessoas': list(pessoas_conectadas.values())}, broadcast=True)

@socketio.on('atualizar_online')
def atualizar_online():
    emit('atualizar_online', {'online': len(pessoas_conectadas)}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    print('Cliente desconectado!')
    pessoas_conectadas.pop(request.sid, None)
    emit('atualizar_online', {'online': len(pessoas_conectadas)}, broadcast=True)
    emit('atualizar_pessoas_conectadas', {'pessoas': list(pessoas_conectadas.values())}, broadcast=True)


@socketio.on('adicionar_video')
def adicionar_video(dados):
    url_ou_id = dados.get('url')

    nome_usuario = pessoas_conectadas.get(request.sid, "Usuário Desconhecido")
        
    url_ou_id = extrair_youtube_id(url_ou_id)
    if url_ou_id:
        youtube_id = url_ou_id
        if 'v=' in youtube_id:
            youtube_id = youtube_id.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in youtube_id:
            youtube_id = youtube_id.split('youtu.be/')[1].split('?')[0]

        titulo = obter_titulo_video(youtube_id)
        objeto_video = {'id': youtube_id, 'titulo': titulo, 'adicionado_por': nome_usuario}
        
        fila_de_videos.append(objeto_video)
        print(f"Vídeo adicionado: {titulo}")
        
        emit('atualizar_fila', {'fila': fila_de_videos}, broadcast=True)

        if len(fila_de_videos) == 1:
            socketio.start_background_task(processar_e_tocar, youtube_id)

@socketio.on('pausar_video')
def pausar_video():
    print("Recebido do cliente: pausar_video")
    emit('pausar_video', broadcast=True)

@socketio.on('play_video')
def play_video():
    print("Recebido do cliente: play_video")
    emit('play_video', broadcast=True)

@socketio.on('video_finalizado')
def video_finalizado():
    if fila_de_videos:
        video_removido = fila_de_videos.pop(0)
        print(f"Vídeo finalizado: {video_removido.get('titulo')}")
        emit('atualizar_fila', {'fila': fila_de_videos}, broadcast=True)
        
        if fila_de_videos:
            proximo_id = fila_de_videos[0]['id']
            socketio.start_background_task(processar_e_tocar, proximo_id)
        else:
            print("Fila de vídeos está vazia.")
            emit('tocar_video', {'url_mp4': None}, broadcast=True)

@socketio.on('enviar_mensagem')
def handle_message(dados):
    texto = dados.get('texto')
    emit('nova_mensagem', {'texto': texto}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)