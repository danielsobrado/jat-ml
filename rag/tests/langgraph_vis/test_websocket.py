#!/usr/bin/env python
# test_websocket.py - Simple script to test WebSocket connection and execution
import asyncio
import websockets
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    stream=sys.stdout)

logger = logging.getLogger("test_websocket")

async def test_websocket(graph_id, initial_args=None, simulation_delay_ms=None):
    """Test WebSocket connection and execution for a graph."""
    if initial_args is None:
        initial_args = {}
    
    # Build the URL (adjust as needed for your environment)
    # This matches the URL in the LangGraphSocketService
    ws_url = f"ws://localhost:8090/v1/lg-vis/ws/langgraph/graphs/{graph_id}/execute"
    logger.info(f"Connecting to WebSocket at: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            logger.info("WebSocket connected!")
            
            # Prepare initial message
            initial_message = {
                "input_args": initial_args,
            }
            if simulation_delay_ms is not None:
                initial_message["simulation_delay_ms"] = simulation_delay_ms
                
            # Send initial message
            logger.info(f"Sending initial message: {initial_message}")
            await websocket.send(json.dumps(initial_message))
            
            # Listen for messages
            while True:
                try:
                    response = await websocket.recv()
                    event = json.loads(response)
                    logger.info(f"Received event: {event['eventType'] if 'eventType' in event else 'unknown'}")
                    logger.debug(f"Event details: {event}")
                    
                    # If graph execution ends, we're done
                    if event.get('eventType') == 'graph_execution_end':
                        logger.info("Graph execution completed successfully!")
                        break
                    # If we get an error, also exit
                    elif event.get('eventType') == 'graph_error':
                        logger.error(f"Graph execution error: {event.get('message')}")
                        if 'details' in event:
                            logger.error(f"Error details: {event['details']}")
                        break
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    break
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}", exc_info=True)

if __name__ == "__main__":
    # Example usage with a simple graph - update with your graph ID
    graph_id = "example_document_workflow"  # Use a graph ID that exists in your system
    
    # Optional: Provide initial arguments and simulation delay
    initial_args = {}
    simulation_delay_ms = 2000  # 2 seconds delay
    
    asyncio.run(test_websocket(graph_id, initial_args, simulation_delay_ms))
