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
#       "juego": object_truco,
#       "max_jugadores": 2, (o 4, o 6)
#       "jugadores": [id_sesion1, id_sesion2, ...],
#       "espectadores": [id_sesion3, ...],
#       "turno_actual": 0,
#       "historial_mesa": [],
#       "fase_envido": "disponible",       # disponible, cantado, declarando, terminada
#       "envido_acumulado": 0,             # Cuenta de los puntos en juego
#       "jugador_grito_envido": None,      # Quién cantó originalmente
#       "respuestas_envido_recibidas": {}, # Registra los tantos o "son buenas"
#       "manos_internas": {}               # Almacena los objetos Carta reales de cada sid
#
#       --- NUEVAS VARIABLES INYECTADAS PARA EL MOTOR DEL TRUCO ---
#       "fase_truco": "disponible",        # disponible, truco_cantado, truco_querido, retruco_cantado, etc.
#       "bando_con_la_pelota_truco": None, # "Par" o "Impar" (derecho a revirar)
#       "puntos_truco_en_juego": 1,        # Arranca en 1 (callado), sube a 2, 3 o 4
#       "jugador_grito_truco": None,       # Quién tiró la última apuesta
#       "resultado_rondas": [],             # Guardará quién ganó cada ronda: ["Impar", "Parda", ...]
#       "bando_mano_partida": "Impar"      # Quién empezó la mano (para desempatar triple parda)
#   }
# }
PARTIDAS = {}

# --- FUNCIONES AUXILIARES MATEMÁTICAS (DETALLE 3) ---

def calcular_envido_mano(mano_enlazada):
    """
    PRE: mano_enlazada es una ListaEnlazada que contiene los objetos Carta del jugador.
    POST: Retorna un entero entre 0 y 33 según las reglas oficiales del Envido argentino.
    """
    cartas = []
    nodo_actual = mano_enlazada.cabeza
    while nodo_actual is not None:
        cartas.append(nodo_actual.dato)
        nodo_actual = nodo_actual.siguiente
    
    # Mapeamos los valores de las cartas para el envido (10, 11 y 12 valen 0)
    def val_envido(c):
        return 0 if c.valor >= 10 else c.valor

    # Agrupamos por palo para detectar emparejamientos
    palos = {}
    for c in cartas:
        p = str(c.palo).lower()
        if p not in palos:
            palos[p] = []
        palos[p].append(c)
        
    max_tanto = 0
    
    # Caso 1: Dos o tres cartas del mismo palo
    for p, lista in palos.items():
        if len(lista) == 2:
            tanto = 20 + val_envido(lista[0]) + val_envido(lista[1])
            if tanto > max_tanto:
                max_tanto = tanto
        elif len(lista) == 3:
            # Si son 3 del mismo palo, tomamos las dos que sumen más envido
            valores = sorted([val_envido(x) for x in lista], reverse=True)
            tanto = 20 + valores[0] + valores[1]
            if tanto > max_tanto:
                max_tanto = tanto

    # Caso 2: Tres cartas de palos distintos (o si el valor individual de una carta supera el puntaje de palos)
    for c in cartas:
        tanto = val_envido(c)
        if tanto > max_tanto:
            max_tanto = tanto
            
    return max_tanto


def calcular_puntos_cadena(historial, decision):
    """
    PRE: historial es una lista con la cadena de gritos y decision es 'quiero' o 'no_quiero'.
    POST: Retorna un entero con los puntos ganados o un string 'falta' si se juega por el chico/partido.
    """
    if decision == 'quiero':
        if historial[-1] == 'falta_envido':
            return 'falta'
            
        cant_envido = historial.count('envido')
        tiene_real = 'real_envido' in historial
        
        puntos = 0
        if cant_envido == 1: puntos += 2
        elif cant_envido == 2: puntos += 4
        
        if tiene_real: puntos += 3
        return puntos
    else:
        if len(historial) == 1:
            return 1
            
        historial_previo = historial[:-1]
        if historial_previo[-1] == 'falta_envido':
            return 'falta'
            
        cant_envido = historial_previo.count('envido')
        tiene_real = 'real_envido' in historial_previo
        
        puntos = 0
        if cant_envido == 1: puntos += 2
        elif cant_envido == 2: puntos += 4
        
        if tiene_real: puntos += 3
        return puntos


# --- NUEVAS CONTROLADORES INTERNOS PARA LAS TRES RONDAS DEL TRUCO ---

def procesar_fin_de_ronda(partida, codigo, cartas_de_la_ronda):
    """
    POST: Compara el poder de las cartas jugadas en esta ronda según la V1,
          deduce qué bando la ganó o si fue parda, y revisa si se define la mano entera.
    """
    juego_v1 = partida["juego"]
    carta_ganadora_obj = None
    jugador_ganador_id = None
    es_parda = False

    for item in cartas_de_la_ronda:
        c_num = int(item['carta']['numero'])
        c_palo = item['carta']['palo']
        
        # Obtenemos el objeto Carta correspondiente desde el mazo o reconstruido
        from modelos.carta import Carta
        from modelos.palo import Palo
        palo_enum = Palo[c_palo.upper()]
        carta_actual_obj = Carta(c_num, palo_enum)

        if carta_ganadora_obj is None:
            carta_ganadora_obj = carta_actual_obj
            jugador_ganador_id = item['jugador']
        else:
            # Comparamos usando la jerarquía nativa de tu V1
            comparacion = juego_v1.comparar_cartas(carta_actual_obj, carta_ganadora_obj)
            if comparacion > 0:  # carta_actual_obj es más poderosa
                carta_ganadora_obj = carta_actual_obj
                jugador_ganador_id = item['jugador']
                es_parda = False
            elif comparacion == 0:
                # Es empate de poder con la máxima de esta ronda
                es_parda = True

    # Deducimos bando ganador de esta ronda
    if es_parda:
        bando_ronda = "Parda"
        print(f"[{codigo}] Resultado de la Ronda {len(partida['resultado_rondas'])+1}: PARDA")
    else:
        idx_jugador = partida["jugadores"].index(jugador_ganador_id)
        bando_ronda = "Impar" if (idx_jugador % 2 == 0) else "Par"
        print(f"[{codigo}] Resultado de la Ronda {len(partida['resultado_rondas'])+1}: Ganó el bando {bando_ronda}")

    partida["resultado_rondas"].append(bando_ronda)
    emit('ronda_finalizada', {'bando_ganador': bando_ronda, 'ronda_numero': len(partida["resultado_rondas"])}, room=codigo)

    # Verificamos si ya hay un ganador de la mano entera
    definir_ganador_mano(partida, codigo)


def definir_ganador_mano(partida, codigo):
    """
    POST: Analiza el historial de las rondas ['Impar', 'Par', ...] para ver si se cumple
          el reglamento del Truco. De cumplirse, asigna los puntos y limpia para otra mano.
    """
    rondas = partida["resultado_rondas"]
    ganador_bando = None

    # Caso 1: Alguien ganó las 2 primeras rondas
    if len(rondas) >= 2:
        if rondas[0] == rondas[1] and rondas[0] != "Parda":
            ganador_bando = rondas[0]
        # Caso 2: La primera fue parda, define la segunda
        elif rondas[0] == "Parda" and rondas[1] != "Parda":
            ganador_bando = rondas[1]
        # Caso 3: La segunda fue parda, gana el que se quedó con la primera
        elif rondas[1] == "Parda" and rondas[0] != "Parda":
            ganador_bando = rondas[0]

    # Caso 4: Llegamos a la tercera ronda
    if len(rondas) == 3 and ganador_bando is None:
        if rondas[2] != "Parda":
            ganador_bando = rondas[2]
        else:
            # Triple parda o R3 parda habiendo venido de R1 parda
            if rondas[0] != "Parda":
                ganador_bando = rondas[0]
            else:
                ganador_bando = partida["bando_mano_partida"]

    if ganador_bando is not None:
        puntos = partida["puntos_truco_en_juego"]
        print(f"[{codigo}] ¡FIN DE LA MANO! El bando {ganador_bando} se lleva {puntos} puntos de la fase de cartas.")
        
        # Seteamos el Truco como terminado para congelar acciones
        partida["fase_truco"] = "terminada"
        
        emit('mano_finalizada', {
            'bando_ganador': ganador_bando,
            'puntos': puntos,
            'mensaje': f'El bando {ganador_bando} gana la mano de cartas y suma {puntos} punto(s).'
        }, room=codigo)
        
        # En el futuro, aquí llamarías a tu función para reiniciar el mazo y repartir de nuevo


@socketio.on('cantar_truco')
def handle_cantar_truco(data):
    """
    PRE: data contiene 'codigo' y el 'tipo' (truco, retruco, vale_4)
    POST: Valida el bando que grita, congela cartas y activa botones de respuesta en el rival.
    """
    codigo = data.get('codigo').upper()
    tipo = data.get('tipo')
    id_sesion = request.sid

    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]

    if id_sesion not in partida["jugadores"]: return
    idx_jugador = partida["jugadores"].index(id_sesion)
    bando_emisor = "Impar" if (idx_jugador % 2 == 0) else "Par"
    bando_receptor = "Par" if bando_emisor == "Impar" else "Impar"

    # Validar que no se cante dos veces seguidas por el mismo bando
    if partida["fase_truco"] != "disponible":
        if bando_emisor != partida["bando_con_la_pelota_truco"]:
            emit('error', {'mensaje': 'Tu bando no tiene permitido revirar en este momento.'})
            return

    # Validar que sea el turno de lanzar de su bando (si es la primera propuesta)
    if partida["fase_truco"] == "disponible":
        idx_turno_actual = partida["turno_actual"]
        bando_turno = "Impar" if (idx_turno_actual % 2 == 0) else "Par"
        if bando_emisor != bando_turno:
            emit('error', {'mensaje': 'Solo podés cantar Truco cuando es el turno de juego de tu bando.'})
            return

    # Determinamos opciones de revire legales para el oponente
    opciones_validas = {'quiero': True, 'no_quiero': True, 'retruco': False, 'vale_4': False, 'envido_primero': False}
    
    # Inyección estratégica: ¿Se puede meter "Envido Primero"?
    if partida["fase_envido"] == "disponible":
        cartas_ya_tiradas = len(partida["historial_mesa"])
        ronda_actual = (cartas_ya_tiradas // partida["max_jugadores"]) + 1
        if ronda_actual == 1:
            opciones_validas['envido_primero'] = True

    if tipo == 'truco':
        partida["fase_truco"] = "truco_cantado"
        opciones_validas['retruco'] = True
    elif tipo == 'retruco':
        partida["fase_truco"] = "retruco_cantado"
        opciones_validas['vale_4'] = True
    elif tipo == 'vale_4':
        partida["fase_truco"] = "vale4_cantado"

    partida["jugador_grito_truco"] = id_sesion
    partida["bando_con_la_pelota_truco"] = bando_receptor # La pelota pasa al rival

    print(f"[{codigo}] Jugador {idx_jugador + 1} (Bando {bando_emisor}) gritó: {tipo.upper()}")
    
    emit('truco_gritado', {
        'rol': f"Jugador {idx_jugador + 1}",
        'bando_emisor': bando_emisor,
        'tipo': tipo,
        'opciones': opciones_validas
    }, room=codigo)


@socketio.on('responder_truco')
def handle_responder_truco(data):
    """
    PRE: data contiene 'codigo' y 'decision' ('quiero', 'no_quiero', 'envido_primero')
    POST: Procesa la respuesta colectiva. Si es NO QUIERO congela y liquida la mano inmediatamente.
    """
    codigo = data.get('codigo').upper()
    decision = data.get('decision')
    id_sesion = request.sid

    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]

    if id_sesion not in partida["jugadores"]: return
    idx_jugador = partida["jugadores"].index(id_sesion)
    bando_respondente = "Impar" if (idx_jugador % 2 == 0) else "Par"

    # --- INTERRUPCIÓN REGLAMENTARIA: ENVIDO PRIMERO ---
    if decision == 'envido_primero':
        print(f"[{codigo}] Jugador {idx_jugador + 1} interrumpió el Truco diciendo: ¡ENVIDO PRIMERO!")
        
        # Pausamos el truco guardando el estado actual
        partida["fase_truco_pausada"] = partida["fase_truco"]
        partida["fase_truco"] = "pausado_por_envido"
        
        # Forzamos la apertura del Envido tradicional
        partida["historial_gritos_envido"] = ['envido']
        partida["fase_envido"] = "cantado"
        partida["jugador_grito_envido"] = id_sesion
        
        opciones_envido = {'quiero': True, 'no_quiero': True, 'envido': True, 'real_envido': True, 'falta_envido': True}
        
        emit('envido_gritado', {
            'rol': f"Jugador {idx_jugador + 1}",
            'tipo': 'envido',
            'id_emisor': id_sesion,
            'opciones': opciones_envido,
            'mensaje_especial': 'Interrupción por Envido Primero. Se resuelven los tantos y luego vuelve el Truco.'
        }, room=codigo)
        return

    # --- RESPUESTAS ESTÁNDAR (QUIERO / NO QUIERO) ---
    estado_actual = partida["fase_truco"]

    if decision == 'quiero':
        if estado_actual == "truco_cantado":
            partida["fase_truco"] = "truco_querido"
            partida["puntos_truco_en_juego"] = 2
        elif estado_actual == "retruco_cantado":
            partida["fase_truco"] = "retruco_querido"
            partida["puntos_truco_en_juego"] = 3
        elif estado_actual == "vale4_cantado":
            partida["fase_truco"] = "vale4_querido"
            partida["puntos_truco_en_juego"] = 4

        # Si aceptaron el truco directo sin responder envido, este se desactiva para siempre
        if partida["fase_envido"] == "disponible":
            partida["fase_envido"] = "terminada"

        print(f"[{codigo}] Apuesta aceptada. Se juegan {partida['puntos_truco_en_juego']} puntos.")
        emit('truco_resuelto', {
            'mensaje': f'El bando {bando_respondente} dijo QUIERO. ¡Se juegan {partida["puntos_truco_en_juego"]} puntos!',
            'fase_truco': partida["fase_truco"]
        }, room=codigo)

    elif decision == 'no_quiero':
        # Escape inmediato: Se frena todo el juego y se calcula el retiro basado en la escala estricta
        puntos_escape = 1
        if estado_actual == "retruco_cantado":
            puntos_escape = 2
        elif estado_actual == "vale4_cantado":
            puntos_escape = 3

        # El ganador es el bando contrario al que se escapó (el bando que tiró el grito)
        id_ganador = partida["jugador_grito_truco"]
        idx_ganador = partida["jugadores"].index(id_ganador)
        bando_ganador = "Impar" if (idx_ganador % 2 == 0) else "Par"

        partida["fase_truco"] = "terminada"
        print(f"[{codigo}] Corrieron. El bando {bando_ganador} gana la mano de cartas sumando {puntos_escape} punto(s) por el NO QUIERO.")
        
        emit('mano_finalizada', {
            'bando_ganador': bando_ganador,
            'puntos': puntos_escape,
            'mensaje': f'El bando contrario dijo NO QUIERO. El bando {bando_ganador} se lleva {puntos_escape} punto(s).'
        }, room=codigo)


# --- ADAPTACIÓN SURGIDA DE REVIRES: RE-ENGANCHE DEL TRUCO TRAS ENVIDO RESUELTO ---
# Modificamos los cierres del Envido para que si venían de un "Envido Primero", devuelvan la botonera del Truco

def chequear_retorno_truco_pausado(partida, codigo):
    if partida.get("fase_truco") == "pausado_por_envido":
        # Restauramos el estado original del truco que quedó colgado
        partida["fase_truco"] = partida["fase_truco_pausada"]
        tipo_original = "truco"
        if partida["fase_truco"] == "retruco_cantado": tipo_original = "retruco"
        elif partida["fase_truco"] == "vale4_cantado": tipo_original = "vale_4"

        # Volvemos a calcular las opciones de respuesta sin el envido primero
        opciones_validas = {'quiero': True, 'no_quiero': True, 'retruco': (tipo_original=='truco'), 'vale_4': (tipo_original=='retruco'), 'envido_primero': False}
        
        id_emisor = partida["jugador_grito_truco"]
        idx_e = partida["jugadores"].index(id_emisor)
        bando_e = "Impar" if (idx_e % 2 == 0) else "Par"

        emit('truco_gritado', {
            'rol': f"Jugador {idx_e + 1}",
            'bando_emisor': bando_e,
            'tipo': tipo_original,
            'opciones': opciones_validas,
            'mensaje_especial': 'Tantos resueltos. Retomamos la propuesta de cartas pendiente.'
        }, room=codigo)


@app.route('/')
def index():
    """Ruta principal: Renderiza la interfaz gráfica de la mesa de juego."""
    return render_template('mesa.html')

# --- EVENTOS DE WEBSOCKETS (Tiempo real) ---
@socketio.on('crear_sala')
def handle_crear_sala(data):
    codigo = data.get('codigo').upper()
    max_jugadores = int(data.get('max_jugadores', 2))
    id_sesion = request.sid
    
    if codigo in PARTIDAS:
        emit('error', {'mensaje': 'Ese código de sala ya existe. Elegí otro.'})
        return

    instancia_juego = Truco()
    
    PARTIDAS[codigo] = {
        "juego": instancia_juego,
        "max_jugadores": max_jugadores,
        "jugadores": [id_sesion],
        "espectadores": [],
        "turno_actual": 0,
        "historial_mesa": [],
        "fase_envido": "disponible",
        "envido_acumulado": 0,
        "jugador_grito_envido": None,
        "respuestas_envido_recibidas": {},
        "manos_internas": {},
        "historial_gritos_envido": [],
        
        # Inicialización del motor de cartas nuevo
        "fase_truco": "disponible",
        "bando_con_la_pelota_truco": None,
        "puntos_truco_en_juego": 1,
        "jugador_grito_truco": None,
        "resultado_rondas": [],
        "bando_mano_partida": "Impar"
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
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        emit('error', {'mensaje': 'La sala no existe. Verificá el código.'})
        return
        
    partida = PARTIDAS[codigo]
    join_room(codigo)
    
    if len(partida["jugadores"]) < partida["max_jugadores"]:
        partida["jugadores"].append(id_sesion)
        numero_jugador = len(partida["jugadores"])
        
        print(f"[NUEVO JUGADOR] Se unió a {codigo}: {id_sesion} como Jugador {numero_jugador}")
        
        emit('rol_asignado', {
            'mensaje': f'Te uniste como Jugador {numero_jugador}.',
            'rol': f'Jugador {numero_jugador}'
        }, room=id_sesion)
        
        if len(partida["jugadores"]) == partida["max_jugadores"]:
            print(f"[PARTIDA LISTA] Sala {codigo} completa. Inicializando el mazo...")
            
            partida["juego"].iniciar_partida()
            partida["turno_actual"] = 0
            partida["historial_mesa"] = []
            partida["fase_envido"] = "disponible"
            partida["envido_acumulado"] = 0
            partida["jugador_grito_envido"] = None
            partida["respuestas_envido_recibidas"] = {}
            partida["manos_internas"] = {}
            partida["historial_gritos_envido"] = []
            
            # Limpieza estructural de la fase de cartas nueva
            partida["fase_truco"] = "disponible"
            partida["bando_con_la_pelota_truco"] = None
            partida["puntos_truco_en_juego"] = 1
            partida["jugador_grito_truco"] = None
            partida["resultado_rondas"] = []
            partida["bando_mano_partida"] = "Impar"
            
            emit('partida_lista', {
                'mensaje': '¡Mesa completa! Repartiendo cartas...',
                'status': 'jugando'
            }, room=codigo)
            
            for jugador_id in partida["jugadores"]:
                from tads.lista_enlazada import ListaEnlazada
                mano_propia = ListaEnlazada()
                cartas_serializadas = []
                
                for _ in range(partida["juego"].cartas_por_mano):
                    carta_robada = partida["juego"].mazo.robar_carta()
                    mano_propia.insertar_final(carta_robada)
                    
                    cartas_serializadas.append({
                        'numero': carta_robada.valor,
                        'palo': str(carta_robada.palo).lower()
                    })
                
                partida["manos_internas"][jugador_id] = mano_propia
                
                emit('recibir_cartas', {
                    'cartas': cartas_serializadas,
                    'total_jugadores': partida["max_jugadores"]
                }, room=jugador_id)
                
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
    codigo = data.get('codigo').upper()
    carta = data.get('carta')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    # Si hay apuestas abiertas de Truco o Envido sin contestar, las cartas se bloquean por completo
    if partida["fase_envido"] in ["cantado", "declarando"]:
        emit('error', {'mensaje': 'Hay una apuesta de tantos activa. Deben resolver primero.'})
        return

    if partida["fase_truco"] in ["truco_cantado", "retruco_cantado", "vale4_cantado", "pausado_por_envido"]:
        emit('error', {'mensaje': 'Hay un grito de Truco/Retruco/Vale 4 pendiente en la mesa.'})
        return
    
    if partida["fase_truco"] == "terminada":
        emit('error', {'mensaje': 'La mano de cartas ya finalizó.'})
        return

    if id_sesion not in partida["jugadores"]:
        emit('error', {'mensaje': 'Los espectadores no pueden jugar cartas.'})
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de lanzar.'})
        return
        
    # Agregamos la carta al historial del paño
    partida["historial_mesa"].append({'jugador': id_sesion, 'carta': carta})
    
    # Calculamos en qué ronda nos encontramos basándonos en la mesa completa
    cartas_ya_tiradas = len(partida["historial_mesa"])
    ronda_deducida = ((cartas_ya_tiradas - 1) // partida["max_jugadores"]) + 1
    
    rol = f"Jugador {indice_jugador + 1}"
    print(f"[{codigo}] {rol} jugó en Ronda {ronda_deducida}: {carta['numero']} de {carta['palo']}")
    
    emit('carta_jugada', {
        'rol': rol,
        'carta': carta,
        'ronda': ronda_deducida
    }, room=codigo)
    
    # Si todos los jugadores de la mesa tiraron una carta en esta ronda, cerramos y evaluamos jerarquías
    if cartas_ya_tiradas % partida["max_jugadores"] == 0:
        cartas_ronda_actual = partida["historial_mesa"][-partida["max_jugadores"]:]
        procesar_fin_de_ronda(partida, codigo, cartas_ronda_actual)

    # Avanzamos el turno normalmente si la mano no terminó
    if partida["fase_truco"] != "terminada":
        partida["turno_actual"] = (indice_turno + 1) % partida["max_jugadores"]


@socketio.on('cantar_envido')
def handle_cantar_envido(data):
    codigo = data.get('codigo').upper()
    tipo = data.get('tipo')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    if id_sesion not in partida["jugadores"]: return
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de cantar tantos.'})
        return
    
    cartas_ya_tiradas = len(partida["historial_mesa"])
    ronda_actual = (cartas_ya_tiradas // partida["max_jugadores"]) + 1
    
    if ronda_actual > 1 or partida["fase_envido"] == "terminada":
        emit('error', {'mensaje': 'El envido solo se puede cantar en la primera ronda.'})
        return
        
    rol = f"Jugador {indice_jugador + 1}"
    
    if "historial_gritos_envido" not in partida:
        partida["historial_gritos_envido"] = []
    partida["historial_gritos_envido"].append(tipo)
    
    partida["fase_envido"] = "cantado"
    partida["jugador_grito_envido"] = id_sesion
    
    opciones_validas = {'quiero': True, 'no_quiero': True, 'envido': False, 'real_envido': False, 'falta_envido': True}
    cantidades_envido = partida["historial_gritos_envido"].count('envido')
    
    if tipo == 'envido':
        if cantidades_envido < 2: opciones_validas['envido'] = True
        opciones_validas['real_envido'] = True
    elif tipo == 'real_envido':
        opciones_validas['envido'] = False
        opciones_validas['real_envido'] = False
    elif tipo == 'falta_envido':
        opciones_validas['envido'] = False
        opciones_validas['real_envido'] = False
        opciones_validas['falta_envido'] = False
    
    print(f"[{codigo}] {rol} gritó: {tipo.upper()}")
    
    emit('envido_gritado', {
        'rol': rol,
        'tipo': tipo,
        'id_emisor': id_sesion,
        'opciones': opciones_validas
    }, room=codigo)


@socketio.on('responder_envido')
def handle_responder_envido(data):
    codigo = data.get('codigo').upper()
    decision = data.get('decision')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    if id_sesion not in partida["jugadores"]: return
    indice_jugador = partida["jugadores"].index(id_sesion)
    rol = f"Jugador {indice_jugador + 1}"
    
    if decision in ['envido', 'real_envido', 'falta_envido']:
        partida["historial_gritos_envido"].append(decision)
        partida["jugador_grito_envido"] = id_sesion
        
        opciones_validas = {'quiero': True, 'no_quiero': True, 'envido': False, 'real_envido': False, 'falta_envido': True}
        cantidades_envido = partida["historial_gritos_envido"].count('envido')
        contiene_real = 'real_envido' in partida["historial_gritos_envido"]
        
        if decision == 'envido' and cantidades_envido < 2:
            opciones_validas['envido'] = True
            opciones_validas['real_envido'] = not contiene_real
        elif decision == 'envido' and cantidades_envido == 2:
            opciones_validas['real_envido'] = not contiene_real
        elif decision == 'real_envido':
            opciones_validas['envido'] = False
            opciones_validas['real_envido'] = False
        elif decision == 'falta_envido':
            opciones_validas['envido'] = False
            opciones_validas['real_envido'] = False
            opciones_validas['falta_envido'] = False
            
        print(f"[{codigo}] {rol} reviró y gritó: {decision.upper()}")
        
        emit('envido_gritado', {
            'rol': rol,
            'tipo': decision,
            'id_emisor': id_sesion,
            'opciones': opciones_validas
        }, room=codigo)
        
    else:
        print(f"[{codigo}] {rol} respondió al tanto con un: {decision.upper()}")
        puntos_en_juego = calcular_puntos_cadena(partida["historial_gritos_envido"], decision)
        partida["puntos_envido_calculados"] = puntos_en_juego
        
        if decision == 'no_quiero':
            id_ganador = partida["jugador_grito_envido"]
            idx_ganador = partida["jugadores"].index(id_ganador)
            bando_ganador = "Impar" if (idx_ganador % 2 == 0) else "Par"
            
            print(f"[{codigo}] Apuesta rechazada. El bando {bando_ganador} gana {puntos_en_juego} punto(s).")
            partida["fase_envido"] = "terminada"
            
            emit('envido_resuelto_no_quiero', {
                'mensaje': f'Apuesta basada en un "NO QUIERO". Bando {bando_ganador} suma {puntos_en_juego} punto(s).',
                'bando_ganador': bando_ganador,
                'puntos': puntos_en_juego
            }, room=codigo)
            
            # Re-enganche si venía de Envido Primero
            chequear_retorno_truco_pausado(partida, codigo)
            
        else:
            partida["fase_envido"] = "declarando"
            partida["tanto_maximo_mesa"] = 0
            partida["jugador_lider_tanto"] = partida["jugadores"][0]
            partida["turno_anuncio_actual"] = 0
            
            print(f"[{codigo}] Apuesta ACEPTADA por {puntos_en_juego} puntos o Falta. Comienza anuncio secuencial.")
            
            emit('fase_declaracion_iniciada', {
                'mensaje': f'¡Apuesta aceptada! Se juega por: {puntos_en_juego if puntos_en_juego != "falta" else "LA FALTA"}. Declaración por orden de mesa.',
                'turno_idx': 0,
                'jugador_esperado': "Jugador 1"
            }, room=codigo)


@socketio.on('declarar_tanto')
def handle_declarar_tanto(data):
    codigo = data.get('codigo').upper()
    accion = data.get('accion')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    if partida["fase_envido"] != "declarando": return
        
    idx_esperado = partida["turno_anuncio_actual"]
    if id_sesion != partida["jugadores"][idx_esperado]:
        emit('error', {'mensaje': f'No es tu turno de declarar tantos. Esperando al Jugador {idx_esperado + 1}.'})
        return
        
    rol_actual = f"Jugador {idx_esperado + 1}"
    mano_real = partida["manos_internas"][id_sesion]
    tanto_real_jugador = calcular_envido_mano(mano_real)
    
    if accion == 'decir_tanto':
        tanto_declarado = int(data.get('tanto', 0))
        
        if tanto_declarado != tanto_real_jugador:
            emit('error', {'mensaje': f'Tus cartas reales suman {tanto_real_jugador} de envido. No podés declarar un número distinto.'})
            return
            
        print(f"[{codigo}] {rol_actual} declara: {tanto_declarado} tantos reales.")
        
        if tanto_declarado > partida["tanto_maximo_mesa"]:
            partida["tanto_maximo_mesa"] = tanto_declarado
            partida["jugador_lider_tanto"] = id_sesion
            
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: {tanto_declarado}.',
            'tanto': tanto_declarado
        }, room=codigo)
        
    else:
        print(f"[{codigo}] {rol_actual} dice: Son Buenas.")
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: Son Buenas.',
            'tanto': 'buenas'
        }, room=codigo)
        
    partida["turno_anuncio_actual"] += 1
    
    if partida["turno_anuncio_actual"] >= partida["max_jugadores"]:
        id_ganador = partida["jugador_lider_tanto"]
        idx_ganador = partida["jugadores"].index(id_ganador)
        bando_ganador = "Impar" if (idx_ganador % 2 == 0) else "Par"
        pts = partida["puntos_envido_calculados"]
        
        print(f"[{codigo}] Fin de declaracion. Ganador: Jugador {idx_ganador + 1} (Bando {bando_ganador}) con un máximo de {partida['tanto_maximo_mesa']} tantos.")
        
        partida["fase_envido"] = "terminada"
        
        emit('envido_resuelto_quiero', {
            'mensaje': f'Fase finalizada. El bando {bando_ganador} gana el envido con el tanto de Jugador {idx_ganador + 1}. Puntos disputados: {pts if pts != "falta" else "LA FALTA"}.',
            'bando_ganador': bando_ganador,
            'puntos': pts,
            'jugador_ganador': f"Jugador {idx_ganador + 1}",
            'tanto_ganador': partida["tanto_maximo_mesa"]
        }, room=codigo)
        
        # Re-enganche si venía de Envido Primero
        chequear_retorno_truco_pausado(partida, codigo)
    else:
        siguiente_idx = partida["turno_anuncio_actual"]
        print(f"[{codigo}] Siguiente en declarar por orden de mesa: Jugador {siguiente_idx + 1}")
        emit('siguiente_turno_declaracion', {
            'turno_idx': siguiente_idx,
            'jugador_esperado': f"Jugador {siguiente_idx + 1}",
            'tanto_maximo_mesa': partida["tanto_maximo_mesa"]
        }, room=codigo)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)