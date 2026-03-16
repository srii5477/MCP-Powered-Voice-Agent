import os
from firecrawl import FirecrawlApp
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPServerStdio
import asyncio
import requests
from livekit.agents import function_tool, WorkerOptions, JobContext
import dotenv

dotenv.load_dotenv()

fcapp = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
mcpserv = MCPServerStdio("npx",
                         args=["-y", "@supabase/mcp-server-supabase@latest",
                               "--access-token", os.getenv("SUPABASE_TOKEN")])



@function_tool
async def firecrawl_search(query, limit=5):
  url = "https://api.firecrawl.dev/v1/search"
  payload = {"query": query, "limit": limit}
  headers = {"Authorization": f"Bearer {os.getenv("FIRECRAWL_API_KEY")}",
             "Content-Type": "application/json"}
  loop = await asyncio.get_event_loop()
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
      async def proxy(context: RunContext):
        response = await server.call_tool(tool_def.name, {}, ctx=context)
        return response
      return function_tool(proxy)
    tools.append(make_proxy())
  return tools


from livekit.agents import Agent, AgentSession
from livekit.plugins import openai, assemblyai, silero

async def entrypoint(ctx: JobContext) -> None:
    """
    Main entrypoint for the LiveKit agent.
    """
    await ctx.connect()
    server = MCPServerStdio(
        "npx",
        args=["-y", "@supabase/mcp-server-supabase@latest", "--access-token", os.getenv("SUPABASE_TOKEN")],
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
            stt=assemblyai.STT(word_boost=["Supabase"]),
            llm=openai.LLM(model="gpt-4o"),
            tts=openai.TTS(voice="ash"),
        )

        await session.start(agent=agent, room=ctx.room)
        await session.generate_reply(instructions="Hello! How can I assist you today?")

        # Keep the session alive until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Session cancelled, shutting down.")

    finally:
        await server.__aexit__(None, None, None)


from livekit.agents import cli, WorkerOptions

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_SECRET")
        )
    )