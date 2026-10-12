import math
from decimal import Decimal
from typing import Any

from langchain_core.messages import AIMessage

from state import OrchestratorState


def analyze_sales(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Valida los datos y calcula la facturación por producto."""
    if not data:
        return {
            "valid": False,
            "errors": ["No hay datos de ventas para analizar."],
        }

    errors = []
    products = []
    seen_products = set()

    for position, item in enumerate(data, start=1):
        product = item.get("product")
        units = item.get("units")
        unit_price = item.get("unit_price")

        if not isinstance(product, str) or not product.strip():
            errors.append(f"Registro {position}: producto inválido.")
            continue

        if product in seen_products:
            errors.append(f"Producto duplicado: {product}.")
            continue

        seen_products.add(product)

        if (
            isinstance(units, bool)
            or not isinstance(units, int)
            or units < 0
        ):
            errors.append(f"{product}: cantidad de unidades inválida.")
            continue

        if (
            isinstance(unit_price, bool)
            or not isinstance(unit_price, (int, float))
            or not math.isfinite(unit_price)
            or unit_price < 0
        ):
            errors.append(f"{product}: precio unitario inválido.")
            continue

        if item.get("currency") != "ARS":
            errors.append(f"{product}: se esperaba moneda ARS.")
            continue

        if not item.get("source"):
            errors.append(f"{product}: falta la fuente de los datos.")
            continue

        # Decimal evita errores habituales de precisión con dinero.
        revenue = Decimal(str(unit_price)) * units

        products.append({
            "product": product,
            "units": units,
            "unit_price": str(Decimal(str(unit_price))),
            "revenue": str(revenue),
            "currency": "ARS",
            "source": item["source"],
        })

    # Si hay errores, no presentamos un total parcial como completo.
    if errors:
        return {
            "valid": False,
            "errors": errors,
        }

    total_revenue = sum(
        (Decimal(item["revenue"]) for item in products),
        Decimal("0"),
    )

    highest_revenue = max(
        Decimal(item["revenue"]) for item in products
    )

    leaders = [
        item["product"]
        for item in products
        if Decimal(item["revenue"]) == highest_revenue
    ]

    return {
        "valid": True,
        "errors": [],
        "products": products,
        "total_units": sum(item["units"] for item in products),
        "total_revenue": str(total_revenue),
        "top_products": leaders,
        "highest_revenue": str(highest_revenue),
        "currency": "ARS",
    }


def analyst_agent(state: OrchestratorState) -> dict[str, Any]:
    """Analiza los datos disponibles y registra su aporte."""
    results = analyze_sales(state.get("research_data", []))

    if results["valid"]:
        details = "\n".join(
            f"- {item['product']}: ARS "
            f"{Decimal(item['revenue']):.2f} de facturación."
            for item in results["products"]
        )

        leaders = ", ".join(results["top_products"])

        summary = (
            "Análisis de ventas ficticias:\n"
            f"{details}\n"
            f"Unidades totales: {results['total_units']}.\n"
            "Facturación total: ARS "
            f"{Decimal(results['total_revenue']):.2f}.\n"
            f"Mayor facturación: {leaders}.\n"
            "La facturación corresponde a unidades × precio unitario. "
            "No representa ganancia, porque no contamos con costos."
        )

        feedback = ""
    else:
        feedback = "\n".join(results["errors"])
        summary = (
            "No se pudo completar el análisis. "
            "Se deben revisar los siguientes problemas:\n"
            f"{feedback}"
        )

    contribution = {
        "agent": "analyst",
        "tool": "analyze_sales",
        "summary": summary,
    }

    return {
        "analysis_results": results,
        "analysis_summary": summary,
        "validation_feedback": feedback,
        "contributions": [
            *state.get("contributions", []),
            contribution,
        ],
        "messages": [
            AIMessage(content=summary, name="analyst")
        ],
        "steps": state.get("steps", 0) + 1,
    }

def analyst_agent_api(
    state: OrchestratorState,
) -> dict[str, Any]:
    """Analista con IA que utiliza una herramienta de cálculo."""
    import json

    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    from config import get_llm

    verified_results: dict[str, Any] = {}
    tool_calls = []

    @tool
    def calculate_sales() -> str:
        """Valida y analiza los registros recuperados por el investigador.

        Calcula facturación por producto, facturación total,
        unidades totales y productos con mayor facturación.
        Devuelve valid=False y los errores si los datos son inválidos.
        """
        results = analyze_sales(state.get("research_data", []))

        verified_results.clear()
        verified_results.update(results)
        tool_calls.append("calculate_sales")

        return json.dumps(results, ensure_ascii=False)

    agent = create_react_agent(
        model=get_llm(),
        tools=[calculate_sales],
        prompt=(
            "Sos un analista especializado en ventas. "
            "Debés usar calculate_sales antes de presentar resultados. "
            "La herramienta trabaja con los datos del investigador. "
            "No inventes ni modifiques cantidades, precios o cálculos. "
            "Si valid es False, explicá los errores y solicitá revisión. "
            "Si valid es True, explicá la facturación de cada producto, "
            "el total, las unidades totales y los productos líderes. "
            "Respetá los empates. "
            "La facturación no es ganancia: no hay datos de costos. "
            "Los datos son ficticios y la moneda es ARS. "
            "Respondé en español y considerá las observaciones "
            "del supervisor."
        ),
    )

    instruction = (
        f"Solicitud del usuario: {state['user_query']}\n"
        "Datos recuperados:\n"
        f"{json.dumps(state.get('research_data', []), ensure_ascii=False)}\n"
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
        verified_results = {
            "valid": False,
            "errors": ["El analista no utilizó la herramienta de cálculo."],
        }

    if verified_results.get("valid"):
        feedback = ""
    else:
        feedback = "\n".join(
            verified_results.get(
                "errors",
                ["No se obtuvieron resultados verificados."],
            )
        )

        summary = (
            f"Análisis pendiente de validación:\n{feedback}\n\n"
            f"{summary}"
        )

    return {
        "analysis_results": verified_results,
        "analysis_summary": summary,
        "validation_feedback": feedback,
        "contributions": [
            *state.get("contributions", []),
            {
                "agent": "analyst",
                "tool": "calculate_sales",
                "summary": summary,
            },
        ],
        "messages": [
            AIMessage(content=summary, name="analyst")
        ],
        "steps": state.get("steps", 0) + 1,
    }