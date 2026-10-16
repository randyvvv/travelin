from google.adk import Workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


async def run_workflow(workflow: Workflow, trip_id: str) -> None:
    """Runs an ADK workflow whose START input is the trip ID. Results land in Firestore."""
    sessions = InMemorySessionService()
    runner = Runner(node=workflow, session_service=sessions)
    session = await sessions.create_session(app_name=runner.app_name, user_id="travelin-api")
    message = types.Content(role="user", parts=[types.Part(text=trip_id)])
    async for _event in runner.run_async(
        user_id="travelin-api", session_id=session.id, new_message=message
    ):
        pass


def trip_id_from(node_input: object) -> str:
    return node_input.parts[0].text if isinstance(node_input, types.Content) else str(node_input)
