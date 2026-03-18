import os
from pydantic_ai.mcp import MCPServerStdio
import asyncio
import requests
from livekit.agents import function_tool, JobContext
import dotenv
from livekit.agents import Agent, AgentSession
from livekit.plugins import openai, assemblyai, silero
from livekit.agents import cli, WorkerOptions

dotenv.load_dotenv()

@function_tool
async def firecrawl_search(query: str, limit:int = 5):
  """
    Search the web for real-time information using Firecrawl.
  """
  url = "https://api.firecrawl.dev/v1/search"
  payload = {"query": query, "limit": limit}
  headers = {"Authorization": f"Bearer {os.getenv("FIRECRAWL_API_KEY")}",
             "Content-Type": "application/json"}
  loop = asyncio.get_event_loop()
  response = await loop.run_in_executor(
      None, lambda: requests.post(url, json=payload, headers=headers)
  )
  response.raise_for_status()
  return response.json()

async def build_livekit_tools(server: MCPServerStdio):
  avail_tools = await server.list_tools()
  tools = []
  for tool in avail_tools:
    if tool.name == "deploy_edge_function":
      continue
    def make_proxy(tool_def = tool):
      async def proxy():
        """
            Call a Supabase backend tool to retrieve or modify internal application data.
            Use this for queries involving stored user data, database records, or backend operations.
        """
        response = await server.call_tool(tool_def.name, {}) #tool doesn't take inputs
        return response

      #proxy.__name__ = tool_def.name
      return function_tool(proxy, name=tool_def.name)
    tools.append(make_proxy())
  return tools

async def entrypoint(ctx: JobContext) -> None:
    """
    Main entrypoint for the LiveKit agent.
    """
    await ctx.connect()
    server = MCPServerStdio(
    r"C:\Users\sride\AppData\Roaming\npm\mcp-server-supabase.cmd",
    args=["--access-token", os.getenv("SUPABASE_TOKEN")]
    )
    await server.__aenter__()

    try:
        supabase_tools = await build_livekit_tools(server)
        tools = [firecrawl_search] + supabase_tools

        agent = Agent(
            instructions=(
                "You can either perform live web searches via `firecrawl_search` or "
                "database queries via Supabase MCP tools. "
                "Choose the appropriate tool based on whether the user needs fresh web data "
                "(news, external facts) or internal Supabase data."
            ),
            tools=tools,
        )

        session = AgentSession(
            vad=silero.VAD.load(min_silence_duration=0.1),
            stt=assemblyai.STT(api_key=os.getenv("ASSEMBLYAI_API_KEY")),
            llm=openai.LLM(model="gpt-4o", api_key=os.getenv("OPENAI_API_KEY")),
            tts=openai.TTS(voice="ash"),
        )
        await session.start(agent=agent, room=ctx.room)
        await session.generate_reply(instructions="Hello! How can I assist you today?")

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Session cancelled, shutting down.")

    finally:
        await server.__aexit__(None, None, None)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_SECRET")
        )
    )