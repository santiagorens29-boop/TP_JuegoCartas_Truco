from tads.lista_enlazada import ListaEnlazada

class Pila:
    # Invariante: 'self.estructura' debe ser siempre una instancia válida de ListaEnlazada.
    # El elemento en el tope de la pila siempre corresponde al nodo cabeza de la lista enlazada.

    def __init__(self):
        """
        PRE: Ninguna.
        POST: Inicializa una pila vacía utilizando una ListaEnlazada interna.
        """
        # Acá está el secreto: tu estructura interna es la ListaEnlazada que programaste
        self.estructura = ListaEnlazada()

    def is_empty(self):
        """
        PRE: La pila debe estar inicializada.
        POST: Devuelve True si la pila no tiene elementos, False en caso contrario.
        """
        # Le delegamos la responsabilidad a la lista enlazada
        return self.estructura.is_empty()

    def push(self, item):
        """
        PRE: Recibe el elemento que se desea apilar.
        POST: Agrega el elemento en el tope de la pila (al inicio de la lista enlazada).
        """
        # Insertamos al inicio para que sea O(1)
        self.estructura.insertar_inicio(item)

    def pop(self):
        """
        PRE: La pila no debe estar vacía.
        POST: Elimina y devuelve el elemento que está en el tope de la pila. 
              Si está vacía, levanta un error o devuelve un mensaje.
        """
        if self.is_empty():
            return "La pila está vacía"
        
        # El tope de la pila es la cabeza de nuestra lista enlazada
        item_tope = self.estructura.cabeza.dato
        
        # Usamos el método eliminar que programamos para sacarlo de la estructura
        self.estructura.eliminar_elemento(item_tope)
        
        return item_tope

    def peek(self):
        """
        PRE: La pila no debe estar vacía.
        POST: Devuelve el elemento en el tope de la pila sin eliminarlo.
        """
        if self.is_empty():
            return "La pila está vacía"
        
        # Solo miramos el dato de la cabeza sin borrar nada
        return self.estructura.cabeza.dato

    def __str__(self):
        """
        PRE: Ninguna.
        POST: Devuelve la representación en texto de los elementos de la pila.
        """
        # Como tu ListaEnlazada ya tiene su propio __str__, ¡lo reutilizamos!
        return str(self.estructura)
