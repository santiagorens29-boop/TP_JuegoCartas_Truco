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
        # Si la cadena termina en falta_envido, se disputa la falta directamente
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
        # Si es NO QUIERO, el ganador se lleva los puntos acumulados hasta el penúltimo grito
        if len(historial) == 1:
            return 1  # Si rechazan el primer grito de la mano, vale 1 punto
            
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
        
        # ✅ REPARADO: Volvemos al nombre correcto 'rol_asignado' en español
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
        
        # ✅ REPARADO: Nombre correcto en español
        emit('rol_asignado', {
            'mensaje': 'La mesa está llena. Entraste en modo Espectador en vivo.',
            'rol': 'Escpectador'
        }, room=id_sesion)
        
        emit('actualizacion_espectadores', {'total': len(partida["espectadores"])}, room=codigo)


@socketio.on('tirar_carta')
def handle_tirar_carta(data):
    """
    PRE: data contains 'codigo' y un diccionario 'carta' con numero y palo.
    POST: Valida si es el turno del jugador emisor. Si es correcto, calcula la ronda actual
          matemáticamente, transmite la jugada estructurada y avanza el turno.
    """
    codigo = data.get('codigo').upper()
    carta = data.get('carta')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    # Si hay un envido cantado y sin resolver, congelamos el tiro de cartas
    if partida["fase_envido"] in ["cantado", "declarando"]:
        emit('error', {'mensaje': 'Hay una apuesta de tantos activa o en declaracion. Deben resolver primero.'})
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
    
    if tipo == 'envido':
        if cantidades_envido < 2:
            opciones_validas['envido'] = True
        opciones_validas['real_envido'] = True
    elif tipo == 'real_envido':
        opciones_validas['envido'] = False
        opciones_validas['real_envido'] = False
    elif tipo == 'falta_envido':
        # ✅ NUEVO: Si abre con Falta Envido de entrada, bloqueamos todos los revires de inmediato
        opciones_validas['envido'] = False
        opciones_validas['real_envido'] = False
        opciones_validas['falta_envido'] = False
    
    print(f"[{codigo}] {rol} gritó: {tipo.upper()}")
    
    # Retransmitimos el grito para pausar las pantallas y activar los botones de respuesta con sus opciones
    emit('envido_gritado', {
        'rol': rol,
        'tipo': tipo,
        'id_emisor': id_sesion,
        'opciones': opciones_validas
    }, room=codigo)


@socketio.on('responder_envido')
def handle_responder_envido(data):
    """
    PRE: data contiene 'codigo' y 'decision' ('quiero', 'no_quiero', 'envido', 'real_envido', 'falta_envido').
    POST: Si es revire, calcula opciones legales y pasa la pelota al bando rival. 
          Si cierra, destraba la mesa o inicia la fase secuencial de declaracion.
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
        partida["jugador_grito_envido"] = id_sesion
        
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
            opciones_validas['envido'] = False
            opciones_validas['real_envido'] = False
        elif decision == 'falta_envido':
            # ✅ NUEVO/CORREGIDO: Si reviran con Falta Envido, apagamos todos los botones de revire
            # para obligar a elegir únicamente entre 'quiero' y 'no_quiero' y romper el ciclo infinito.
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
        
    # 2. CASO DE CIERRE: Se acepta o rechaza la cadena
    else:
        print(f"[{codigo}] {rol} respondió al tanto con un: {decision.upper()}")
        puntos_en_juego = calcular_puntos_cadena(partida["historial_gritos_envido"], decision)
        partida["puntos_envido_calculados"] = puntos_en_juego
        
        if decision == 'no_quiero':
            # Si es un No Quiero, los puntos van directo al bando que dio el último grito sin cantar tantos
            id_ganador = partida["jugador_grito_envido"]
            idx_ganador = partida["jugadores"].index(id_ganador)
            bando_ganador = "Impar" if (idx_ganador % 2 == 0) else "Par"
            
            print(f"[{codigo}] Apuesta rechazada. El bando {bando_ganador} gana {puntos_en_juego} punto(s).")
            partida["fase_envido"] = "terminada"
            
            emit('envido_resuelto_no_quiero', {
                'mensaje': f'Apuesta rechazada con un "NO QUIERO". Bando {bando_ganador} suma {puntos_en_juego} punto(s).',
                'bando_ganador': bando_ganador,
                'puntos': puntos_en_juego
            }, room=codigo)
            
        else:
            # Si es QUIERO, se activa la fase estructurada de declaración secuencial (Mano arranca)
            partida["fase_envido"] = "declarando"
            partida["tanto_maximo_mesa"] = 0
            partida["jugador_lider_tanto"] = partida["jugadores"][0] # El primer jugador (Mano) es el líder provisional
            partida["turno_anuncio_actual"] = 0 # Le toca hablar al Jugador 1
            
            print(f"[{codigo}] Apuesta ACEPTADA por {puntos_en_juego} puntos o Falta. Comienza anuncio secuencial.")
            
            emit('fase_declaracion_iniciada', {
                'mensaje': f'¡Apuesta aceptada! Se juega por: {puntos_en_juego if puntos_en_juego != "falta" else "LA FALTA"}. Declaración por orden de mesa.',
                'turno_idx': 0,
                'jugador_esperado': "Jugador 1"
            }, room=codigo)


# ✅ NUEVO EVENTO: CONTROLADOR DEL ANUNCIO SECUENCIAL DE TANTOS POR EQUIPOS
@socketio.on('declarar_tanto')
def handle_declarar_tanto(data):
    """
    PRE: data contiene 'codigo' y 'accion' ('decir_tanto' o 'son_buenas'). Si es 'decir_tanto', incluye 'tanto' (int).
    POST: Procesa la declaración respetando estrictamente la ronda secuencial de la mesa.
          Al terminar el último jugador, otorga los puntos calculados al bando ganador.
    """
    codigo = data.get('codigo').upper()
    accion = data.get('accion')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        return
        
    partida = PARTIDAS[codigo]
    
    if partida["fase_envido"] != "declarando":
        return
        
    # Control estricto de Turno de Anuncio
    idx_esperado = partida["turno_anuncio_actual"]
    if id_sesion != partida["jugadores"][idx_esperado]:
        emit('error', {'mensaje': f'No es tu turno de declarar tantos. Esperando al Jugador {idx_esperado + 1}.'})
        return
        
    rol_actual = f"Jugador {idx_esperado + 1}"
    mano_real = partida["manos_internas"][id_sesion]
    tanto_real_jugador = calcular_envido_mano(mano_real)
    
    if accion == 'decir_tanto':
        # El jugador decide anunciar un valor numérico
        tanto_declarado = int(data.get('tanto', 0))
        
        # Validación interna de Fair Play para evitar errores de tipeo accidentales
        if tanto_declarado != tanto_real_jugador:
            emit('error', {'mensaje': f'Tus cartas reales suman {tanto_real_jugador} de envido. No podés declarar un número distinto.'})
            return
            
        print(f"[{codigo}] {rol_actual} declara: {tanto_declarado} tantos reales.")
        
        # Verificamos si supera el puntaje máximo registrado hasta ahora en la mesa
        # En caso de igualdad, el jugador actual no supera al líder anterior porque el anterior está antes en orden de mesa
        if tanto_declarado > partida["tanto_maximo_mesa"]:
            partida["tanto_maximo_mesa"] = tanto_declarado
            partida["jugador_lider_tanto"] = id_sesion
            
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: {tanto_declarado}.',
            'tanto': tanto_declarado
        }, room=codigo)
        
    else:
        # El jugador decide pasar cantando "Son Buenas"
        print(f"[{codigo}] {rol_actual} dice: Son Buenas.")
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: Son Buenas.',
            'tanto': 'buenas'
        }, room=codigo)
        
    # Avanzamos el puntero secuencial al siguiente jugador de la lista
    partida["turno_anuncio_actual"] += 1
    
    # CONTROL DE FINALIZACIÓN DE LA MESA (2, 4 o 6 jugadores procesados por igual)
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
    else:
        # Quedan jugadores por hablar, notificamos el siguiente turno de la cadena
        siguiente_idx = partida["turno_anuncio_actual"]
        print(f"[{codigo}] Siguiente en declarar por orden de mesa: Jugador {siguiente_idx + 1}")
        emit('siguiente_turno_declaracion', {
            'turno_idx': siguiente_idx,
            'jugador_esperado': f"Jugador {siguiente_idx + 1}"
        }, room=codigo)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)