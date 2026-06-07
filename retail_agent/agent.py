from google.adk.agents import LlmAgent

def say_hello(name: str) -> dict:
    """Says hello to someone."""
    return {"message": f"Hello, {name}!"}

root_agent = LlmAgent(
    model="gemini-2.5-flash-lite",
    name="test_agent",
    description="A simple test agent.",
    instruction="You are a helpful assistant. Use say_hello when greeting someone.",
    tools=[say_hello],
)