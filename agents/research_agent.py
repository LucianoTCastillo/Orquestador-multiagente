import sqlite3
import unicodedata
from typing import Any

from langchain_core.messages import AIMessage

from state import OrchestratorState


# Datos ficticios utilizados exclusivamente para la demostración.
DEMO_SALES = [
    ("Llaveros", 50, 1300.0),
    ("Miniaturas", 12, 4500.0),
    ("Dummys", 8, 6500.0),
]


def normalize_text(text: str) -> str:
    """Convierte a minúsculas y elimina acentos para facilitar búsquedas."""
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )


def search_sales(query: str) -> list[dict[str, Any]]:
    """Herramienta que consulta ventas ficticias en una base SQLite."""
    normalized_query = normalize_text(query)

    aliases = {
        "Llaveros": ("llavero",),
        "Miniaturas": ("miniatura",),
        "Dummys": ("dummy", "dummys", "dummies"),
    }

    selected_products = [
        product
        for product, keywords in aliases.items()
        if any(keyword in normalized_query for keyword in keywords)
    ]

    # Una consulta general sobre ventas recupera todos los productos.
    if not selected_products and any(
        keyword in normalized_query
        for keyword in ("venta", "producto", "facturacion", "ingreso")
    ):
        selected_products = list(aliases)

    # No inventamos resultados para consultas fuera de este ejemplo.
    if not selected_products:
        return []

    # La base se crea en memoria: no requiere instalar un servidor.
    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            """
            CREATE TABLE sales (
                product TEXT PRIMARY KEY,
                units INTEGER NOT NULL,
                unit_price REAL NOT NULL
            )
            """
        )

        connection.executemany(
            "INSERT INTO sales VALUES (?, ?, ?)",
            DEMO_SALES,
        )

        placeholders = ", ".join("?" for _ in selected_products)

        rows = connection.execute(
            f"""
            SELECT product, units, unit_price
            FROM sales
            WHERE product IN ({placeholders})
            ORDER BY product
            """,
            selected_products,
        ).fetchall()

    return [
        {
            "product": product,
            "units": units,
            "unit_price": unit_price,
            "currency": "ARS",
            "source": "SQLite: tabla sales (datos ficticios)",
        }
        for product, units, unit_price in rows
    ]


def research_agent(state: OrchestratorState) -> dict[str, Any]:
    """Consulta la herramienta y devuelve los datos al estado compartido."""
    data = search_sales(state["user_query"])

    if data:
        details = "\n".join(
            f"- {item['product']}: {item['units']} unidades, "
            f"precio unitario ARS {item['unit_price']:.2f}."
            for item in data
        )

        summary = (
            "Investigación realizada sobre ventas ficticias.\n"
            f"{details}\n"
            "Fuente: SQLite, tabla sales."
        )
    else:
        summary = (
            "No se encontraron datos para esta consulta. "
            "La demostración contiene ventas de llaveros, "
            "miniaturas y dummys."
        )

    contribution = {
        "agent": "researcher",
        "tool": "search_sales",
        "summary": summary,
    }

    return {
        "research_data": data,
        "research_summary": summary,
        # Una nueva investigación invalida los cálculos anteriores.
        "analysis_results": {},
        "analysis_summary": "",
        "task_completed": False,
        "contributions": [
            *state.get("contributions", []),
            contribution,
        ],
        "messages": [
            AIMessage(content=summary, name="researcher")
        ],
        "steps": state.get("steps", 0) + 1,
    }

def research_agent_api(
    state: OrchestratorState,
) -> dict[str, Any]:
    """Investigador con IA y una herramienta de consulta a SQLite."""
    import json

    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    from config import get_llm

    # Conservamos los datos reales devueltos por la herramienta.
    # No extraemos cifras del texto generado por el modelo.
    retrieved_records: dict[str, dict[str, Any]] = {}
    tool_calls = []

    @tool
    def search_sales_database(query: str) -> str:
        """Consulta ventas ficticias de llaveros, miniaturas y dummys.

        Usá los nombres de los productos solicitados. Para consultar
        todo el catálogo, usá 'ventas de todos los productos'.
        Devuelve unidades, precio unitario, moneda y fuente.
        """
        records = search_sales(query)

        for record in records:
            retrieved_records[record["product"]] = record

        tool_calls.append(query)

        return json.dumps(records, ensure_ascii=False)

    agent = create_react_agent(
        model=get_llm(),
        tools=[search_sales_database],
        prompt=(
            "Sos un investigador especializado en recuperar datos "
            "de ventas de una base SQLite de demostración. "
            "El catálogo contiene llaveros, miniaturas y dummys. "
            "Consultá la herramienta para obtener datos; no inventes "
            "productos, cantidades, precios ni fuentes. "
            "Consultá únicamente los productos que pide el usuario, "
            "o todo el catálogo si la solicitud es general. "
            "Si el pedido está fuera del catálogo, explicá la limitación. "
            "No calcules facturación: esa tarea corresponde al analista. "
            "Respondé en español, indicá la fuente y aclarа que los datos "
            "son ficticios. Considerá las observaciones del supervisor."
        ),
    )

    instruction = (
        f"Solicitud del usuario: {state['user_query']}\n"
        "Observaciones del supervisor: "
        f"{state.get('validation_feedback', '')}"
    )

    response = agent.invoke(
        {"messages": [HumanMessage(content=instruction)]},
        config={"recursion_limit": 12},
    )

    content = response["messages"][-1].content

    summary = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False)
    )

    if not tool_calls:
        summary = (
            "El investigador no utilizó la herramienta. "
            "No hay datos verificados disponibles.\n"
            f"{summary}"
        )

    return {
        "research_data": list(retrieved_records.values()),
        "research_summary": summary,
        "analysis_results": {},
        "analysis_summary": "",
        "task_completed": False,
        "contributions": [
            *state.get("contributions", []),
            {
                "agent": "researcher",
                "tool": "search_sales_database",
                "summary": summary,
            },
        ],
        "messages": [
            AIMessage(content=summary, name="researcher")
        ],
        "steps": state.get("steps", 0) + 1,
    }