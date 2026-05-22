from modelos.mazo import Mazo
from modelos.carta import Carta

class FabricaMazos:
    @staticmethod
    def crear_mazo(tipo_baraja):
        """
        PRE: 'tipo_baraja' debe ser un string indicando el tipo (ej. "Espanola", "Poker", "UNO").
        POST: Retorna una instancia de Mazo cargada con las cartas específicas correspondientes.
        """
        mazo_nuevo = Mazo()

        if tipo_baraja == "Espanola": 
            palos = ["Oro", "Copa", "Espada", "Basto"] 
            valores = [1, 2, 3, 4, 5, 6, 7, 10, 11, 12] # Tradicionales para el Truco (sin 8 ni 9) 
            
            # Cargamos las cartas estándar
            for palo in palos:
                for valor in valores:
                    # Asignamos un peso por defecto, después la Estrategia del Truco definirá el real
                    carta = Carta(valor, palo) 
                    mazo_nuevo.pila_cartas.push(carta)
            
            # Añadimos los dos comodines requeridos por la consigna
            mazo_nuevo.pila_cartas.push(Carta("Comodín", "Especial")) 
            mazo_nuevo.pila_cartas.push(Carta("Comodín", "Especial")) 

        elif tipo_baraja == "Poker":
            palos = ["Picas", "Corazones", "Diamantes", "Tréboles"]
            # Aquí poblarías con la lógica de Poker de forma independiente
            pass

        elif tipo_baraja == "UNO":
            colors = ["Rojo", "Azul", "Verde", "Amarillo"]
            # Aquí poblarías con cartas de números y efectos especiales de UNO
            pass

        return mazo_nuevo