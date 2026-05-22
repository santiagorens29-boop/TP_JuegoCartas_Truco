from tads.lista_enlazada import ListaEnlazada

class JuegoCartas:
    def __init__(self, tipo_baraja):
        """
        PRE: 'tipo_baraja' es un string (ej. "Espanola") que define qué mazo usar.
        POST: Inicializa el juego con un mazo vacío, una lista enlazada de jugadores y el estado activo.
        """
        self.tipo_baraja = tipo_baraja
        self.jugadores = ListaEnlazada()  # Guardará los nombres o clases de los jugadores
        self.mazo = None                  # Se asignará al iniciar la partida
        self.partida_terminada = False

    def agregar_jugador(self, nombre_jugador):
        """
        PRE: Recibe el nombre o identificador del jugador.
        POST: Agrega al jugador al final de la lista enlazada de la partida.
        """
        self.jugadores.insertar_final(nombre_jugador)

    def __str__(self):
        """
        PRE: Ninguna.
        POST: Retorna el estado actual resumido del juego.
        """
        return f"Juego de cartas tipo: {self.tipo_baraja}. Estado terminado: {self.partida_terminada}"