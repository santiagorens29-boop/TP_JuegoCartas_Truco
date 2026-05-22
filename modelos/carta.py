class Carta:
    def __init__(self, valor, palo, peso_puntuacion=0):
        """
        PRE: 'valor' puede ser entero o string (ej. 1, 'Reversa'). 'palo' / 'color' es un string.
        POST: Inicializa un naipe con sus atributos básicos y un peso numérico para comparaciones.
        """
        self.valor = valor
        self.palo = palo
        self.peso_puntuacion = peso_puntuacion # Clave para que funcione con cualquier regla de juego

    def __str__(self):
        """
        PRE: Ninguna.
        POST: Retorna la representación legible de la carta (ej. "1 de Espada").
        """
        return f"{self.valor} de {self.palo}"

    # --- MÉTODOS MÁGICOS DE COMPARACIÓN REQUERIDOS ---

    def __eq__(self, otra_carta):
        """
        PRE: 'otra_carta' debe ser una instancia de la clase Carta.
        POST: Retorna True si tienen el mismo peso de juego, False en caso contrario.
        """
        if not isinstance(otra_carta, Carta):
            return False
        return self.peso_puntuacion == otra_carta.peso_puntuacion

    def __lt__(self, otra_carta):
        """
        PRE: 'otra_carta' debe ser una instancia de la clase Carta.
        POST: Retorna True si esta carta es MENOS valiosa que la otra en el juego actual.
        """
        return self.peso_puntuacion < otra_carta.peso_puntuacion

    def __gt__(self, otra_carta):
        """
        PRE: 'otra_carta' debe ser una instancia de la clase Carta.
        POST: Retorna True si esta carta es MÁS valiosa que la otra en el juego actual.
        """
        return self.peso_puntuacion > otra_carta.peso_puntuacion 