import json
from pathlib import Path


def markdown_cell(text):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code_cell(text):
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


cells = [
    markdown_cell(
        "# Demostración del orquestador multiagente\n\n"
        "Esta demo ejecuta el modo local con datos ficticios. "
        "No realiza llamadas a OpenAI ni consume créditos.\n\n"
        "Ejecutá las celdas en orden desde la carpeta del proyecto."
    ),
    code_cell(
        "from decimal import Decimal\n"
        "from main import build_graph, create_initial_state\n\n"
        "# Selección explícita del modo local.\n"
        "graph = build_graph(mode='local')\n"
        "print('Grafo local preparado, sin llamadas a OpenAI.')\n"
    ),
    markdown_cell(
        "## 1. Solicitud que requiere ambos especialistas\n\n"
        "El investigador recupera los registros y el analista calcula "
        "la facturación. El supervisor valida antes de finalizar."
    ),
    code_cell(
        "query = (\n"
        "    'Investigá las ventas de llaveros, miniaturas y dummys. '\n"
        "    'Calculá la facturación de cada producto y el total, '\n"
        "    'e indicá cuál generó más ingresos.'\n"
        ")\n"
        "initial_state = create_initial_state(query)\n"
        "print(query)\n"
    ),
    markdown_cell(
        "## 2. Flujo de delegación\n\n"
        "Cada bloque muestra un nodo ejecutado y su aporte."
    ),
    code_cell(
        "final_state = None\n"
        "for update in graph.stream(\n"
        "    initial_state,\n"
        "    config={'recursion_limit': 30},\n"
        "    stream_mode='updates',\n"
        "):\n"
        "    for node, changes in update.items():\n"
        "        print(f'\\nNODO: {node.upper()}')\n"
        "        if node == 'supervisor':\n"
        "            print('Destino:', changes['next_agent'])\n"
        "        print(changes['contributions'][-1]['summary'])\n"
        "        if node == 'supervisor' and changes['next_agent'] == 'FINISH':\n"
        "            final_state = changes\n"
    ),
    markdown_cell("## 3. Respuesta final y registro de aportes"),
    code_cell(
        "assert final_state is not None\n"
        "print(final_state['final_answer'])\n"
        "print('\\nCompletada:', final_state['task_completed'])\n"
        "print('Intervenciones:', final_state['steps'])\n\n"
        "agents = [item['agent'] for item in final_state['contributions']]\n"
        "print('Orden de participación:', agents)\n"
        "assert final_state['task_completed'] is True\n"
        "assert agents == [\n"
        "    'supervisor', 'researcher', 'supervisor', 'analyst', 'supervisor'\n"
        "]\n"
    ),
    markdown_cell(
        "## 4. Comprobación de los resultados\n\n"
        "Ejecutamos otra consulta para comprobar los importes "
        "del estado completo."
    ),
    code_cell(
        "result = graph.invoke(\n"
        "    create_initial_state(query),\n"
        "    config={'recursion_limit': 30},\n"
        ")\n"
        "analysis = result['analysis_results']\n"
        "assert Decimal(analysis['total_revenue']) == Decimal('171000')\n"
        "assert analysis['total_units'] == 70\n"
        "assert analysis['top_products'] == ['Llaveros']\n"
        "print('Resultados esperados verificados.')\n"
    ),
    markdown_cell(
        "## 5. Consulta sin datos disponibles\n\n"
        "Una consulta fuera del catálogo debe terminar "
        "sin afirmar que la tarea fue completada."
    ),
    code_cell(
        "missing = graph.invoke(\n"
        "    create_initial_state('Investiga bicicletas'),\n"
        "    config={'recursion_limit': 30},\n"
        ")\n"
        "print(missing['final_answer'])\n"
        "print('Completada:', missing['task_completed'])\n"
        "assert missing['task_completed'] is False\n"
    ),
    markdown_cell(
        "## Alcance de la demostración\n\n"
        "Se demuestra la delegación, el uso de herramientas, "
        "el registro de aportes y la finalización del modo local. "
        "El modo con API está implementado en el proyecto, "
        "pero no se ejecuta en este notebook."
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

for index, cell in enumerate(cells):
    cell["id"] = f"demo-{index:02d}"

path = Path(__file__).resolve().parent / "demo.ipynb"
path.write_text(
    json.dumps(notebook, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"Notebook creado: {path.name}")