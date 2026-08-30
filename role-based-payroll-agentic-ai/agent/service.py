from agent.planner import execute_agent_pipeline
from agent.novalm import status as novalm_status

class IndependentAgent:
    """Gemini-free NovaHR agent orchestrator."""
    def process_query(self, user, message):
        result=execute_agent_pipeline(user, message)
        result["engine"]="NovaLM + deterministic safety router"
        return result

    def model_status(self):
        return novalm_status()

def run_agent(user, message):
    return IndependentAgent().process_query(user, message)
