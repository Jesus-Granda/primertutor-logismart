"""Ejecuta las pruebas unitarias de la carpeta pruebas/.

Uso:  python correr_pruebas.py
Las pruebas usan una base de datos simulada y un LLM simulado: no tocan MongoDB ni Ollama.
"""
import sys
import unittest

cargador = unittest.TestLoader()
cargador.testMethodPrefix = "prueba"          # métodos que empiezan con "prueba_"
suite = cargador.discover("pruebas", pattern="prueba_*.py")
resultado = unittest.TextTestRunner(verbosity=2).run(suite)
print("\nResultado:", "TODAS LAS PRUEBAS PASARON" if resultado.wasSuccessful() else "HAY PRUEBAS CON FALLAS")
sys.exit(0 if resultado.wasSuccessful() else 1)
