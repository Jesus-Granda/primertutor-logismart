"""Pruebas del clasificador híbrido (sin Ollama: el LLM se simula)."""
import json
import unittest
from unittest import mock

import mongomock

from capa_datos import basedatos as bd
from capa_logica import clasificador as clf


VACIAS = {"placa": None, "camion_id": None, "peso_reportado_kg": None, "ubicacion": None}


def _respuesta(obj):
    return (json.dumps(obj) if not isinstance(obj, str) else obj), 0.05


class PruebaReglasYExtraccion(unittest.TestCase):
    def prueba_derrame_critico(self):
        c, palabras = clf.clasificar_reglas("URGENTE: derrame en andén 3",
                                            "El camión CAM-102 con placas ABC-123-D tiene fuga de químico. 48.5 toneladas")
        self.assertEqual((c.categoria, c.prioridad), ("materiales_peligrosos", "critica"))
        self.assertEqual(c.entidades.placa, "ABC-123-D")
        self.assertEqual(c.entidades.camion_id, "CAM-102")
        self.assertEqual(c.entidades.peso_reportado_kg, 48500)
        self.assertIn("urgente", palabras)

    def prueba_sin_datos_no_inventa(self):
        e = clf.extraer_datos("Hola", "¿A qué hora abre el comedor?")
        self.assertEqual(e.model_dump(), {"placa": None, "camion_id": None, "peso_reportado_kg": None, "ubicacion": None})

    def prueba_esquema_normaliza(self):
        c = clf.Clasificacion(categoria="Sobrepeso", prioridad="ALTA", resumen="abc",
                              entidades=dict(VACIAS, peso_reportado_kg="52,000 kg"))
        self.assertEqual(c.categoria, "sobrepeso")
        self.assertEqual(c.entidades.peso_reportado_kg, 52000)

    def prueba_esquema_invalido(self):
        with self.assertRaises(Exception):
            clf.Clasificacion(categoria="inventada", prioridad="alta", resumen="abc", entidades=VACIAS)

    def prueba_esquema_exacto(self):
        """El JSON debe traer exactamente categoria, prioridad, entidades y resumen."""
        with self.assertRaises(Exception):   # clave de más
            clf.Clasificacion(categoria="otro", prioridad="baja", resumen="abc", entidades=VACIAS, extra=1)
        with self.assertRaises(Exception):   # falta entidades
            clf.Clasificacion(categoria="otro", prioridad="baja", resumen="abc")
        with self.assertRaises(Exception):   # a entidades le falta una clave
            clf.Clasificacion(categoria="otro", prioridad="baja", resumen="abc", entidades={"placa": None})


class PruebaHibrido(unittest.TestCase):
    def setUp(self):
        bd.usar_bd(mongomock.MongoClient().db)

    def tearDown(self):
        bd.usar_bd(None)

    def prueba_reintento_y_respaldo(self):
        with mock.patch("capa_logica.llm.chat", return_value=_respuesta("esto no es json")):
            r = clf.hibrido("Sistema lento", "La aplicación está lenta", reintentos=1)
        self.assertEqual(r["metodo"], "reglas (respaldo)")
        self.assertEqual(r["intentos_llm"], 2)
        self.assertEqual(bd.contar("evaluaciones_llm"), 1)

    def prueba_discrepancia_gana_prioridad_alta(self):
        llm_dice = {"categoria": "falla_software", "prioridad": "baja", "entidades": VACIAS, "resumen": "texto"}
        with mock.patch("capa_logica.llm.chat", return_value=_respuesta(llm_dice)):
            r = clf.hibrido("Fuga", "Hay una fuga de químico en el muelle 2")
        self.assertEqual((r["categoria"], r["prioridad"]), ("materiales_peligrosos", "critica"))
        self.assertTrue(r["requiere_revision_humana"])

    def prueba_empate_prefiere_seguridad(self):
        reg = clf.Clasificacion(categoria="acceso_no_autorizado", prioridad="alta", resumen="abc", entidades=VACIAS)
        otro = clf.Clasificacion(categoria="sobrepeso", prioridad="alta", resumen="abc", entidades=VACIAS)
        final, _, revision, _ = clf.fusionar(reg, otro)
        self.assertEqual(final.categoria, "acceso_no_autorizado")
        self.assertTrue(revision)

    def prueba_entidad_alucinada_se_descarta(self):
        llm_dice = {"categoria": "sobrepeso", "prioridad": "media", "resumen": "exceso",
                    "entidades": {"placa": "ZZZ-999-Z", "camion_id": None, "peso_reportado_kg": 52000, "ubicacion": None}}
        with mock.patch("capa_logica.llm.chat", return_value=_respuesta(llm_dice)):
            r = clf.hibrido("Exceso de peso", "La báscula marcó 52 toneladas")
        self.assertIsNone(r["entidades"]["placa"])
        self.assertTrue(r["avisos"])


if __name__ == "__main__":
    unittest.main()
