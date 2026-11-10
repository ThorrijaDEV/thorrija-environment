"""
Configuración pytest para tests de Thorrija Environment.
"""

import sys
from pathlib import Path

# Añadir src al path para todos los tests
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Configuración de pytest
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: tests unitarios")
    config.addinivalue_line("markers", "integration: tests de integración")
    config.addinivalue_line("markers", "slow: tests lentos")


def pytest_collection_modifyitems(config, items):
    # Marcar tests de integración automáticamente
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker("integration")
        else:
            item.add_marker("unit")