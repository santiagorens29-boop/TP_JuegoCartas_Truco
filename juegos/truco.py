from juegos.juego_cartas import JuegoCartas
from modelos.fabrica_mazos import FabricaMazos
from tads.lista_enlazada import ListaEnlazada

class Truco(JuegoCartas):
    def __init__(self):
        """
        PRE: Ninguna.
        POST: Inicializa el Truco Argentino configurando el mazo español y los puntajes en 0.
        """
        super().__init__("Espanola") # Invoca al constructor padre con la baraja requerida
        self.puntaje_j1 = 0
        self.puntaje_j2 = 0
        self.cartas_por_mano = 3 # Exigido por la dinámica del juego y diseño base

    def asignar_pesos_truco(self):
        """
        PRE: El mazo de la partida ya debe estar creado y poblado en self.mazo.
        POST: Modifica el atributo 'peso_puntuacion' de cada carta dentro del mazo 
              según la escala de poder del Truco Argentino.
        """
        # Recorremos el mazo usando el iterador de nuestra lista enlazada interna de la Pila
        for carta in self.mazo.pila_cartas.estructura:
            v = carta.valor
            p = carta.palo

            # Evaluamos las cartas de poder más altas (Las "bravas")
            if v == 1 and p == "Espada": carta.peso_puntuacion = 14
            elif v == 1 and p == "Basto": carta.peso_puntuacion = 13
            elif v == 7 and p == "Espada": carta.peso_puntuacion = 12
            elif v == 7 and p == "Oro": carta.peso_puntuacion = 11
            # Cartas comunes ordenadas por valor numérico tradicional
            elif v == 3: carta.peso_puntuacion = 10
            elif v == 2: carta.peso_puntuacion = 9
            elif v == 1: carta.peso_puntuacion = 8  # Copas y Oros
            elif v == 12: carta.peso_puntuacion = 7
            elif v == 11: carta.peso_puntuacion = 6
            elif v == 10: carta.peso_puntuacion = 5
            elif v == 7: carta.peso_puntuacion = 4   # Bastos y Copas
            elif v == 6: carta.peso_puntuacion = 3
            elif v == 5: carta.peso_puntuacion = 2
            elif v == 4: carta.peso_puntuacion = 1
            else: carta.peso_puntuacion = 0         # Comodines u otras si las hubiera

    def iniciar_partida(self):
        """
        PRE: Debe haber exactamente 2 jugadores agregados en la lista de jugadores.
        POST: Genera el mazo a través de la fábrica, baraja, le asigna las reglas de peso y deja listo el inicio.
        """
        # 1. Pedimos el mazo a la fábrica
        self.mazo = FabricaMazos.crear_mazo(self.tipo_baraja)
        
        # 2. Le inyectamos los pesos jerárquicos del Truco
        self.asignar_pesos_truco()
        
        # 3. Mezclamos de forma legal
        self.mazo.barajar()

    def evaluar_envido(self, carta1, carta2):
        """
        PRE: Recibe dos objetos de tipo Carta pertenecientes al mismo palo.
        POST: Retorna el puntaje de envido correspondiente (suma de valores + 20). 
              Los valores de 10, 11 y 12 suman 0 puntos.
        """
        val1 = carta1.valor if carta1.valor < 10 else 0
        val2 = carta2.valor if carta2.valor < 10 else 0
        return val1 + val2 + 20