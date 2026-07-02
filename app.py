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
#       "turno_actual": 0,
#       "historial_mesa": [],
#       "fase_envido": "disponible",       # disponible, cantado, o terminada
#       "envido_acumulado": 0,             # Cuenta de los puntos en juego
#       "jugador_grito_envido": None,      # Quién cantó originalmente
#       "respuestas_envido_recibidas": {}, # Registra los tantos o "son buenas"
#       "manos_internas": {}               # Almacena los objetos Carta reales de cada sid
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
        "turno_actual": 0,  # Inicia el Jugador 1
        "historial_mesa": [],  # Inicia vacío
        "fase_envido": "disponible",
        "envido_acumulado": 0,
        "jugador_grito_envido": None,
        "respuestas_envido_recibidas": {},
        "manos_internas": {},
        "historial_gritos_envido": [] # Para el seguimiento de revires del Detalle 2
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
        
        emit('rol_assigned', {
            'mensaje': f'Te uniste como Jugador {numero_jugador}.',
            'rol': f'Jugador {numero_jugador}'
        }, room=id_sesion)
        
        # --- ¡MESA LLENA! COMENZAMOS EL REPARTO ---
        if len(partida["jugadores"]) == partida["max_jugadores"]:
            print(f"[PARTIDA LISTA] Sala {codigo} completa. Inicializando el mazo...")
            
            # El motor de tu V1 baraja y prepara las cartas
            partida["juego"].iniciar_partida()
            partida["turno_actual"] = 0  # Nos aseguramos de que empiece el Jugador 1
            partida["historial_mesa"] = [] # Limpiamos mesa
            partida["fase_envido"] = "disponible"
            partida["envido_acumulado"] = 0
            partida["jugador_grito_envido"] = None
            partida["respuestas_envido_recibidas"] = {}
            partida["manos_internas"] = {}
            partida["historial_gritos_envido"] = []
            
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
                    
                    # Mapeamos .valor al 'numero' que espera la web
                    cartas_serializadas.append({
                        'numero': carta_robada.valor,
                        'palo': str(carta_robada.palo).lower()
                    })
                
                # Guardamos los objetos Carta completos en el servidor para cálculos de tantos
                partida["manos_internas"][jugador_id] = mano_propia
                
                # Le enviamos de forma EXCLUSIVA y PRIVADA sus 3 cartas a este dispositivo
                emit('recibir_cartas', {
                    'cartas': cartas_serializadas,
                    'total_jugadores': partida["max_jugadores"]
                }, room=jugador_id)
                
    # 2. Si las sillas de juego están llenas, entra directo como Espectador
    else:
        partida["espectadores"].append(id_sesion)
        print(f"[ESPECTADOR] {id_sesion} entró a mirar la sala {codigo}")
        
        emit('rol_assigned', {
            'mensaje': 'La mesa está llena. Entraste en modo Espectador en vivo.',
            'rol': 'Espectador'
        }, room=id_sesion)
        
        emit('actualizacion_espectadores', {'total': len(partida["espectadores"])}, room=codigo)


@socketio.on('tirar_carta')
def handle_tirar_carta(data):
    """
    PRE: data contiene 'codigo' y un diccionario 'carta' con numero y palo.
    POST: Valida si es el turno del jugador emisor. Si es correcto, calcula la ronda actual
          matemáticamente, transmits la jugada estructurada y avanza el turno.
    """
    codigo = data.get('codigo').upper()
    carta = data.get('carta')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    # Si hay un envido cantado y sin resolver, congelamos el tiro de cartas
    if partida["fase_envido"] == "cantado":
        emit('error', {'mensaje': 'Hay una apuesta de tantos activa. Deben responder primero.'})
        return
    
    if id_sesion not in partida["jugadores"]:
        emit('error', {'mensaje': 'Los espectadores no pueden jugar cartas.'})
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de lanzar.'})
        return
        
    cartas_ya_tiradas = len(partida["historial_mesa"])
    ronda_deducida = (cartas_ya_tiradas // partida["max_jugadores"]) + 1
    
    partida["historial_mesa"].append({'jugador': id_sesion, 'carta': carta})
    
    rol = f"Jugador {indice_jugador + 1}"
    print(f"[{codigo}] {rol} jugó en Ronda {ronda_deducida}: {carta['numero']} de {carta['palo']}")
    
    emit('carta_jugada', {
        'rol': rol,
        'carta': carta,
        'ronda': ronda_deducida
    }, room=codigo)
    
    partida["turno_actual"] = (indice_turno + 1) % partida["max_jugadores"]


@socketio.on('cantar_envido')
def handle_cantar_envido(data):
    """
    PRE: data contiene 'codigo' and el 'tipo' de tanto (envido, real_envido, falta_envido).
    POST: Valida que estemos en ronda 1 y establece el estado de la mesa en pausa por tantos.
    """
    codigo = data.get('codigo').upper()
    tipo = data.get('tipo')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    # Validación estricta de turno para cantar tantos
    if id_sesion not in partida["jugadores"]:
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de cantar tantos.'})
        return
    
    # Validación: Solo se puede gritar tantos si está disponible (Ronda 1 antes del pase)
    cartas_ya_tiradas = len(partida["historial_mesa"])
    ronda_actual = (cartas_ya_tiradas // partida["max_jugadores"]) + 1
    
    if ronda_actual > 1 or partida["fase_envido"] == "terminada":
        emit('error', {'mensaje': 'El envido solo se puede cantar en la primera ronda.'})
        return
        
    rol = f"Jugador {indice_jugador + 1}"
    
    # Registramos el grito actual en la cadena de revires
    if "historial_gritos_envido" not in partida:
        partida["historial_gritos_envido"] = []
    partida["historial_gritos_envido"].append(tipo)
    
    partida["fase_envido"] = "cantado"
    partida["jugador_grito_envido"] = id_sesion
    
    # Deducimos las opciones de respuesta válidas según el reglamento mapeado
    opciones_validas = {
        'quiero': True,
        'no_quiero': True,
        'envido': False,
        'real_envido': False,
        'falta_envido': True
    }
    
    cantidades_envido = partida["historial_gritos_envido"].count('envido')
    if tipo == 'envido' and cantidades_envido < 2:
        opciones_validas['envido'] = True
        opciones_validas['real_envido'] = True
    elif tipo == 'envido' and cantidades_envido == 2:
        opciones_validas['real_envido'] = True
    
    print(f"[{codigo}] {rol} gritó: {tipo.upper()}")
    
    # Retransmitimos el grito para pausar las pantallas y activar los botones de respuesta con sus opciones
    emit('envido_gritado', {
        'rol': rol,
        'tipo': tipo,
        'id_emisor': id_sesion,
        'opciones': opciones_validas
    }, room=codigo)


# ✅ NUEVO (DETALLE 2): Controlador del Ping-Pong infinito de respuestas por equipos
@socketio.on('responder_envido')
def handle_responder_envido(data):
    """
    PRE: data contiene 'codigo' y 'decision' ('quiero', 'no_quiero', 'envido', 'real_envido', 'falta_envido').
    POST: Si es revire, calcula opciones legales y pasa la pelota al bando rival. 
          Si cierra, destraba la mesa para continuar jugando las cartas.
    """
    codigo = data.get('codigo').upper()
    decision = data.get('decision')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    if id_sesion not in partida["jugadores"]:
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    rol = f"Jugador {indice_jugador + 1}"
    
    # 1. CASO DE REVIRE: La pelota va de vuelta al otro equipo
    if decision in ['envido', 'real_envido', 'falta_envido']:
        partida["historial_gritos_envido"].append(decision)
        partida["jugador_grito_envido"] = id_sesion # Actualizamos el último emisor
        
        # Árbol de opciones estrictas para la contra-respuesta
        opciones_validas = {
            'quiero': True,
            'no_quiero': True,
            'envido': False,
            'real_envido': False,
            'falta_envido': True
        }
        
        cantidades_envido = partida["historial_gritos_envido"].count('envido')
        contiene_real = 'real_envido' in partida["historial_gritos_envido"]
        
        if decision == 'envido' and cantidades_envido < 2:
            opciones_validas['envido'] = True
            opciones_validas['real_envido'] = not contiene_real
        elif decision == 'envido' and cantidades_envido == 2:
            opciones_validas['real_envido'] = not contiene_real
        elif decision == 'real_envido':
            # Bloqueado revirar con otro Real Envido o Envido simple
            opciones_validas['envido'] = False
            opciones_validas['real_envido'] = False
            
        print(f"[{codigo}] {rol} reviró y gritó: {decision.upper()}")
        
        # Hacemos rebotar el evento hacia el equipo contrario
        emit('envido_gritado', {
            'rol': rol,
            'tipo': decision,
            'id_emisor': id_sesion,
            'opciones': opciones_validas
        }, room=codigo)
        
    # 2. CASO DE CIERRE: Se acepta o rechaza la cadena, destrabamos el juego
    else:
        print(f"[{codigo}] {rol} respondió al tanto con un: {decision.upper()}")
        partida["fase_envido"] = "terminada"
        
        # Emitimos un aviso general para que todas las pantallas limpien sus modales de respuesta
        emit('envido_resuelto', {
            'mensaje': f'Apuesta de tantos resuelta con un "{decision.upper()}". Continúa la partida.',
            'decision': decision
        }, room=codigo)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)