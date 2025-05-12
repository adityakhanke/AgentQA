from appium import webdriver
from tools.tool_registry import tool
from tools.session_management import load_app
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)

@tool(
    agent_names=["test_executor"],
    description="Get the current page source of the application. This will help get all the elements currently available on the page we are on",
    name="page_source",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Dictionary containing the page source of the current screen"
    }
)
async def page_source() -> dict:
    logging.info("Function Call: Page source, arguments: ")
    try:
        driver = (await load_app())["driver"]
        return {"message": "Success", "body": driver.page_source}
    except Exception as err:
        return {"message": "Failure", "body": err}



@tool(
    agent_names=["test_executor"],
    description="Lock the device we are testing on. We can pass the number of seconds we want to lock the device for.",
    name="lock_device",
    parameters={
        "time": {
            "type": "integer",
            "description": "Number of seconds to lock the device (negative for indefinite lock)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the lock operation indicating success or failure"
    }
)
## If time input is negative, it will lock itself unless we unlock it with unlock function
async def lock_device(time:int) -> dict:
    logging.info("Function Call: Lock Device, arguments: " + str(time))
    try:
        driver = (await load_app())["driver"]
        driver.lock(time)
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Unlock the device we are testing on by calling unlock_device()",
    name="unlock_device",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Result of the unlock operation indicating success or failure"
    }
)
async def unlock_device() -> dict:
    logging.info("Function Call: Unlock Device, arguments: ")
    try:
        driver = (await load_app())["driver"]
        driver.unlock()
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Get the orientation of the device, whether LANDSCAPE or PORTRAIT",
    name="get_orientation",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Dictionary containing the current orientation of the device (LANDSCAPE or PORTRAIT)"
    }
)
async def get_orientation() -> dict:
    logging.info("Function Call: Get Orientation, arguments: ")
    try:
        driver = (await load_app())["driver"]
        return {"message": "Success", "body": driver.orientation}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Set the orientation of the device to required orientation: LANDSCAPE or PORTRAIT",
    name="set_orientation",
    parameters={
        "orientation": {
            "type": "string",
            "description": "Desired orientation, either 'LANDSCAPE' or 'PORTRAIT'"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the orientation change operation"
    }
)
async def set_orientation(orientation: str) -> dict:
    logging.info("Function Call: Set Orientation, arguments: " + orientation)
    try:
        driver = (await load_app())["driver"]
        driver.orientation = orientation.upper
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Get the current location of the device by calling get_location().",
    name="get_location",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Dictionary containing the current geolocation coordinates of the device"
    }
)
async def get_location() -> dict:
    logging.info("Function Call: Get Location, arguments: ")
    try:
        driver = (await load_app())["driver"]
        return {"message": "Success", "body": driver.location}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Set the current location of the device by passing the latitudes and longitudes",
    name="set_location",
    parameters={
        "latitude": {
            "type": "integer",
            "description": "Latitude coordinate to set"
        },
        "longitude": {
            "type": "integer",
            "description": "Longitude coordinate to set"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the location change operation"
    }
)
async def set_location(latitude: int, longitude: int) -> dict:
    logging.info("Function Call: Set Location, arguments: " + latitude + " " + longitude)
    try:
        driver = (await load_app())["driver"]
        driver.set_location(latitude, longitude)
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Set the app to background for a specified duration",
    name="background_app",
    parameters={
        "time": {
            "type": "integer",
            "description": "Number of seconds to keep app in background (negative for indefinite)"
        }
    },
    output={
        "type": Dict[str, Any],
        "description": "Result of the background operation indicating success or failure"
    }
)
## If time input is negative, it will put app to background infinitely unless we bring the app back to foreground
async def background_app(time:int) -> dict:
    logging.info("Function Call: Background App, arguments: ")
    try:
        driver = (await load_app())["driver"]
        driver.background_app(time)
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}

@tool(
    agent_names=["test_executor"],
    description="Bring back the app from background by calling activate_app()",
    name="activate_app",
    parameters={},
    output={
        "type": Dict[str, Any],
        "description": "Result of the app activation operation indicating success or failure"
    }
)
## Bring the background app back to the screen
async def activate_app() -> dict:
    logging.info("Function Call: Activate App, arguments: ")
    try:
        driver = (await load_app())["driver"]
        driver.launch_app()
        return {"message": "Success", "body": None}
    except Exception as err:
        return {"message": "Failure", "body": err}
