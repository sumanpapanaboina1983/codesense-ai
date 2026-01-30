import asyncio
import random
import sys
from copilot import CopilotClient
from copilot.tools import define_tool
from copilot.generated.session_events import SessionEventType

from pydantic import BaseModel

class WeatherParams(BaseModel):
    city: str

# Define a tool that Copilot can call
@define_tool(description="Get the current weather for a city", params_type=WeatherParams)
async def get_weather(params: WeatherParams) -> dict:
    print("inside tool")
    print(params)
    city = params.city
    print("city:", city)
    # In a real app, you'd call a weather API here
    conditions = ["sunny", "cloudy", "rainy", "partly cloudy"]
    temp = random.randint(50, 80)
    condition = random.choice(conditions)
    message = {"city": city, "temperature": f"{temp}°F", "condition": condition}
    print(message)
    return message

async def main():
    client = CopilotClient()
    await client.start()

    session = await client.create_session({
        "model": "gpt-4.1",
        "streaming": True,
        "tools": [get_weather],
    })

    def handle_event(event):
        if event.type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
            sys.stdout.write(event.data.delta_content)
            sys.stdout.flush()
        if event.type == SessionEventType.SESSION_IDLE:
            print()

    session.on(handle_event)

    await session.send_and_wait({
        "prompt": "What's the weather like in Seattle and Tokyo?"
    })

    await client.stop()

asyncio.run(main())