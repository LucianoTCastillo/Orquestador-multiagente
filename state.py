from typing import Any, Literal

from langgraph.graph import MessagesState


class OrchestratorState(MessagesState):
    """Información compartida por el supervisor y los especialistas."""

    # Solicitud original del usuario.
    user_query: str

    # Próximo destino elegido por el supervisor.
    next_agent: Literal["researcher", "analyst", "FINISH"]

    # Datos y fuentes obtenidos por el investigador.
    research_data: list[dict[str, Any]]
    research_summary: str

    # Cálculos y conclusiones del analista.
    analysis_results: dict[str, Any]
    analysis_summary: str

    # Registro de quién aportó cada resultado.
    contributions: list[dict[str, str]]

    # Observaciones para solicitar correcciones.
    validation_feedback: str

    # Control del flujo y condición de parada.
    steps: int
    max_steps: int
    task_completed: bool

    # Respuesta integrada para el usuario.
    final_answer: str