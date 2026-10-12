from typing import Any, Literal

from langchain_core.messages import AIMessage

from agents.analyst_agent import analyze_sales
from state import OrchestratorState


def supervisor(state: OrchestratorState) -> dict[str, Any]:
    """Decide el siguiente paso y valida los resultados."""
    steps = state.get("steps", 0)
    max_steps = state.get("max_steps", 10)

    contributions = state.get("contributions", [])

    research_attempts = sum(
        item.get("agent") == "researcher"
        for item in contributions
    )

    analysis_attempts = sum(
        item.get("agent") == "analyst"
        for item in contributions
    )

    next_agent: Literal["researcher", "analyst", "FINISH"]
    feedback = ""
    final_answer = ""
    completed = False

    data = state.get("research_data", [])
    results = state.get("analysis_results", {})

    # Condición de parada: limita el flujo completo.
    if steps >= max_steps:
        next_agent = "FINISH"
        decision = "Se alcanzó el límite de pasos."
        feedback = decision
        final_answer = (
            "No se pudo completar y validar la tarea "
            "dentro del límite de pasos."
        )

    elif not data:
        if research_attempts < 2:
            next_agent = "researcher"
            decision = (
                "Solicitar al investigador datos de ventas "
                "con producto, unidades, precio, moneda y fuente."
            )

            if research_attempts:
                feedback = (
                    "La búsqueda anterior no obtuvo datos. "
                    "Revisá la consulta dentro del catálogo disponible."
                )
        else:
            next_agent = "FINISH"
            decision = "Finalizar por falta de datos."
            feedback = "La investigación no obtuvo registros."
            final_answer = (
                "No encontré datos para responder la consulta. "
                "Esta demostración contiene ventas ficticias "
                "de llaveros, miniaturas y dummys."
            )

    else:
        # Verificación independiente del resumen del analista:
        # recalculamos los resultados desde los datos originales.
        expected_results = analyze_sales(data)

        if not expected_results["valid"]:
            if research_attempts < 2:
                next_agent = "researcher"
                decision = "Pedir al investigador que revise los datos."
                feedback = "\n".join(expected_results["errors"])
            else:
                next_agent = "FINISH"
                decision = "Finalizar porque los datos siguen siendo inválidos."
                feedback = "\n".join(expected_results["errors"])
                final_answer = (
                    "No se pudo completar la tarea por errores "
                    f"en los datos:\n{feedback}"
                )

        elif (
            results != expected_results
            or not state.get("analysis_summary", "").strip()
        ):
            if analysis_attempts < 2:
                next_agent = "analyst"
                decision = "Solicitar cálculos y conclusiones al analista."

                if analysis_attempts:
                    feedback = (
                        "El análisis no coincide con los datos "
                        "o falta su resumen. Recalculá los resultados."
                    )
            else:
                next_agent = "FINISH"
                decision = "Finalizar porque el análisis no pasó la validación."
                feedback = "Los resultados no pudieron validarse."
                final_answer = (
                    "No se pudo obtener un análisis validado "
                    "después de dos intentos."
                )

        else:
            next_agent = "FINISH"
            completed = True
            decision = "Datos y cálculos validados. Finalizar la tarea."

            final_answer = (
                "Resultado final — datos ficticios de demostración\n\n"
                f"{state.get('research_summary', '')}\n\n"
                f"{state['analysis_summary']}\n\n"
                "Validación del supervisor: los datos tienen "
                "los campos requeridos y los resultados coinciden "
                "con el recálculo de unidades × precio unitario."
            )

    message = decision

    if feedback:
        message += f"\nObservaciones: {feedback}"

    if final_answer:
        message += f"\n\n{final_answer}"

    return {
        "next_agent": next_agent,
        "validation_feedback": feedback,
        "task_completed": completed,
        "final_answer": final_answer,
        "steps": steps + 1,
        "contributions": [
            *contributions,
            {
                "agent": "supervisor",
                "tool": "validation_rules",
                "summary": message,
            },
        ],
        "messages": [
            AIMessage(content=message, name="supervisor")
        ],
    }


def route_next(
    state: OrchestratorState,
) -> Literal["researcher", "analyst", "FINISH"]:
    """Devuelve el destino para las conexiones condicionales del grafo."""
    return state["next_agent"]

def supervisor_api(
    state: OrchestratorState,
) -> dict[str, Any]:
    """Supervisor con IA y controles deterministas de validación."""
    import json

    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import BaseModel, Field

    from config import get_llm

    class SupervisorDecision(BaseModel):
        next_agent: Literal["researcher", "analyst", "FINISH"] = Field(
            description="Siguiente destino del flujo."
        )
        reason: str = Field(
            description="Justificación breve de la decisión."
        )
        feedback: str = Field(
            description="Corrección concreta para el especialista, o vacío."
        )
        final_answer: str = Field(
            description="Respuesta final al usuario, o vacío si falta trabajo."
        )

    # Reutilizamos las comprobaciones del supervisor local.
    # Esta función devuelve una actualización; no modifica el estado.
    checked = supervisor(state)

    # Los límites y los errores terminales se resuelven sin llamar al LLM.
    if (
        checked["next_agent"] == "FINISH"
        and not checked["task_completed"]
    ):
        return checked

    contributions = state.get("contributions", [])

    research_attempts = sum(
        item.get("agent") == "researcher"
        for item in contributions
    )

    analysis_attempts = sum(
        item.get("agent") == "analyst"
        for item in contributions
    )

    data = state.get("research_data", [])
    expected_results = analyze_sales(data)

    allowed_destinations = []

    if research_attempts < 2:
        allowed_destinations.append("researcher")

    if expected_results["valid"] and analysis_attempts < 2:
        allowed_destinations.append("analyst")

    # Solo permitimos finalizar con éxito si Python validó los resultados.
    if checked["task_completed"]:
        allowed_destinations.append("FINISH")

    context = {
        "user_query": state["user_query"],
        "research_data": data,
        "research_summary": state.get("research_summary", ""),
        "analysis_results": state.get("analysis_results", {}),
        "analysis_summary": state.get("analysis_summary", ""),
        "validation_feedback": state.get("validation_feedback", ""),
        "python_validation": {
            "recommended_destination": checked["next_agent"],
            "results_validated": checked["task_completed"],
            "feedback": checked["validation_feedback"],
        },
        "allowed_destinations": allowed_destinations,
    }

    model = get_llm().with_structured_output(
        SupervisorDecision,
        method="function_calling",
    )

    decision = model.invoke([
        SystemMessage(content=(
            "Sos el supervisor de un equipo de investigación y análisis. "
            "Decidí quién debe intervenir o si corresponde finalizar. "
            "Elegí únicamente entre allowed_destinations. "
            "Rúbrica de revisión: "
            "1) Los productos recuperados deben coincidir con la solicitud. "
            "2) Los datos deben incluir unidades, precio, moneda y fuente. "
            "3) Los cálculos deben pasar la validación de Python. "
            "4) La explicación debe coincidir con los resultados numéricos. "
            "5) Debe distinguir facturación de ganancia y mencionar "
            "que los datos son ficticios. "
            "Si falta información, delegá al investigador. "
            "Si faltan cálculos o la explicación contiene errores, "
            "delegá al analista con una corrección concreta. "
            "No finalices si los resúmenes no responden a la solicitud, "
            "aunque los cálculos sean válidos. "
            "Al finalizar, integrá los resultados en español, "
            "sin inventar datos ni fuentes. "
            "Si pedís más trabajo, dejá final_answer vacío."
        )),
        HumanMessage(content=json.dumps(context, ensure_ascii=False)),
    ])

    if decision.next_agent not in allowed_destinations:
        raise ValueError(
            "El supervisor eligió un destino no permitido: "
            f"{decision.next_agent}"
        )

    completed = decision.next_agent == "FINISH"

    if completed and not decision.final_answer.strip():
        raise ValueError(
            "El supervisor decidió finalizar sin una respuesta final."
        )

    final_answer = decision.final_answer if completed else ""
    feedback = "" if completed else decision.feedback

    summary = (
        f"Decisión: {decision.next_agent}.\n"
        f"Motivo: {decision.reason}"
    )

    if feedback:
        summary += f"\nCorrección solicitada: {feedback}"

    return {
        "next_agent": decision.next_agent,
        "validation_feedback": feedback,
        "task_completed": completed,
        "final_answer": final_answer,
        "steps": state.get("steps", 0) + 1,
        "contributions": [
            *contributions,
            {
                "agent": "supervisor",
                "tool": "llm_routing_and_python_validation",
                "summary": summary,
            },
        ],
        "messages": [
            AIMessage(content=summary, name="supervisor")
        ],
    }