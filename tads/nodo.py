class Nodo:

    def __init__(self, dato):
        """
        PRE: Recibe un dato que se desea almacenar.
        POST: El nodo queda inicializado con el dato y sin un nodo siguiente.
        """
        self.dato = dato
        self.siguiente = None



    def __str__(self):
        """
        PRE: El nodo debe estar inicializado.
        POST: Devuelve la representación en cadena de texto del dato almacenado.
        """
        return str(self.dato)
