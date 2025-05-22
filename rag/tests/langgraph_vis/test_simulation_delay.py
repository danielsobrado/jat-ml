#!/usr/bin/env python
# test_simulation_delay.py - Test simulation delay feature
import asyncio
import logging
import sys
from rag.langgraph_vis.core.definitions import create_basic_agent_workflow
from langgraph.graph import StateGraph

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    stream=sys.stdout)

logger = logging.getLogger("test_simulation_delay")

async def main():
    # Create a graph using our helper function
    graph = create_basic_agent_workflow()
    
    # Basic input for the graph
    input_args = {}
    
    logger.info("Running graph WITHOUT simulation delay...")
    # Run the graph WITHOUT simulation delay
    result_without_delay = await graph.ainvoke(input_args)
    logger.info(f"Graph execution completed without delay: {result_without_delay}")
    
    logger.info("\n\nRunning graph WITH simulation delay...")
    # Run the graph WITH simulation delay
    result_with_delay = await graph.ainvoke(
        input_args, 
        config={"simulation_delay_ms": 2000}  # 2 second delay
    )
    logger.info(f"Graph execution completed with delay: {result_with_delay}")

if __name__ == "__main__":
    asyncio.run(main())
