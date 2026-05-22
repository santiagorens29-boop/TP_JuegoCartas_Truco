from tads.nodo import Nodo

class ListaEnlazada:
    # Invariante: 'self.cabeza' debe ser None o una instancia válida de la clase Nodo.
    # Todos los nodos encadenados deben apuntar secuencialmente hasta que el último apunte a None.

    def __init__(self):
        """
        PRE: Ninguna.  
        POST: Se crea una instancia de ListaEnlazada con su referencia 
        inicial (cabeza) apuntando a None, representando una lista vacía.
        """
        self.cabeza = None

    def is_empty(self):
        """
        PRE: La lista debe estar inicializada.
        POST: Devuelve True si la lista no contiene ningún nodo y False en caso contrario.
        """
        return self.cabeza is None
    
    def insertar_inicio(self, dato):
        """
        PRE: Recibe un dato que se desea insertar al principio de la lista.
        POST: El dato queda almacenado en un nuevo nodo que pasa a ser la cabeza de la lista.
        """
        nuevo = Nodo(dato)
        nuevo.siguiente = self.cabeza
        self.cabeza = nuevo

    def insertar_final(self, dato):
        """
        PRE: Recibe un dato para agregar al final.
        POST: El dato se guarda en un nuevo nodo al final de la lista.
        """
        nuevo = Nodo(dato)
        if self.is_empty():
            self.cabeza = nuevo
        else:
            aux = self.cabeza
            while aux.siguiente is not None:
                aux = aux.siguiente
            aux.siguiente = nuevo

    def eliminar_elemento(self, valor):
        """
        PRE: Recibe el valor/elemento específico que se desea eliminar de la lista.
        POST: Si el elemento existe, se remueve de la lista reestructurando los enlaces y se retorna True. 
              Si no existe o la lista está vacía, retorna False.
        """
        if self.is_empty():
            return False
            
        # Caso 1: El elemento a eliminar está en la cabeza
        if self.cabeza.dato == valor:
            self.cabeza = self.cabeza.siguiente
            return True
            
        # Caso 2: Buscar en el resto de la lista
        aux = self.cabeza
        while aux.siguiente is not None:
            if aux.siguiente.dato == valor:
                aux.siguiente = aux.siguiente.siguiente
                return True
            aux = aux.siguiente
        return False

    def buscar_elemento(self, valor):
        """
        PRE: Recibe un valor a buscar.
        POST: Retorna True si el elemento se encuentra en la lista, de lo contrario False.
        """
        aux = self.cabeza
        while aux is not None:
            if aux.dato == valor:
                return True
            aux = aux.siguiente
        return False

    # --- MÉTODOS MÁGICOS REQUERIDOS ---

    def __len__(self):
        """
        PRE: Ninguna.
        POST: Retorna la cantidad total de elementos (nodos) en la lista de forma entera.
        """
        contador = 0
        aux = self.cabeza
        while aux is not None:
            contador += 1
            aux = aux.siguiente
        return contador

    def __str__(self):
        """
        PRE: Ninguna.
        POST: Retorna una representación en cadena de los elementos de la lista.
        """
        valores = []
        aux = self.cabeza
        while aux is not None:
            valores.append(str(aux.dato)) # Usamos append temporal para construir el string de salida legible
            aux = aux.siguiente
        return " -> ".join(valores) if valores else "Lista Vacía"

    def __iter__(self):
        """
        PRE: Ninguna.
        POST: Permite iterar la lista enlazada utilizando estructuras de control como 'for ... in ...'.
        """
        aux = self.cabeza
        while aux is not None:
            yield aux.dato
            aux = aux.siguiente
           
           
           
        

