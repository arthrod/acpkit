from pydantic_ai import Agent
from pydantic_acp import AcpProvider

provider = AcpProvider(agent=None, cwd="/workspace")
model = provider.model("zed-agent")
agent = Agent(model)

