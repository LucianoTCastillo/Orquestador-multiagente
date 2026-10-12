from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.analyst_agent import analyst_agent, analyst_agent_api
from agents.research_agent import research_agent, research_agent_api
from config import get_llm, get_run_mode
from state import OrchestratorState
from supervisor import route_next, supervisor, supervisor_api


def build_graph(mode: str = "local"):
    """Construye el grafo con los nodos del modo elegido."""
    if mode not in {"local", "api"}:
        raise ValueError("El modo debe ser 'local' o 'api'.")

    if mode == "api":
        # Valida clave y modelo antes de iniciar el flujo.
        get_llm()

        supervisor_node = supervisor_api
        researcher_node = research_agent_api
        analyst_node = analyst_agent_api
    else:
        supervisor_node = supervisor
        researcher_node = research_agent
        analyst_node = analyst_agent

    builder = StateGraph(OrchestratorState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("analyst", analyst_node)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        route_next,
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "FINISH": END,
        },
    )

    builder.add_edge("researcher", "supervisor")
    builder.add_edge("analyst", "supervisor")

    return builder.compile()


def create_initial_state(query: str) -> OrchestratorState:
    """Inicializa el estado para una nueva consulta."""
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "next_agent": "researcher",
        "research_data": [],
        "research_summary": "",
        "analysis_results": {},
        "analysis_summary": "",
        "contributions": [],
        "validation_feedback": "",
        "steps": 0,
        "max_steps": 10,
        "task_completed": False,
        "final_answer": "",
    }


def run_demo():
    """Ejecuta la consulta de demostración en el modo configurado."""
    mode = get_run_mode()

    query = (
        "Investigá las ventas de llaveros, miniaturas y dummys. "
        "Calculá la facturación de cada producto y el total, "
        "e indicá cuál generó más ingresos."
    )

    graph = build_graph(mode)
    initial_state = create_initial_state(query)

    print("ORQUESTADOR MULTIAGENTE")
    print(f"Modo de ejecución: {mode}")

    if mode == "local":
        print("Sin llamadas a OpenAI ni consumo de créditos.")
    else:
        print("Con llamadas a OpenAI: requiere créditos de API.")

    print("Datos ficticios de demostración.")
    print(f"\nConsulta: {query}")
    print("\nFLUJO DE DELEGACIÓN")

    final_state = None
    previous_contributions = 0

    for current_state in graph.stream(
        initial_state,
        config={"recursion_limit": 30},
        stream_mode="values",
    ):
        contributions = current_state.get("contributions", [])

        for contribution in contributions[previous_contributions:]:
            agent = contribution["agent"]
            print(f"\n[{agent.upper()}]")

            if agent == "supervisor":
                print(
                    f"Próximo destino: {current_state['next_agent']}"
                )

            print(contribution["summary"])

        previous_contributions = len(contributions)
        final_state = current_state

    if final_state is None:
        raise RuntimeError("El grafo no devolvió ningún estado.")

    print("\n" + "=" * 60)
    print("RESPUESTA FINAL")
    print("=" * 60)
    print(final_state["final_answer"])

    status = (
        "Completada y validada"
        if final_state["task_completed"]
        else "Incompleta"
    )

    print(f"\nEstado de la tarea: {status}")
    print(f"Intervenciones: {final_state['steps']}")


if __name__ == "__main__":
    run_demo()