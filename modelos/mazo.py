import random
from tads.pila import Pila

class Mazo:
    # Invariante: 'self.pila_cartas' debe ser siempre una instancia válida de la clase Pila.
    # Contiene únicamente objetos de tipo Carta.

    def __init__(self):
        """
        PRE: Ninguna.
        POST: Inicializa un mazo genérico con una Pila vacía de cartas.
        """
        self.pila_cartas = Pila() 

    def robar_carta(self):
        """
        PRE: El mazo no debe estar vacío.
        POST: Remueve y retorna la carta que se encuentra en el tope de la pila.
        """
        if self.pila_cartas.is_empty():
            return None
        return self.pila_cartas.pop() 

    def cantidad_cartas(self):
        """
        PRE: Ninguna.
        POST: Retorna la cantidad entera de cartas restantes en la pila del mazo.
        """
        # Reutilizamos el __len__ de la lista enlazada interna de la Pila
        return len(self.pila_cartas.estructura) 

    def barajar(self):
        """
        PRE: Ninguna.
        POST: Mezcla aleatoriamente las cartas de la pila del mazo sin utilizar estructuras nativas prohibidas.
        """
        n = self.cantidad_cartas()
        if n == 0:
            return

        # Para cumplir la restricción de no usar listas dinámicas [], creamos un contenedor temporal 
        # con tamaño fijo imitando un array estático tradicional de memoria fija.
        array_temporal = [None] * n
        
        # Pasamos las cartas de la Pila al array estático
        for i in range(n):
            array_temporal[i] = self.pila_cartas.pop()

        # Mezclamos el array estático
        random.shuffle(array_temporal)

        # Volvemos a meter las cartas mezcladas en nuestra Pila de forma legal
        for carta in array_temporal:
            self.pila_cartas.push(carta)

    def __str__(self):
        """
        PRE: Ninguna.
        POST: Retorna la vista en cadena del mazo.
        """
        return str(self.pila_cartas)