from juegos.truco import Truco
from tads.lista_enlazada import ListaEnlazada

class GameManager:
    def __init__(self):
        """
        PRE: Ninguna.
        POST: Inicializa el GameManager con el control del juego en None.
        """
        self.juego = None

    def iniciar_programa(self):
        """
        PRE: Ninguna.
        POST: Controla el flujo de bienvenida, crea la partida de Truco y registra los jugadores.
        """
        print("=== BIENVENIDO AL JUEGO DE TRUCO INTERACTIVO (V1) ===")
        
        self.juego = Truco()
        
        print("\n--- Registro de Jugadores ---")
        j1 = input("Nombre del Jugador 1: ")
        j2 = input("Nombre del Jugador 2: ")
        
        self.juego.agregar_jugador(j1)
        self.juego.agregar_jugador(j2)
        
        self.juego.iniciar_partida()
        
        # Comenzamos la partida real por turnos
        self.jugar_partida(j1, j2)

    def mostrar_mano_oculta(self, nombre, mano):
        """
        PRE: 'nombre' es string y 'mano' es una ListaEnlazada de objetos Carta.
        POST: Muestra las opciones numéricas para que el jugador elija su carta.
        """
        print(f"\n==================================================")
        print(f"TURNO DE: {nombre} (No mires la pantalla si sos el otro!)")
        print(f"==================================================")
        print("Tus cartas:")
        
        # Recorremos la mano usando el iterador que programaste en tu ListaEnlazada
        indice = 1
        for carta in mano:
            print(f"[{indice}] {carta}")
            indice += 1

    def pedir_carta_valida(self, mano):
        """
        PRE: 'mano' es una ListaEnlazada de cartas.
        POST: Retorna el objeto Carta seleccionado y lo elimina de la mano del jugador.
        """
        cant = len(mano)
        while True:
            try:
                opcion = int(input(f"Elegí el número de carta a jugar (1-{cant}): "))
                if 1 <= opcion <= cant:
                    # Buscamos la carta correspondiente recorriendo la lista
                    aux = mano.cabeza
                    for _ in range(opcion - 1):
                        aux = aux.siguiente
                    
                    carta_elegida = aux.dato
                    # La removemos de la mano usando tu método eliminar
                    mano.eliminar_elemento(carta_elegida)
                    return carta_elegida
                else:
                    print("Número fuera de rango.")
            except ValueError:
                print("Por favor, ingresá un número válido.")

    def jugar_partida(self, j1, j2):
        """
        PRE: Nombres de jugadores registrados.
        POST: Simula el desarrollo de una mano de 3 rondas comparando los pesos de las cartas.
        """
        print("\n--- ¡Comienza la partida! Repartiendo... ---")
        
        mano_j1 = ListaEnlazada()
        mano_j2 = ListaEnlazada()
        
        for _ in range(self.juego.cartas_por_mano):
            mano_j1.insertar_final(self.juego.mazo.robar_carta())
            mano_j2.insertar_final(self.juego.mazo.robar_carta())

        rondas_ganadas_j1 = 0
        rondas_ganadas_j2 = 0

        # Simulación de las 3 manos/rondas del Truco
        for chico in range(1, 4):
            print(f"\n--- CHICO {chico} ---")
            
            # Jugador 1 elige carta
            self.mostrar_mano_oculta(j1, mano_j1)
            carta_j1 = self.pedir_carta_valida(mano_j1)
            
            # Jugador 2 elige carta
            self.mostrar_mano_oculta(j2, mano_j2)
            carta_j2 = self.pedir_carta_valida(mano_j2)
            
            # Mostramos el enfrentamiento
            print(f"\n--> {j1} jugó: {carta_j1}")
            print(f"--> {j2} jugó: {carta_j2}")
            
            # Comparamos las cartas usando los métodos mágicos __gt__ y __lt__ de tu clase Carta
            if carta_j1 > carta_j2:
                print(f"¡Ganó {j1} esta mano!")
                rondas_ganadas_j1 += 1
            elif carta_j2 > carta_j1:
                print(f"¡Ganó {j2} esta mano!")
                rondas_ganadas_j2 += 1
            else:
                print("¡Parda! (Empate de cartas)")
                rondas_ganadas_j1 += 1
                rondas_ganadas_j2 += 1

            # Verificación rápida de quién gana el punto del truco (mejor de 3)
            if rondas_ganadas_j1 >= 2 and rondas_ganadas_j1 > rondas_ganadas_j2:
                print(f"\n🏆 ¡{j1} se lleva los puntos de este Truco! 🏆")
                break
            elif rondas_ganadas_j2 >= 2 and rondas_ganadas_j2 > rondas_ganadas_j1:
                print(f"\n🏆 ¡{j2} se lleva los puntos de este Truco! 🏆")
                break
            elif rondas_ganadas_j1 == 3 and rondas_ganadas_j2 == 3:
                print("\n🏆 ¡Empate absoluto en esta mano! 🏆")
                break

# --- ARRANCAR EL JUEGO ---
if __name__ == "__main__":
    manager = GameManager()
    manager.iniciar_programa()