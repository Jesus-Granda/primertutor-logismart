"""Pruebas del motor de reglas. Ejecutar: python correr_pruebas.py"""
import unittest
from itertools import product

from capa_logica import reglas


class PruebaReglasOriginales(unittest.TestCase):
    # Tabla escrita A MANO (P,Q,R,S) -> (A,E), igual que en el script original
    ESPERADO = {
        (1, 1, 1, 1): (0, 1), (1, 1, 1, 0): (0, 1), (1, 1, 0, 1): (0, 1), (1, 1, 0, 0): (0, 1),
        (1, 0, 1, 1): (1, 1), (1, 0, 1, 0): (0, 1), (1, 0, 0, 1): (1, 0), (1, 0, 0, 0): (0, 0),
        (0, 1, 1, 1): (0, 0), (0, 1, 1, 0): (0, 0), (0, 1, 0, 1): (0, 0), (0, 1, 0, 0): (0, 0),
        (0, 0, 1, 1): (0, 0), (0, 0, 1, 0): (0, 0), (0, 0, 0, 1): (0, 0), (0, 0, 0, 0): (0, 0),
    }

    def prueba_tabla_original_sin_reglas_nuevas(self):
        # Con H=V y F=F las reglas nuevas no intervienen: debe coincidir con el script original
        for (P, Q, R, S), (A, E) in self.ESPERADO.items():
            r = reglas.evaluar(bool(P), bool(Q), bool(R), bool(S), True, False)
            self.assertEqual((r["A"], r["E"]), (bool(A), bool(E)), f"P={P} Q={Q} R={R} S={S}")

    def prueba_tipo_invalido(self):
        with self.assertRaises(TypeError):
            reglas.evaluar(1, False, False, True)


class PruebaReglasNuevas(unittest.TestCase):
    def prueba_r3_peligrosos_fuera_de_horario(self):
        r = reglas.evaluar(True, False, True, True, H=False)
        self.assertFalse(r["A"])
        self.assertTrue(r["E"])
        self.assertEqual(r["decision"], "ENVIAR A INSPECCIÓN ESPECIAL")

    def prueba_r4_fatiga(self):
        r = reglas.evaluar(True, False, False, True, F=True)
        self.assertFalse(r["A"])
        self.assertTrue(r["E"])

    def prueba_fatiga_sin_autorizacion_no_inspecciona(self):
        r = reglas.evaluar(False, False, False, True, F=True)
        self.assertEqual((r["A"], r["E"]), (False, False))

    def prueba_explicacion_presente(self):
        r = reglas.evaluar(True, True, False, True)
        self.assertEqual(len(r["pasos"]), 4)
        self.assertTrue(any("peso" in c for c in r["causas"]))


class PruebaAnalisis(unittest.TestCase):
    def prueba_sin_contradicciones_ni_redundancias(self):
        a = reglas.analizar()
        self.assertEqual(a["contradicciones"], [])
        self.assertEqual(a["redundantes"], [])
        self.assertEqual(a["efecto_por_regla"]["R3"]["E"], 0)  # R3 solo afecta A

    def prueba_tablas(self):
        self.assertEqual(len(reglas.tabla_completa()), 64)
        for filas in reglas.tablas_verdad().values():
            self.assertTrue(filas)

    def prueba_a_implica_premisas(self):
        for vals in product([True, False], repeat=6):
            A, _ = reglas.calcular(*vals)
            P, Q, R, S, H, F = vals
            if A:
                self.assertTrue(P and S and not Q and not F and not (R and not H))


if __name__ == "__main__":
    unittest.main()
