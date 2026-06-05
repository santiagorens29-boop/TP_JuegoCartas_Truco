from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

# Importamos tu lógica de la V1
from juegos.truco import Truco

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secreto_truco_123'
socketio = SocketIO(app, cors_allowed_origins="*")

# Estructura del diccionario PARTIDAS:
# {
#   "CODIGO123": {
#       "juego": objeto_truco,
#       "max_jugadores": 2, (o 4, o 6)
#       "jugadores": [id_sesion1, id_sesion2, ...],
#       "espectadores": [id_sesion3, ...]
#   }
# }
PARTIDAS = {}

@app.route('/')
def index():
    """Ruta principal: Renderiza la interfaz gráfica de la mesa de juego."""
    return render_template('mesa.html')

# --- EVENTOS DE WEBSOCKETS (Tiempo real) ---

@socketio.on('crear_sala')
def handle_crear_sala(data):
    """
    PRE: data contiene 'codigo' (string) y 'max_jugadores' (int: 2, 4 o 6).
    POST: Registra la partida en el diccionario global y asigna al creador como Jugador 1.
    """
    codigo = data.get('codigo').upper() # Pasamos a mayúsculas para evitar errores de tipeo
    max_jugadores = int(data.get('max_jugadores', 2))
    id_sesion = request.sid
    
    if codigo in PARTIDAS:
        emit('error', {'mensaje': 'Ese código de sala ya existe. Elegí otro.'})
        return

    # Instanciamos el Truco de tu carpeta juegos [cite: 60]
    # Nota de escalabilidad para la V2 final: con un IF acá podés cambiar a Uno() o Poker() según el menú
    instancia_juego = Truco()
    
    PARTIDAS[codigo] = {
        "juego": instancia_juego,
        "max_jugadores": max_jugadores,
        "jugadores": [id_sesion], # El creador es el primer jugador
        "espectadores": []
    }
    
    join_room(codigo)
    print(f"\n[SALA CREADA] Código: {codigo} | Modo: {max_jugadores} jugadores | Creador: {id_sesion}")
    
    emit('sala_creada', {
        'mensaje': f'Sala {codigo} creada con éxito.',
        'rol': 'Jugador 1 (Administrador)',
        'max_jugadores': max_jugadores
    })

@socketio.on('unirse_sala')
def handle_unirse_sala(data):
    """
    PRE: data contiene el 'codigo' al que se quiere unir el dispositivo.
    POST: Clasifica automáticamente al ingresante como Jugador activo o Espectador.
    """
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        emit('error', {'mensaje': 'La sala no existe. Verificá el código.'})
        return
        
    partida = PARTIDAS[codigo]
    join_room(codigo)
    
    # 1. Verificamos si todavía hay "sillas" libres para jugar
    if len(partida["jugadores"]) < partida["max_jugadores"]:
        partida["jugadores"].append(id_sesion)
        numero_jugador = len(partida["jugadores"])
        
        print(f"[NUEVO JUGADOR] Se unió a {codigo}: {id_sesion} como Jugador {numero_jugador}")
        
        # Le avisamos de forma privada a este usuario qué número de jugador es
        emit('rol_asignado', {
            'mensaje': f'Te uniste como Jugador {numero_jugador}.',
            'rol': f'Jugador {numero_jugador}'
        }, room=id_sesion)
        
        # Si la sala se llenó por completo con los jugadores requeridos, arranca la partida
        if len(partida["jugadores"]) == partida["max_jugadores"]:
            print(f"[PARTIDA LISTA] Sala {codigo} completa. Inicializando el mazo...")
            
            # Inicializamos el motor del Truco (fabrica el mazo, asigna pesos y baraja)
            partida["juego"].iniciar_partida()
            
            # Emitimos a TODA la sala que el juego comenzó
            emit('partida_lista', {
                'mensaje': '¡Mesa completa! Comienza la partida.',
                'status': 'jugando'
            }, room=codigo)
            
    # 2. Si las sillas de juego están llenas, entra directo como Espectador en vivo
    else:
        partida["espectadores"].append(id_sesion)
        print(f"[ESPECTADOR] {id_sesion} entró a mirar la sala {codigo}")
        
        emit('rol_asignado', {
            'mensaje': 'La mesa está llena. Entraste en modo Espectador en vivo.',
            'rol': 'Espectador'
        }, room=id_sesion)
        
        # Avisamos a la sala que hay un nuevo mirón
        emit('actualizacion_espectadores', {
            'total': len(partida["espectadores"])
        }, room=codigo)

if __name__ == '__main__':
    # host='0.0.0.0' expone el servidor a los celulares y computadoras de tu Intranet
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)