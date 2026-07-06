from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

# Importamos tu lógica de la V1 (mantenida solo por inicialización)
from juegos.truco import Truco

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secreto_truco_123'
socketio = SocketIO(app, cors_allowed_origins="*")

# Estructura del diccionario PARTIDAS simplificado
PARTIDAS = {}

# --- FUNCIONES AUXILIARES MATEMÁTICAS ---

def calcular_envido_mano(mano_enlazada):
    cartas = []
    nodo_actual = mano_enlazada.cabeza
    while nodo_actual is not None:
        cartas.append(nodo_actual.dato)
        nodo_actual = nodo_actual.siguiente
    
    def val_envido(c):
        return 0 if c.valor >= 10 else c.valor

    palos = {}
    for c in cartas:
        p = str(c.palo).lower()
        if p not in palos:
            palos[p] = []
        palos[p].append(c)
        
    max_tanto = 0
    for p, lista in palos.items():
        if len(lista) == 2:
            tanto = 20 + val_envido(lista[0]) + val_envido(lista[1])
            if tanto > max_tanto: max_tanto = tanto
        elif len(lista) == 3:
            valores = sorted([val_envido(x) for x in lista], reverse=True)
            tanto = 20 + valores[0] + valores[1]
            if tanto > max_tanto: max_tanto = tanto

    for c in cartas:
        tanto = val_envido(c)
        if tanto > max_tanto: max_tanto = tanto
            
    return max_tanto


def calcular_puntos_cadena(historial, decision):
    if decision == 'quiero':
        if historial[-1] == 'falta_envido': return 'falta'
        cant_envido = historial.count('envido')
        tiene_real = 'real_envido' in historial
        puntos = 0
        if cant_envido == 1: puntos += 2
        elif cant_envido == 2: puntos += 4
        if tiene_real: puntos += 3
        return puntos
    else:
        if len(historial) == 1: return 1
        historial_previo = historial[:-1]
        if historial_previo[-1] == 'falta_envido': return 'falta'
        cant_envido = historial_previo.count('envido')
        tiene_real = 'real_envido' in historial_previo
        puntos = 0
        if cant_envido == 1: puntos += 2
        elif cant_envido == 2: puntos += 4
        if tiene_real: puntos += 3
        return puntos


def chequear_retorno_truco_pausado(partida, codigo):
    if partida.get("fase_truco") == "pausado_por_envido":
        partida["fase_truco"] = partida["fase_truco_pausada"]
        tipo_original = "truco"
        if partida["fase_truco"] == "retruco_cantado": tipo_original = "retruco"
        elif partida["fase_truco"] == "vale4_cantado": tipo_original = "vale_4"

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
    return render_template('mesa.html')


# --- EVENTOS DE WEBSOCKETS ---

@socketio.on('crear_sala')
def handle_crear_sala(data):
    codigo = data.get('codigo').upper()
    max_jugadores = int(data.get('max_jugadores', 2))
    id_sesion = request.sid
    
    if codigo in PARTIDAS:
        emit('error', {'mensaje': 'Ese código de sala ya existe.'})
        return

    PARTIDAS[codigo] = {
        "juego": Truco(),
        "max_jugadores": max_jugadores,
        "jugadores": [id_sesion],
        "espectadores": [],
        "turno_actual": 0,
        "historial_mesa": [],
        "fase_envido": "disponible",
        "puntos_envido_calculados": 0,
        "jugador_grito_envido": None,
        "manos_internas": {},
        "historial_gritos_envido": [],
        "fase_truco": "disponible",
        "bando_con_la_pelota_truco": None,
        "puntos_truco_en_juego": 1,
        "jugador_grito_truco": None
    }
    
    join_room(codigo)
    emit('sala_creada', {
        'mensaje': f'Sala {codigo} creada.',
        'rol': 'Jugador 1 (Administrador)',
        'max_jugadores': max_jugadores
    })


@socketio.on('unirse_sala')
def handle_unirse_sala(data):
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS:
        emit('error', {'mensaje': 'La sala no existe.'})
        return
        
    partida = PARTIDAS[codigo]
    join_room(codigo)
    
    if len(partida["jugadores"]) < partida["max_jugadores"]:
        partida["jugadores"].append(id_sesion)
        numero_jugador = len(partida["jugadores"])
        
        emit('rol_asignado', {
            'mensaje': f'Te uniste como Jugador {numero_jugador}.',
            'rol': f'Jugador {numero_jugador}'
        }, room=id_sesion)
        
        if len(partida["jugadores"]) == partida["max_jugadores"]:
            partida["juego"].iniciar_partida()
            partida["turno_actual"] = 0
            partida["historial_mesa"] = []
            partida["fase_envido"] = "disponible"
            partida["manos_internas"] = {}
            partida["historial_gritos_envido"] = []
            partida["fase_truco"] = "disponible"
            partida["puntos_truco_en_juego"] = 1
            
            emit('partida_lista', {
                'mensaje': '¡Mesa completa! Repartiendo...',
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
        emit('rol_asignado', {
            'mensaje': 'Mesa llena. Modo Espectador.',
            'rol': 'Espectador'
        }, room=id_sesion)


@socketio.on('tirar_carta')
def handle_tirar_carta(data):
    codigo = data.get('codigo').upper()
    carta = data.get('carta')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    if partida["fase_envido"] in ["cantado", "declarando"]:
        emit('error', {'mensaje': 'Hay una apuesta de tantos activa. Deben responder primero.'})
        return

    if partida["fase_truco"] in ["truco_cantado", "retruco_cantado", "vale4_cantado", "pausado_por_envido"]:
        emit('error', {'mensaje': 'Hay un grito de Truco pendiente.'})
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de lanzar.'})
        return
        
    partida["historial_mesa"].append({'jugador': id_sesion, 'carta': carta})
    cartas_ya_tiradas = len(partida["historial_mesa"])
    
    # La ronda visual progresa de manera exacta según la vuelta de la mesa
    ronda_deducida = ((cartas_ya_tiradas - 1) // partida["max_jugadores"]) + 1
    
    rol = f"Jugador {indice_jugador + 1}"
    print(f"[{codigo}] {rol} tiró en Ronda {ronda_deducida}")
    
    emit('carta_jugada', {
        'rol': rol,
        'carta': carta,
        'ronda': ronda_deducida
    }, room=codigo)
    
    # ✅ LÓGICA LINEAL PURA: El turno pasa al siguiente de forma circular (J1 -> J2 -> J1 -> J2)
    partida["turno_actual"] = (indice_turno + 1) % partida["max_jugadores"]
    
    # Informamos del cambio estricto de turno a la sala
    emit('cambio_turno_sincro', {
        'turno_actual_idx': partida["turno_actual"],
        'jugador_esperado': f"Jugador {partida['turno_actual'] + 1}"
    }, room=codigo)
    
    # Si todos los de la mesa completaron la vuelta, dejamos asentado en consola el cierre de la ronda
    if cartas_ya_tiradas % partida["max_jugadores"] == 0:
        print(f"[{codigo}] Fin de la Ronda {ronda_deducida}. Próximo tiro: Jugador {partida['turno_actual'] + 1}")


@socketio.on('cantar_envido')
def handle_cantar_envido(data):
    codigo = data.get('codigo').upper()
    tipo = data.get('tipo')
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    if id_sesion not in partida["jugadores"]: return
    indice_jugador = partida["jugadores"].index(id_sesion)
    if indice_jugador != partida["turno_actual"]:
        emit('error', {'mensaje': 'No es tu turno.'})
        return
    
    partida["fase_envido"] = "cantado"
    partida["jugador_grito_envido"] = id_sesion
    partida["historial_gritos_envido"].append(tipo)
    
    opciones_validas = {'quiero': True, 'no_quiero': True, 'envido': (partida["historial_gritos_envido"].count('envido') < 2), 'real_envido': True, 'falta_envido': True}
    
    emit('envido_gritado', {
        'rol': f"Jugador {indice_jugador + 1}",
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
    
    indice_jugador = partida["jugadores"].index(id_sesion)
    rol = f"Jugador {indice_jugador + 1}"
    
    if decision in ['envido', 'real_envido', 'falta_envido']:
        partida["historial_gritos_envido"].append(decision)
        partida["jugador_grito_envido"] = id_sesion
        opciones_validas = {'quiero': True, 'no_quiero': True, 'envido': (partida["historial_gritos_envido"].count('envido') < 2), 'real_envido': True, 'falta_envido': True}
        
        emit('envido_gritado', {
            'rol': rol,
            'tipo': decision,
            'id_emisor': id_sesion,
            'opciones': opciones_validas
        }, room=codigo)
    else:
        puntos = calcular_puntos_cadena(partida["historial_gritos_envido"], decision)
        partida["fase_envido"] = "terminada"
        
        if decision == 'no_quiero':
            emit('envido_resuelto_no_quiero', {
                'mensaje': f'Apuesta rechazada. Se llevan {puntos} punto(s).',
                'puntos': puntos
            }, room=codigo)
            chequear_retorno_truco_pausado(partida, codigo)
        else:
            partida["fase_envido"] = "declarando"
            partida["tanto_maximo_mesa"] = 0
            partida["turno_anuncio_actual"] = 0
            
            emit('fase_declaracion_iniciada', {
                'mensaje': f'¡Apuesta aceptada por {puntos} puntos! Canten por orden.',
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
    
    idx_esperado = partida["turno_anuncio_actual"]
    if id_sesion != partida["jugadores"][idx_esperado]: return
        
    rol_actual = f"Jugador {idx_esperado + 1}"
    
    if accion == 'decir_tanto':
        tanto_declarado = int(data.get('tanto', 0))
        if tanto_declarado > partida["tanto_maximo_mesa"]:
            partida["tanto_maximo_mesa"] = tanto_declarado
            
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: {tanto_declarado}.'
        }, room=codigo)
    else:
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: Son Buenas.'
        }, room=codigo)
        
    partida["turno_anuncio_actual"] += 1
    
    if partida["turno_anuncio_actual"] >= partida["max_jugadores"]:
        partida["fase_envido"] = "terminada"
        emit('envido_resuelto_quiero', {
            'mensaje': f'Envido finalizado. El tanto más alto en mesa fue: {partida["tanto_maximo_mesa"]}. Anoten los puntos correspondientes.',
        }, room=codigo)
        chequear_retorno_truco_pausado(partida, codigo)
    else:
        siguiente_idx = partida["turno_anuncio_actual"]
        emit('siguiente_turno_declaracion', {
            'turno_idx': siguiente_idx,
            'jugador_esperado': f"Jugador {siguiente_idx + 1}",
            'tanto_maximo_mesa': partida["tanto_maximo_mesa"]
        }, room=codigo)


@socketio.on('cantar_truco')
def handle_cantar_truco(data):
    codigo = data.get('codigo').upper()
    tipo = data.get('tipo')
    id_sesion = request.sid

    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]

    if id_sesion not in partida["jugadores"]: return
    idx_jugador = partida["jugadores"].index(id_sesion)
    
    # 1. Identificamos los bandos (Sillas impares vs pares)
    bando_emisor = "Impar" if (idx_jugador % 2 == 0) else "Par"
    bando_receptor = "Par" if bando_emisor == "Impar" else "Impar"

    # 2. VALIDACIÓN DE TURNO CRÍTICA:
    # Si el Truco está disponible (nadie cantó todavía), SOLO lo puede cantar el bando que tiene el turno de juego
    if partida["fase_truco"] == "disponible":
        idx_turno_actual = partida["turno_actual"]
        bando_turno = "Impar" if (idx_turno_actual % 2 == 0) else "Par"
        
        if bando_emisor != bando_turno:
            emit('error', {'mensaje': 'Solo podés cantar Truco cuando es el turno de juego de tu bando.'})
            return

    # Si ya hay una propuesta en curso (ej: truco_cantado), el control de quién responde lo maneja el bando receptor
    if partida["fase_truco"] != "disponible":
        if bando_emisor != partida.get("bando_con_la_pelota_truco"):
            emit('error', {'mensaje': 'Tu bando no tiene permitido revirar en este momento.'})
            return

    opciones_validas = {
        'quiero': True, 
        'no_quiero': True, 
        'retruco': (tipo == 'truco'), 
        'vale_4': (tipo == 'retruco'), 
        'envido_primero': (partida["fase_envido"] == "disponible")
    }

    partida["fase_truco"] = f"{tipo}_cantado"
    partida["jugador_grito_truco"] = id_sesion
    partida["bando_con_la_pelota_truco"] = bando_receptor

    print(f"[{codigo}] Jugador {idx_jugador + 1} (Bando {bando_emisor}) gritó: {tipo.upper()}")

    emit('truco_gritado', {
        'rol': f"Jugador {idx_jugador + 1}",
        'bando_emisor': bando_emisor,
        'tipo': tipo,
        'opciones': opciones_validas
    }, room=codigo)


@socketio.on('responder_truco')
def handle_responder_truco(data):
    codigo = data.get('codigo').upper()
    decision = data.get('decision')
    id_sesion = request.sid

    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]

    idx_jugador = partida["jugadores"].index(id_sesion)

    if decision == 'envido_primero':
        partida["fase_truco_pausada"] = partida["fase_truco"]
        partida["fase_truco"] = "pausado_por_envido"
        partida["historial_gritos_envido"] = ['envido']
        partida["fase_envido"] = "cantado"
        partida["jugador_grito_envido"] = id_sesion
        
        emit('envido_gritado', {
            'rol': f"Jugador {idx_jugador + 1}",
            'tipo': 'envido',
            'id_emisor': id_sesion,
            'opciones': {'quiero': True, 'no_quiero': True, 'envido': True, 'real_envido': True, 'falta_envido': True},
            'mensaje_especial': 'Interrupción por Envido Primero.'
        }, room=codigo)
        return

    if decision == 'quiero':
        partida["fase_truco"] = "aceptado"
        emit('truco_resuelto', {
            'mensaje': f'¡Aceptaron el grito! Sigan jugando las cartas.',
            'fase_truco': "truco_querido"
        }, room=codigo)
    elif decision == 'no_quiero':
        partida["fase_truco"] = "terminada"
        emit('mano_finalizada', {
            'mensaje': f'No se quiso la apuesta. Sumen los puntos del retiro y repartan de nuevo.'
        }, room=codigo)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)