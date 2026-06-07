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
#       "espectadores": [id_sesion3, ...],
#       "turno_actual": 0  # 💡 Índice del jugador que tiene el permiso de lanzar
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

    # Instanciamos el Truco de tu carpeta juegos
    instancia_juego = Truco()
    
    PARTIDAS[codigo] = {
        "juego": instancia_juego,
        "max_jugadores": max_jugadores,
        "jugadores": [id_sesion], # El creador es el primer jugador
        "espectadores": [],
        "turno_actual": 0  # Inicia el Jugador 1
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
    POST: Clasifica al ingresante, inicializa el juego si se llena y reparte 
          las cartas reales usando la ListaEnlazada a cada pantalla.
    """
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        emit('error', {'mensaje': 'La sala no existe. Verificá el código.'})
        return
        
    partida = PARTIDAS[codigo]
    join_room(codigo)
    
    # 1. Si hay lugar en la mesa, se sienta a jugar
    if len(partida["jugadores"]) < partida["max_jugadores"]:
        partida["jugadores"].append(id_sesion)
        numero_jugador = len(partida["jugadores"])
        
        print(f"[NUEVO JUGADOR] Se unió a {codigo}: {id_sesion} como Jugador {numero_jugador}")
        
        emit('rol_asignado', {
            'mensaje': f'Te uniste como Jugador {numero_jugador}.',
            'rol': f'Jugador {numero_jugador}'
        }, room=id_sesion)
        
        # --- ¡MESA LLENA! COMENZAMOS EL REPARTO ---
        if len(partida["jugadores"]) == partida["max_jugadores"]:
            print(f"[PARTIDA LISTA] Sala {codigo} completa. Inicializando el mazo...")
            
            # El motor de tu V1 baraja y prepara las cartas
            partida["juego"].iniciar_partida()
            partida["turno_actual"] = 0  # Nos aseguramos de que empiece el Jugador 1
            
            # Avisamos a toda la sala que la mesa está lista
            emit('partida_lista', {
                'mensaje': '¡Mesa completa! Repartiendo cartas...',
                'status': 'jugando'
            }, room=codigo)
            
            # Repartimos 3 cartas reales a cada jugador de la lista
            for jugador_id in partida["jugadores"]:
                from tads.lista_enlazada import ListaEnlazada
                mano_propia = ListaEnlazada()
                cartas_serializadas = [] # Lista simple para mandarle al navegador web
                
                # Robamos las 3 cartas del mazo de la V1
                for _ in range(partida["juego"].cartas_por_mano):
                    carta_robada = partida["juego"].mazo.robar_carta()
                    mano_propia.insertar_final(carta_robada)
                    
                    # ✅ CAMBIO CLAVE: Mapeamos .valor (de tu constructor) al 'numero' que espera la web
                    cartas_serializadas.append({
                        'numero': carta_robada.valor,
                        'palo': str(carta_robada.palo).lower()
                    })
                
                # Le enviamos de forma EXCLUSIVA y PRIVADA sus 3 cartas a este dispositivo
                emit('recibir_cartas', {'cartas': cartas_serializadas}, room=jugador_id)
                
    # 2. Si las sillas de juego están llenas, entra directo como Espectador
    else:
        partida["espectadores"].append(id_sesion)
        print(f"[ESPECTADOR] {id_sesion} entró a mirar la sala {codigo}")
        
        emit('rol_asignado', {
            'mensaje': 'La mesa está llena. Entraste en modo Espectador en vivo.',
            'rol': 'Escpectador'
        }, room=id_sesion)
        
        emit('actualizacion_espectadores', {'total': len(partida["espectadores"])}, room=codigo)


@socketio.on('tirar_carta')
def handle_tirar_carta(data):
    """
    PRE: data contiene 'codigo' y un diccionario 'carta' con numero y palo.
    POST: Valida si es el turno del jugador emisor. Si es correcto, transmite la jugada
          y avanza cíclicamente el turno para 2, 4 o 6 jugadores.
    """
    codigo = data.get('codigo').upper()
    carta = data.get('carta')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    # 1. Validar si el dispositivo que tira está sentado en la mesa
    if id_sesion not in partida["jugadores"]:
        emit('error', {'mensaje': 'Los espectadores no pueden jugar cartas.'})
        return
        
    # 2. Obtener el índice del jugador actual y el índice de quién debería jugar
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    # 3. ⚠️ VALIDACIÓN DE TURNO ESTRICTA
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de lanzar.'})
        return
        
    # 4. Si el turno es correcto, procesamos la jugada
    rol = f"Jugador {indice_jugador + 1}"
    print(f"[{codigo}] {rol} jugó: {carta['numero']} de {carta['palo']}")
    
    # Retransmitimos la jugada a todos los de la sala
    emit('carta_jugada', {
        'rol': rol,
        'carta': carta
    }, room=codigo)
    
    # 5. 🔄 AVANCE CÍCLICO DEL TURNO (Aritmética modular para 2, 4 o 6 jugadores)
    partida["turno_actual"] = (indice_turno + 1) % partida["max_jugadores"]
    print(f"[{codigo}] Siguiente turno: Jugador {partida['turno_actual'] + 1}")