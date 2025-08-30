

from .instruction import INSTRUCTION
from google.adk.agents import Agent
from .tools import rag_tool
from dotenv import load_dotenv

load_dotenv()


root_agent = Agent(
  name="lawer_agent",
  model="gemini-2.0-flash",
  description="Bạn là một trợ lý hỗ trợ tra cứu thông tin về Luật tại Việt Nam",
  instruction=INSTRUCTION,
  tools=[rag_tool]
)


