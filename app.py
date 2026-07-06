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
    """Menú principal de selección de juego."""
    return render_template('index.html')

@app.route('/truco')
def juego_truco():
    """Lleva a la pantalla del Truco que ya armaste."""
    return render_template('truco.html') # Acár va tu mesa del truco actual

@app.route('/siete_y_medio')
def juego_siete():
    """Lleva a la nueva pantalla del Siete y Medio."""
    return render_template('siete.html')

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
        "manos_iniciales": {},  
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
            partida["manos_iniciales"] = {}  
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
                mano_inicial_copia = ListaEnlazada()  
                cartas_serializadas = []
                
                for _ in range(partida["juego"].cartas_por_mano):
                    carta_robada = partida["juego"].mazo.robar_carta()
                    mano_propia.insertar_final(carta_robada)
                    mano_inicial_copia.insertar_final(carta_robada)  
                    
                    cartas_serializadas.append({
                        'numero': carta_robada.valor,
                        'palo': str(carta_robada.palo).lower()
                    })
                
                partida["manos_internas"][jugador_id] = mano_propia
                partida["manos_iniciales"][jugador_id] = mano_inicial_copia  
                
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

    if "cantado" in partida["fase_truco"]:
        emit('error', {'mensaje': 'Hay un grito de Truco pendiente.'})
        return
        
    indice_jugador = partida["jugadores"].index(id_sesion)
    indice_turno = partida["turno_actual"]
    
    if indice_jugador != indice_turno:
        emit('error', {'mensaje': 'No es tu turno de lanzar.'})
        return
        
    partida["historial_mesa"].append({'jugador': id_sesion, 'carta': carta})
    cartas_ya_tiradas = len(partida["historial_mesa"])
    
    ronda_deducida = ((cartas_ya_tiradas - 1) // partida["max_jugadores"]) + 1
    
    rol = f"Jugador {indice_jugador + 1}"
    print(f"[{codigo}] {rol} tiró en Ronda {ronda_deducida}")
    
    emit('carta_jugada', {
        'rol': rol,
        'carta': carta,
        'ronda': ronda_deducida
    }, room=codigo)
    
    partida["turno_actual"] = (indice_turno + 1) % partida["max_jugadores"]
    
    emit('cambio_turno_sincro', {
        'turno_actual_idx': partida["turno_actual"],
        'jugador_esperado': f"Jugador {partida['turno_actual'] + 1}"
    }, room=codigo)
    
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
    
    bando_respondente = "Impar" if (indice_jugador % 2 == 0) else "Par"
    
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
                'bando_defensor': bando_respondente,
                'mensaje': f'¡Apuesta aceptada por {puntos} puntos! Canten por orden.',
                'turno_idx': 0,
                'jugador_esperado': "Jugador 1"
            }, room=codigo)


@socketio.on('declarar_tanto')
def handle_declarar_tanto(data):
    codigo = data.get('codigo').upper()
    accion = data.get('accion') # decir_tanto o son_buenas
    id_sesion = request.sid
    
    if codigo not in PARTIDAS: return
    partida = PARTIDAS[codigo]
    
    idx_esperado = partida["turno_anuncio_actual"]
    if id_sesion != partida["jugadores"][idx_esperado]: return
        
    rol_actual = f"Jugador {idx_esperado + 1}"
    
    # ✅ CORRECCIÓN EN LA VALIDACIÓN: Solo verificamos el número si la acción es 'decir_tanto'
    if accion == 'decir_tanto':
        mano_original_completa = partida["manos_iniciales"][id_sesion]
        tanto_real_jugador = calcular_envido_mano(mano_original_completa)
        tanto_declarado = int(data.get('tanto', 0))
        
        if tanto_declarado != tanto_real_jugador:
            emit('error', {'mensaje': f'Tus cartas reales suman {tanto_real_jugador} de envido. No podés cantar otra cosa.'})
            return
            
        if tanto_declarado > partida["tanto_maximo_mesa"]:
            partida["tanto_maximo_mesa"] = tanto_declarado
            
        emit('tanto_anunciado_sala', {
            'rol': rol_actual,
            'mensaje': f'{rol_actual} dice: {tanto_declarado}.'
        }, room=codigo)
    else:
        # Si dice 'son_buenas', el flujo progresa libremente sin trabar la secuencia
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
    
    bando_emisor = "Impar" if (idx_jugador % 2 == 0) else "Par"
    bando_receptor = "Par" if bando_emisor == "Impar" else "Impar"

    if partida["fase_truco"] == "disponible":
        idx_turno_actual = partida["turno_actual"]
        bando_turno = "Impar" if (idx_turno_actual % 2 == 0) else "Par"
        if bando_emisor != bando_turno:
            emit('error', {'mensaje': 'Solo podés cantar Truco cuando es el turno de juego de tu bando.'})
            return

    if "cantado" not in partida["fase_truco"] and partida["fase_truco"] != "disponible":
        if bando_emisor != partida.get("bando_con_la_pelota_truco"):
            emit('error', {'mensaje': 'Tu bando no tiene permitido revirar.'})
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
    bando_respondente = "Impar" if (idx_jugador % 2 == 0) else "Par"
    bando_contrario = "Par" if bando_respondente == "Impar" else "Impar"

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
        if partida["fase_truco"] == "truco_cantado":
            partida["fase_truco"] = "truco_querido"
        elif partida["fase_truco"] == "retruco_cantado":
            partida["fase_truco"] = "retruco_querido"
        elif partida["fase_truco"] == "vale_4_cantado":
            partida["fase_truco"] = "vale4_querido"

        partida["bando_con_la_pelota_truco"] = bando_contrario

        emit('truco_resuelto', {
            'bando_defensor': bando_respondente,
            'mensaje': f'El bando {bando_respondente} aceptó el grito. ¡Sigan jugando las cartas!',
            'fase_truco': partida["fase_truco"]
        }, room=codigo)

    elif decision == 'no_quiero':
        partida["fase_truco"] = "terminada"
        emit('mano_finalizada', {
            'bando_defensor': bando_respondente,
            'mensaje': f'El bando {bando_respondente} dijo NO QUIERO. Fin de la mano de cartas.'
        }, room=codigo)

# --- LOGICA COMPLEMENTARIA: SIETE Y MEDIO ---
PARTIDAS_SIETE = {}

@socketio.on('siete_crear_sala')
def handle_siete_crear(data):
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo in PARTIDAS_SIETE:
        emit('error', {'mensaje': 'Ese código de sala ya existe en Siete y Medio.'})
        return

    # Inicializamos un mazo limpio para este juego usando tu V1
    instancia_juego = Truco()
    instancia_juego.iniciar_partida() 

    PARTIDAS_SIETE[codigo] = {
        "juego": instancia_juego,
        "jugadores": [id_sesion],
        "turno_actual": 0,
        "puntos_mesas": {}
    }
    
    join_room(codigo)
    emit('siete_sala_creada', {'rol': 'Jugador 1 (Banca)', 'codigo': codigo})


@socketio.on('siete_unirse_sala')
def handle_siete_unirse(data):
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS_SIETE:
        emit('error', {'mensaje': 'La sala de Siete y Medio no existe.'})
        return
        
    partida = PARTIDAS_SIETE[codigo]
    join_room(codigo)
    
    if len(partida["jugadores"]) < 2:
        partida["jugadores"].append(id_sesion)
        emit('siete_rol_asignado', {'rol': 'Jugador 2', 'codigo': codigo}, room=id_sesion)
        
        # Al estar los 2, arranca la partida automáticamente
        partida["turno_actual"] = 0
        emit('siete_partida_lista', {
            'mensaje': '¡Partida lista! J1 (Banca) empieza pidiendo carta.',
            'turno_actual_idx': 0
        }, room=codigo)
    else:
        emit('siete_rol_asignado', {'rol': 'Espectador', 'codigo': codigo}, room=id_sesion)


@socketio.on('siete_pedir_carta')
def handle_siete_pedir(data):
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS_SIETE: return
    partida = PARTIDAS_SIETE[codigo]
    
    if id_sesion not in partida["jugadores"]: return
    idx = partida["jugadores"].index(id_sesion)
    
    if idx != partida["turno_actual"]:
        emit('error', {'mensaje': 'No es tu turno de pedir.'})
        return
        
    try:
        # ✅ CORRECCIÓN DE TAD: Usamos el método nativo de tu V1 para desencadenar o desapilar del mazo
        carta_sacada = partida["juego"].mazo.robar_carta()
    except Exception as e:
        print(f"Error al robar carta: {e}")
        emit('error', {'mensaje': 'No se pudo robar la carta o el mazo está vacío.'})
        return
        
    if not carta_sacada:
        emit('error', {'mensaje': 'No quedan más cartas en el mazo.'})
        return
        
    # Mapeamos los valores según las reglas oficiales del Siete y Medio
    num = carta_sacada.valor
    valor_siete = float(num) if num < 10 else 0.5
    
    print(f"[{codigo} - 7.5] Jugador {idx + 1} pidió carta: {num} de {carta_sacada.palo}")
    
    emit('siete_carta_recibida', {
        'rol': f"Jugador {idx + 1}",
        'numero': num,
        'palo': str(carta_sacada.palo).lower(),
        'valor_siete': valor_siete
    }, room=codigo)


@socketio.on('siete_plantarse')
def handle_siete_plantar(data):
    codigo = data.get('codigo').upper()
    id_sesion = request.sid
    
    if codigo not in PARTIDAS_SIETE: return
    partida = PARTIDAS_SIETE[codigo]
    
    if id_sesion not in partida["jugadores"]: return
    idx = partida["jugadores"].index(id_sesion)
    
    if idx != partida["turno_actual"]: return

    if partida["turno_actual"] == 0:
        # Pasa el turno al J2 de forma estricta
        partida["turno_actual"] = 1
        print(f"[{codigo} - 7.5] Jugador 1 se plantó. Turno del Jugador 2.")
        emit('siete_cambio_turno', {
            'turno_actual_idx': 1,
            'mensaje': 'Jugador 1 se plantó. Turno del Jugador 2.'
        }, room=codigo)
    else:
        # Ya se plantaron ambos. Fin de la ronda
        print(f"[{codigo} - 7.5] Ambos jugadores se plantaron. Fin del juego.")
        emit('siete_juego_terminado', {
            'mensaje': '¡Ambos jugadores se plantaron! Verifiquen sus cartas para ver quién ganó.'
        }, room=codigo)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)