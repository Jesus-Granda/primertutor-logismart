"""Pruebas de la matriz de riesgos y del asistente RAG (con MongoDB simulado)."""
import unittest
from unittest import mock

import mongomock

import datos_demo
from capa_datos import basedatos as bd
from capa_logica import asistente, riesgos


class PruebaRiesgos(unittest.TestCase):
    def prueba_niveles(self):
        self.assertEqual(riesgos.nivel(20), "crítico")
        self.assertEqual(riesgos.nivel(12), "alto")
        self.assertEqual(riesgos.nivel(6), "medio")
        self.assertEqual(riesgos.nivel(4), "bajo")

    def prueba_residual(self):
        d = riesgos.documento("Mod", "desc", "sesgo", 4, 5, "mitigar", 2, 3)
        self.assertEqual((d["puntaje_inherente"], d["puntaje_residual"]), (20, 6))
        self.assertEqual(d["reduccion_pct"], 70.0)

    def prueba_residual_mayor_invalido(self):
        with self.assertRaises(ValueError):
            riesgos.documento("Mod", "desc", "sesgo", 1, 1, "x", 5, 5)

    def prueba_categoria_invalida(self):
        with self.assertRaises(ValueError):
            riesgos.documento("Mod", "desc", "inventada", 2, 2, "x", 1, 1)


class PruebaAsistenteYDatosDemo(unittest.TestCase):
    def setUp(self):
        bd.usar_bd(mongomock.MongoClient().db)
        datos_demo.cargar()

    def tearDown(self):
        bd.usar_bd(None)

    def prueba_datos_demo(self):
        for c in bd.COLECCIONES[:4]:
            self.assertGreater(bd.contar(c), 0, c)

    def prueba_sin_informacion_no_llama_al_llm(self):
        with mock.patch("capa_logica.llm.chat") as chat:
            texto, fuentes, _ = asistente.responder("¿Por qué CAM-999 fue enviado a inspección?")
        chat.assert_not_called()
        self.assertEqual(texto, asistente.SIN_INFO)
        self.assertEqual(fuentes, [])

    def prueba_registra_en_evaluaciones(self):
        with mock.patch("capa_logica.llm.chat", return_value=("CAM-102 fue a inspección.", 0.1)):
            asistente.responder("¿Por qué CAM-102 fue enviado a inspección?")
        ev = bd.listar("evaluaciones_llm", {"origen": "asistente"})
        self.assertEqual(len(ev), 1)
        self.assertTrue({"prompt", "respuesta", "modelo", "latencia_s"} <= set(ev[0]))

    def prueba_respaldo_sin_ollama(self):
        from capa_logica import llm
        with mock.patch("capa_logica.llm.chat", side_effect=llm.ErrorLLM("sin conexión")):
            texto, fuentes, _ = asistente.responder("¿Por qué CAM-102 fue enviado a inspección?")
        self.assertIn("ENVIAR A INSPECCIÓN ESPECIAL", texto)
        self.assertTrue(fuentes)

    def prueba_filtra_denegados(self):
        docs = [d for f, d in asistente.recuperar("¿Qué camiones fueron denegados?") if f.startswith("accesos/")]
        self.assertTrue(docs)
        self.assertTrue(all(d["decision"] == "ACCESO DENEGADO" for d in docs))

    def prueba_recupera_cam102(self):
        docs = asistente.recuperar("¿Por qué CAM-102 fue enviado a inspección?")
        self.assertTrue(any(f.startswith("accesos/") for f, _ in docs))
        self.assertTrue(any(f.startswith("camiones/") for f, _ in docs))

    def prueba_esquema_de_colecciones(self):
        """Cada colección tiene los campos que pide la actividad."""
        requeridos = {
            "camiones": {"placa", "camion_id", "empresa", "autorizacion", "certificacion_conductor"},
            "accesos": {"P", "Q", "R", "S", "A", "E", "marca_tiempo", "operador", "explicacion"},
            "incidentes": {"correo_original", "clasificacion", "datos_extraidos", "estado", "historial"},
            "riesgos_eticos": {"modulo", "descripcion", "categoria", "probabilidad", "impacto", "mitigacion",
                               "historico", "puntaje_inherente", "puntaje_residual"},
        }
        for col, campos in requeridos.items():
            doc = bd.listar(col, limite=1)[0]
            self.assertTrue(campos <= set(doc), f"{col}: faltan {campos - set(doc)}")

    def prueba_agregacion(self):
        self.assertTrue(bd.incidentes_por_categoria_semana())


if __name__ == "__main__":
    unittest.main()
